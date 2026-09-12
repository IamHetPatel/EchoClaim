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

    def drop_collection(self) -> None:
        """Delete the collection if it exists. Used by --recreate for a hermetic run."""
        try:
            self.client.delete_collection(self.collection)
        except Exception:
            pass  # absent is the desired end state either way

    def ensure_collection(self, version_names: list[str]) -> None:
        """Create the collection (if absent) with a named vector slot per version.

        Slots are created for *every registered* embedding version, not only the ones
        being written now. Qdrant cannot add a named vector to a live collection --
        ``update_collection`` takes a ``VectorParamsDiff``, which can change hnsw or
        quantization settings but not introduce a new vector -- so a slot that does not
        exist at creation cannot be added later without rebuilding the collection.

        An empty slot costs nothing: points simply carry no vector under that name. This
        is what makes the later migration a pointer flip instead of a rebuild.
        """
        from qdrant_client import models

        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection not in existing:
            slots = sorted(set(version_names) | set(settings.versions))
            vectors_config = {
                name: models.VectorParams(
                    size=settings.version(name).dim, distance=models.Distance.COSINE
                )
                for name in slots
            }
            self.client.create_collection(self.collection, vectors_config=vectors_config)
            # Index the payload keys we filter on so filtering stays fast at scale.
            for key in ("product_code", "lang", "doc_type"):
                self.client.create_payload_index(
                    self.collection, field_name=key,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            self._set_meta({"versions": sorted(version_names), "slots": slots,
                            "active": settings.active_version})
        else:
            self.add_vector_version(version_names)

    def add_vector_version(self, version_names: list[str]) -> None:
        """Verify the named-vector slots exist. Qdrant cannot create them after the fact.

        Kept as a named step because it is phase 1 of the migration, but it is a check,
        not a mutation: ``update_collection`` accepts only a ``VectorParamsDiff``
        (hnsw / quantization / on_disk / memory), so there is no API that adds a vector
        name to a live collection. If a slot is missing the collection has to be rebuilt
        -- see ``retrieval.migrate`` for the alias-swap path that does it without taking
        reads down.
        """
        info = self.client.get_collection(self.collection)
        present = set(info.config.params.vectors or {})
        missing = [v for v in version_names if v not in present]
        if missing:
            raise RuntimeError(
                f"collection {self.collection!r} has no named-vector slot for "
                f"{missing}; present: {sorted(present)}. Qdrant cannot add one in place. "
                f"Rebuild with `python -m retrieval.migrate rebuild --to {missing[0]}`."
            )

    def aliases_of(self, collection: str | None = None) -> list[str]:
        target = collection or self.collection
        return [a.alias_name for a in self.client.get_collection_aliases(target).aliases]

    def switch_alias(self, alias: str, to_collection: str) -> None:
        """Atomically repoint an alias. This is the zero-downtime cutover primitive.

        Qdrant applies the delete and create in one operation, so no read observes the
        alias as missing.
        """
        from qdrant_client import models

        self.client.update_collection_aliases(change_aliases_operations=[
            models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias)),
            models.CreateAliasOperation(create_alias=models.CreateAlias(
                collection_name=to_collection, alias_name=alias)),
        ])

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

        # query_points is the current read API; client.search() was deprecated in
        # qdrant-client 1.10 and removed in 1.19. Keep the old call as a fallback so the
        # module still works against the older client pinned in some environments.
        if hasattr(self.client, "query_points"):
            res = self.client.query_points(
                self.collection,
                query=query_vector.tolist(),
                using=version,          # the named vector to search
                query_filter=flt,
                limit=limit,
                with_payload=True,
            ).points
        else:  # pragma: no cover - legacy client
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
