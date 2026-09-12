"""Versioned embedding wrappers.

Each embedder is bound to one EmbeddingVersion, so the model id and dimension travel
with every vector it produces and nothing is ambiguous when a second model appears
(PR4 migration). A content-hash SQLite cache means re-ingest and the migration backfill
never re-embed unchanged text.

Two backends share one interface (``encode`` / ``encode_one``):

* ``Embedder``: the real BGE-M3 via sentence-transformers (multilingual, German).
* ``HashEmbedder``: deterministic, dependency-free vectors from a content hash. Used by
  tests, CI, and reproducible migration shadow-evals where downloading a multi-GB model
  is neither available nor wanted. Same dimension as the version it's bound to.

See echoclaim-spine/BUILD_PLAN.md sections 3.3 and 3.4.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import numpy as np

from .config import EmbeddingVersion, settings


def content_hash(text: str, model_id: str) -> str:
    return hashlib.sha256(f"{model_id}\x00{text}".encode()).hexdigest()


class _SqliteVectorCache:
    """Tiny persistent cache: (hash) -> float32 vector bytes."""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.execute("CREATE TABLE IF NOT EXISTS vec (h TEXT PRIMARY KEY, v BLOB)")

    def get(self, h: str) -> np.ndarray | None:
        row = self.con.execute("SELECT v FROM vec WHERE h=?", (h,)).fetchone()
        return np.frombuffer(row[0], dtype=np.float32) if row else None

    def put(self, h: str, v: np.ndarray) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO vec VALUES (?, ?)", (h, v.astype(np.float32).tobytes())
        )
        self.con.commit()


class _BaseEmbedder:
    version: EmbeddingVersion

    def _encode_uncached(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def __init__(self, version: EmbeddingVersion, use_cache: bool = True):
        self.version = version
        self._cache = _SqliteVectorCache(settings.embed_cache_path) if use_cache else None

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return (len(texts), dim) float32, normalized for cosine."""
        if not texts:
            return np.empty((0, self.version.dim), dtype=np.float32)

        out: list[np.ndarray | None] = [None] * len(texts)
        todo_idx, todo_txt = [], []
        for i, t in enumerate(texts):
            h = content_hash(t, self.version.model_id)
            cached = self._cache.get(h) if self._cache else None
            if cached is not None:
                out[i] = cached
            else:
                todo_idx.append(i)
                todo_txt.append(t)

        if todo_txt:
            vecs = self._encode_uncached(todo_txt).astype(np.float32)
            for k, i in enumerate(todo_idx):
                out[i] = vecs[k]
                if self._cache:
                    self._cache.put(content_hash(texts[i], self.version.model_id), vecs[k])

        arr = np.vstack(out)
        assert arr.shape[1] == self.version.dim, (
            f"dim mismatch: backend produced {arr.shape[1]}, config says {self.version.dim}"
        )
        return arr

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


class Embedder(_BaseEmbedder):
    """Real embedder: BGE-M3 (or whatever the version's model_id points at)."""

    def __init__(self, version: EmbeddingVersion, use_cache: bool = True):
        super().__init__(version, use_cache)
        self._model = None  # lazy so the module imports without the heavy dep

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.version.model_id, device=settings.torch_device)
        return self._model

    def _encode_uncached(self, texts: list[str]) -> np.ndarray:
        return self._load().encode(
            texts,
            batch_size=settings.embed_batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )


class HashEmbedder(_BaseEmbedder):
    """Deterministic, dependency-free embedder.

    Hashes each text into a fixed seed, draws a vector from that seed, and L2-normalizes.
    Identical text -> identical vector, so it is reproducible across machines and runs,
    which is exactly what an offline eval / migration shadow-comparison needs. It carries
    no semantics. It is for plumbing, determinism, and CI, not retrieval quality.
    """

    def _encode_uncached(self, texts: list[str]) -> np.ndarray:
        dim = self.version.dim
        vecs = np.empty((len(texts), dim), dtype=np.float32)
        for i, t in enumerate(texts):
            seed = int.from_bytes(
                hashlib.sha256(f"{self.version.name}\x00{t}".encode()).digest()[:8], "big"
            )
            rng = np.random.default_rng(seed)
            v = rng.standard_normal(dim).astype(np.float32)
            n = np.linalg.norm(v)
            vecs[i] = v / n if n else v
        return vecs


def get_embedder(version: EmbeddingVersion, *, backend: str | None = None, use_cache: bool = True) -> _BaseEmbedder:
    """Return the embedder for ``version`` using the configured (or overridden) backend."""
    backend = backend or settings.embed_backend
    if backend == "hash":
        # The hash backend is deterministic and cheap, and it shares the cache key space
        # (version.model_id) with the real model, so caching it would let a hash vector
        # leak into a later real-model run, so never cache it.
        return HashEmbedder(version, use_cache=False)
    if backend in ("sentence-transformers", "st", "bge"):
        return Embedder(version, use_cache=use_cache)
    raise ValueError(f"unknown EMBED_BACKEND: {backend!r}")
