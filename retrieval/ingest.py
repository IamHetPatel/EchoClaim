"""Corpus ingest: load -> chunk -> embed -> upsert into the Qdrant named-vector index.

This is the PR1 entrypoint. It writes the active embedding version (plus the dual-write
version, if one is configured for a migration) and records an ``index_meta`` manifest so
the embedding version that produced each index is never ambiguous.

Run it::

    python -m retrieval.ingest                 # ingest into Qdrant
    python -m retrieval.ingest --dry-run       # chunk + embed + write manifest, no Qdrant
    EMBED_BACKEND=hash python -m retrieval.ingest --dry-run   # offline, no model download

If Qdrant is unreachable, ingest degrades to a dry run with a warning rather than
failing — matching the repo's "the demo never breaks" tool convention.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .chunker import Chunk, chunk_document
from .config import settings
from .corpus import load_corpus
from .embedder import get_embedder


def load_and_chunk(corpus_dir: str | None = None) -> list[Chunk]:
    docs = load_corpus(corpus_dir or settings.corpus_dir)
    chunks: list[Chunk] = []
    for d in docs:
        chunks.extend(
            chunk_document(
                d.text,
                doc_id=d.doc_id,
                doc_type=d.doc_type,
                product_code=d.product_code,
                lang=d.lang,
                max_tokens=settings.max_chunk_tokens,
                overlap=settings.chunk_overlap_tokens,
            )
        )
    return chunks


def _target_versions() -> list[str]:
    """Active version, plus the dual-write version during a migration."""
    versions = [settings.active_version]
    if settings.dual_write_version and settings.dual_write_version not in versions:
        versions.append(settings.dual_write_version)
    return versions


def _write_manifest(manifest: dict) -> None:
    path = Path(settings.ingest_manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def ingest(corpus_dir: str | None = None, *, dry_run: bool = False, backend: str | None = None) -> dict:
    chunks = load_and_chunk(corpus_dir)
    versions = _target_versions()

    vectors_by_version = {}
    for name in versions:
        emb = get_embedder(settings.version(name), backend=backend)
        vectors_by_version[name] = emb.encode([c.text for c in chunks])

    manifest = {
        "collection": settings.collection,
        "active": settings.active_version,
        "versions": versions,
        "embedding_versions": {
            name: {"model_id": settings.version(name).model_id, "dim": settings.version(name).dim}
            for name in versions
        },
        "backend": backend or settings.embed_backend,
        "n_docs": len({c.doc_id for c in chunks}),
        "n_chunks": len(chunks),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dry_run": dry_run,
    }

    if not dry_run:
        try:
            from .index import QdrantIndex

            idx = QdrantIndex()
            idx.ensure_collection(versions)
            idx.upsert(chunks, vectors_by_version)
            manifest["upserted"] = True
        except Exception as exc:  # qdrant not running / client missing -> manifest-only
            print(f"[ingest] Qdrant unavailable ({exc}); writing manifest only.")
            manifest["dry_run"] = True
            manifest["upserted"] = False

    _write_manifest(manifest)
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest the policy corpus into the retrieval index.")
    ap.add_argument("--corpus-dir", default=None, help="override CORPUS_DIR")
    ap.add_argument("--dry-run", action="store_true", help="chunk + embed + manifest, no Qdrant")
    ap.add_argument("--backend", default=None, help="embed backend override: sentence-transformers | hash")
    args = ap.parse_args()

    m = ingest(args.corpus_dir, dry_run=args.dry_run, backend=args.backend)
    print(json.dumps(m, indent=2, ensure_ascii=False))
    print(
        f"\n[ingest] {m['n_chunks']} chunks from {m['n_docs']} docs "
        f"-> versions {m['versions']} (backend={m['backend']}); "
        f"manifest at {settings.ingest_manifest_path}"
    )


if __name__ == "__main__":
    main()
