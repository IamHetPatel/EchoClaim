"""Zero-downtime embedding-model migration.

Changing the embedding model is the migration everyone gets wrong, because old and new
vectors are not comparable. Re-embedding in place means search is broken for the duration;
a fresh collection means a flag-day cutover with no way back.

Named vectors avoid both. One point carries ``emb_v1`` and ``emb_v2`` side by side, so the
new model can be built up while the old one keeps serving, and switching is a pointer
flip rather than a data move.

Six phases::

    1. introduce   add the new named vector to the collection
    2. dual-write  new ingests write both  (set DUAL_WRITE_EMBED_VERSION=emb_v2)
    3. backfill    re-embed existing points into emb_v2; resumable, idempotent
    4. shadow-eval score both versions on the golden set; gate on non-inferiority
    5. cutover     flip the active pointer; reads now serve emb_v2
    6. rollback    flip it back; emb_v1 was never deleted

Reads never stop at any point. Phases 1-4 do not touch what reads serve; phase 5 is a
single metadata write; phase 6 is the same write in reverse.

Run::

    python -m retrieval.migrate status
    python -m retrieval.migrate introduce   --to emb_v2
    python -m retrieval.migrate backfill    --to emb_v2
    python -m retrieval.migrate shadow-eval --to emb_v2      # exit 1 => do not cut over
    python -m retrieval.migrate cutover     --to emb_v2
    python -m retrieval.migrate rollback    --to emb_v1
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from .config import settings
from .embedder import get_embedder
from .eval import evaluate, load_golden
from .index import QdrantIndex


# ---- helpers -------------------------------------------------------------------

def _retriever_for(version: str):
    """A retriever pinned to one named vector, regardless of which one is active."""
    from .backends import QdrantBackend
    from .rerank import get_reranker
    from .retriever import Retriever

    return Retriever(backend=QdrantBackend(version=version), reranker=get_reranker())


def _vector_coverage(idx: QdrantIndex, version: str) -> tuple[int, int]:
    """(points carrying this named vector, total points). Drives backfill progress."""
    total = with_vec = 0
    offset = None
    while True:
        # Payload is needed to recognise the metadata point; without it the meta row is
        # counted as corpus and coverage can never reach 100%, which would block cutover.
        points, offset = idx.client.scroll(
            idx.collection, limit=256, offset=offset, with_payload=True, with_vectors=True
        )
        if not points:
            break
        for p in points:
            if p.payload is not None and p.payload.get("_index_meta"):
                continue  # the metadata point is not corpus content
            total += 1
            vec = p.vector or {}
            if isinstance(vec, dict) and vec.get(version) is not None:
                with_vec += 1
        if offset is None:
            break
    return with_vec, total


# ---- phases --------------------------------------------------------------------

def status() -> dict:
    idx = QdrantIndex()
    active = idx.get_active_version()
    info = idx.client.get_collection(idx.collection)
    present = list(info.config.params.vectors.keys())
    out = {
        "collection": idx.collection,
        "active_version": active,
        "named_vectors_present": present,
        "dual_write_version": settings.dual_write_version,
        "registered_versions": {
            n: {"model_id": v.model_id, "dim": v.dim} for n, v in settings.versions.items()
        },
        "coverage": {v: dict(zip(("with_vector", "total"), _vector_coverage(idx, v)))
                     for v in present},
    }
    print(json.dumps(out, indent=2))
    return out


def introduce(to_version: str) -> None:
    """Phase 1. Add the new named vector. Reads are untouched."""
    version = settings.version(to_version)
    idx = QdrantIndex()
    idx.add_vector_version([to_version])
    print(f"[introduce] {to_version} ({version.model_id}, {version.dim}d) present on "
          f"{idx.collection}; active version is still {idx.get_active_version()}.")
    print(f"[introduce] next: export DUAL_WRITE_EMBED_VERSION={to_version} so new ingests "
          f"write both, then run backfill.")


def backfill(to_version: str, *, batch: int = 64, resume_from: str | None = None) -> int:
    """Phase 3. Re-embed stored points into the new named vector.

    Idempotent and resumable: text comes back out of the payload, point ids never change,
    and the embedder's content-hash cache makes a re-run nearly free. A crash loses at
    most one batch -- rerun the same command and it converges.
    """
    idx = QdrantIndex()
    emb = get_embedder(settings.version(to_version))
    from qdrant_client import models

    offset, done, t0 = resume_from, 0, time.perf_counter()
    while True:
        points, offset = idx.client.scroll(
            idx.collection, limit=batch, offset=offset, with_payload=True, with_vectors=False
        )
        if not points:
            break
        corpus = [p for p in points if not (p.payload or {}).get("_index_meta")]
        if corpus:
            vecs = emb.encode([(p.payload or {}).get("text", "") for p in corpus])
            idx.client.update_vectors(
                idx.collection,
                points=[models.PointVectors(id=p.id, vector={to_version: vecs[i].tolist()})
                        for i, p in enumerate(corpus)],
            )
            done += len(corpus)
            print(f"[backfill] {done} points -> {to_version}; resume offset={offset}", flush=True)
        if offset is None:
            break
    with_vec, total = _vector_coverage(idx, to_version)
    print(f"[backfill] complete: {done} embedded in {time.perf_counter() - t0:.1f}s; "
          f"coverage {with_vec}/{total}")
    return done


def shadow_eval(to_version: str, *, tolerance: float = 0.01, k: int | None = None) -> bool:
    """Phase 4. The gate. Score both versions on the golden set; block if the candidate
    is worse by more than ``tolerance``.

    This is the phase that makes the migration safe rather than merely reversible. The
    candidate is queried live, against real stored vectors, while the incumbent keeps
    serving traffic -- so the comparison reflects what users would actually get.
    """
    idx = QdrantIndex()
    active = idx.get_active_version()
    golden = load_golden()
    k = k or settings.eval_k

    base = evaluate(golden, retriever=_retriever_for(active), k=k).metrics
    cand = evaluate(golden, retriever=_retriever_for(to_version), k=k).metrics

    print(f"\n{'metric':14}{active:>14}{to_version:>14}{'delta':>10}")
    print("-" * 52)
    ok = True
    for m in (f"ndcg@{k}", "mrr", f"recall@{k}", f"precision@{k}"):
        b, c = base[m], cand[m]
        print(f"{m:14}{b:>14.4f}{c:>14.4f}{c - b:>+10.4f}")
        # Gate on the ranking-quality metrics; precision@k has a low ceiling here and
        # moves with the number of relevant clauses, so it is reported, not gated.
        if m in (f"ndcg@{k}", "mrr") and c < b - tolerance:
            ok = False
    print("-" * 52)
    verdict = "PASS" if ok else "FAIL"
    print(f"[shadow-eval] {verdict}: {to_version} is "
          f"{'non-inferior to' if ok else 'WORSE than'} {active} "
          f"(tolerance {tolerance} on ndcg/mrr)")
    if not ok:
        print(f"[shadow-eval] do NOT cut over. {active} keeps serving; nothing has changed.")
    return ok


def cutover(to_version: str, *, force: bool = False) -> None:
    """Phase 5. Flip the pointer. One metadata write; no vectors move."""
    idx = QdrantIndex()
    previous = idx.get_active_version()
    with_vec, total = _vector_coverage(idx, to_version)
    if with_vec < total and not force:
        raise SystemExit(
            f"[cutover] refusing: {to_version} covers {with_vec}/{total} points. "
            f"Finish the backfill, or pass --force to accept partial coverage."
        )
    idx.set_active_version(to_version)
    print(f"[cutover] active version {previous} -> {to_version}. Reads now serve "
          f"{settings.version(to_version).model_id}.")
    print(f"[cutover] {previous} is still stored; roll back with: "
          f"python -m retrieval.migrate rollback --to {previous}")


def rollback(to_version: str) -> None:
    """Phase 6. The same pointer flip, backwards. Instant, because nothing was deleted."""
    idx = QdrantIndex()
    previous = idx.get_active_version()
    idx.set_active_version(to_version)
    print(f"[rollback] active version {previous} -> {to_version}.")


# ---- cli -----------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Zero-downtime embedding migration")
    ap.add_argument("phase", choices=["status", "introduce", "backfill", "shadow-eval",
                                      "cutover", "rollback"])
    ap.add_argument("--to", default=None, help="target version, e.g. emb_v2")
    ap.add_argument("--tolerance", type=float, default=0.01)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--resume-from", default=None)
    ap.add_argument("--force", action="store_true", help="cutover despite partial coverage")
    args = ap.parse_args()

    if args.phase == "status":
        status()
        return
    if not args.to:
        ap.error(f"--to is required for '{args.phase}'")
    if args.to not in settings.versions:
        ap.error(f"unknown version {args.to!r}; registered: {list(settings.versions)}")

    if args.phase == "introduce":
        introduce(args.to)
    elif args.phase == "backfill":
        backfill(args.to, batch=args.batch, resume_from=args.resume_from)
    elif args.phase == "shadow-eval":
        sys.exit(0 if shadow_eval(args.to, tolerance=args.tolerance) else 1)
    elif args.phase == "cutover":
        cutover(args.to, force=args.force)
    elif args.phase == "rollback":
        rollback(args.to)


if __name__ == "__main__":
    main()
