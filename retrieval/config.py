"""Central configuration for the retrieval subsystem.

Everything two modules must agree on (model ids, vector names, dimensions, collection
names, top-k) lives here so nothing drifts out of sync. All values are env-overridable
so the same code runs against a local Docker Qdrant, a hosted cluster, or the offline
hash-embedder path used by tests and CI.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmbeddingVersion:
    """A named, versioned embedding configuration.

    ``name`` is the Qdrant *named vector* key, so two versions can coexist in one
    collection — this is what makes the zero-downtime migration (PR4) clean.
    """
    name: str          # qdrant named-vector key, e.g. "emb_v1"
    model_id: str      # huggingface id, e.g. "BAAI/bge-m3"
    dim: int           # vector dimension


# Registered embedding versions. Add a new entry to introduce a model; never edit an
# existing one in place — that would invalidate vectors already written under it.
EMBEDDING_VERSIONS: dict[str, EmbeddingVersion] = {
    "emb_v1": EmbeddingVersion("emb_v1", "BAAI/bge-m3", 1024),
    # "emb_v2": EmbeddingVersion("emb_v2", "<next-model>", <dim>),  # added in PR4
}


@dataclass(frozen=True)
class Settings:
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str | None = os.getenv("QDRANT_API_KEY")
    collection: str = os.getenv("QDRANT_COLLECTION", "echoclaim_policies")

    # The version reads are served from. Migration flips this (see migrate.py, PR4).
    active_version: str = os.getenv("ACTIVE_EMBED_VERSION", "emb_v1")
    # When set, ingests also write this version's vectors (dual-write phase).
    dual_write_version: str | None = os.getenv("DUAL_WRITE_EMBED_VERSION") or None

    # Embedding backend. "sentence-transformers" loads the real BGE-M3 model;
    # "hash" is a deterministic, dependency-free embedder for offline tests, CI,
    # and reproducible migration shadow-evals. See embedder.get_embedder.
    embed_backend: str = os.getenv("EMBED_BACKEND", "sentence-transformers")

    rerank_model_id: str = os.getenv("RERANK_MODEL_ID", "BAAI/bge-reranker-v2-m3")

    # Structure-aware chunking budget (see chunker.py).
    max_chunk_tokens: int = int(os.getenv("MAX_CHUNK_TOKENS", "400"))
    chunk_overlap_tokens: int = int(os.getenv("CHUNK_OVERLAP_TOKENS", "64"))

    top_k_recall: int = int(os.getenv("TOP_K_RECALL", "50"))   # bi-encoder candidates
    top_k_final: int = int(os.getenv("TOP_K_FINAL", "6"))      # after rerank

    embed_batch_size: int = int(os.getenv("EMBED_BATCH_SIZE", "64"))
    embed_cache_path: str = os.getenv("EMBED_CACHE_PATH", ".cache/embeddings.sqlite")

    # Where the corpus lives and where ingest writes its manifest.
    corpus_dir: str = os.getenv("CORPUS_DIR", "data/policies")
    ingest_manifest_path: str = os.getenv("INGEST_MANIFEST_PATH", ".cache/ingest_manifest.json")

    # Golden set for retrieval-quality evaluation (eval.py).
    golden_set_path: str = os.getenv("GOLDEN_SET_PATH", "data/eval/golden_set.jsonl")
    eval_k: int = int(os.getenv("EVAL_K", "5"))

    versions: dict[str, EmbeddingVersion] = field(default_factory=lambda: dict(EMBEDDING_VERSIONS))

    def version(self, name: str) -> EmbeddingVersion:
        return self.versions[name]


settings = Settings()
