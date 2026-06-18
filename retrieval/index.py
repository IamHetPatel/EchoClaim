"""Qdrant wrapper with named-vector versioning.

One collection holds multiple embedding versions as *named vectors* (emb_v1, emb_v2).
Reads target the active version; the migration (PR4) writes a second version alongside
the first and flips the active pointer atomically. ``qdrant_client`` is imported lazily
so this module, and everything that only needs the chunker/embedder, imports without
the dependency installed.

See echoclaim-spine/BUILD_PLAN.md sections 3.2 and 3.4.
"""
from __future__ import annotations

from dataclasses import dataclass

from .chunker import Chunk
from .config import settings


@dataclass
class Hit:
    score: float
    payload: dict

    @property
    def clause_id(self) -> str:
        return self.payload.get("clause_id", "")

    @property
    def text(self) -> str:
        return self.payload.get("text", "")


class QdrantIndex:
    def __init__(self):
        from qdrant_client import QdrantClient

        self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        self.collection = settings.collection

    # ---- schema / versions ---------------------------------------------------

    def ensure_collection(self, version_names: list[str]) -> None:
        """Create the collection (if absent) with one named vector per version."""
        from qdrant_client import models

        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection not in existing:
            vectors_config = {
                name: models.VectorParams(
                    size=settings.version(name).dim, distance=models.Distance.COSINE
                )
                for name in version_names
            }
            self.client.create_collection(self.collection, vectors_config=vectors_config)
            # Index the payload keys we filter on so filtering stays fast at scale.
            for key in ("product_code", "lang", "doc_type"):
                self.client.create_payload_index(
                    self.collection, field_name=key,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            self._set_meta({"versions": sorted(version_names), "active": settings.active_version})
        else:
            self.add_vector_version(version_names)

    def add_vector_version(self, version_names: list[str]) -> None:
        """Add a new named vector to an existing collection (PR4, dual-write setup).

        NOTE: adding a named vector in place requires a recent Qdrant. If the running
        server is too old, create ``{collection}__v2``, backfill, then swap by alias.
        """
        from qdrant_client import models

        meta = self._get_meta()
        known = set(meta.get("versions", []))
        new = [v for v in version_names if v not in known]
        for name in new:
            self.client.update_collection(
                self.collection,
                vectors_config={
                    name: models.VectorParams(
                        size=settings.version(name).dim, distance=models.Distance.COSINE
                    )
                },
            )
        if new:
            meta["versions"] = sorted(known | set(new))
            self._set_meta(meta)

    # ---- writes --------------------------------------------------------------

    def upsert(self, chunks: list[Chunk], vectors_by_version: dict[str, object]) -> None:
        """Upsert points carrying one or more named vectors.

        ``vectors_by_version``: {version_name: ndarray[len(chunks), dim]}. Dual-write =
        pass two versions here.
        """
        from qdrant_client import models

        points = []
        for i, ch in enumerate(chunks):
            vector = {v: vectors_by_version[v][i].tolist() for v in vectors_by_version}
            points.append(models.PointStruct(id=ch.id, vector=vector, payload=ch.payload()))
        self.client.upsert(self.collection, points=points, wait=True)

    # ---- reads ---------------------------------------------------------------

    def search(
        self,
        query_vector,
        *,
        version: str,
        limit: int,
        product_code: str | None = None,
        lang: str | None = None,
    ) -> list[Hit]:
        from qdrant_client import models

        must = []
        if product_code:
            must.append(models.FieldCondition(key="product_code",
                                              match=models.MatchValue(value=product_code)))
        if lang:
            must.append(models.FieldCondition(key="lang",
                                              match=models.MatchValue(value=lang)))
        flt = models.Filter(must=must) if must else None

        res = self.client.search(
            self.collection,
            query_vector=models.NamedVector(name=version, vector=query_vector.tolist()),
            query_filter=flt,
            limit=limit,
            with_payload=True,
        )
        return [Hit(score=p.score, payload=p.payload) for p in res]

    # ---- active-version pointer (atomic cutover) -----------------------------

    def get_active_version(self) -> str:
        return self._get_meta().get("active", settings.active_version)

    def set_active_version(self, version: str) -> None:
        meta = self._get_meta()
        meta["active"] = version
        self._set_meta(meta)

    # ---- meta (stored as a single reserved point) ----------------------------

    _META_ID = "00000000-0000-0000-0000-0000000000ff"

    def _set_meta(self, meta: dict) -> None:
        from qdrant_client import models

        self.client.upsert(
            self.collection,
            points=[models.PointStruct(id=self._META_ID, vector={}, payload={"_index_meta": meta})],
            wait=True,
        )

    def _get_meta(self) -> dict:
        recs = self.client.retrieve(self.collection, ids=[self._META_ID], with_payload=True)
        return recs[0].payload.get("_index_meta", {}) if recs else {}
