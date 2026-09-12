"""Compare recall backends on the same golden set.

The point of a dense multilingual embedder over BM25 is paraphrase robustness: a caller
says "gegen einen Hirsch gefahren" and the clause says "Zusammenstoß mit Haarwild". BM25
has no way to connect those. This script quantifies that gap instead of asserting it.

Run::

    TORCH_DEVICE=cpu python -m retrieval.compare_backends
    python -m retrieval.compare_backends --backends lexical --json
"""
from __future__ import annotations

import argparse
import json
import os
import time


def _run(backend: str, reranker: str, k: int | None) -> dict:
    # Backend selection is read from the environment at construction time, so set it
    # before importing the retriever's factories.
    os.environ["RETRIEVAL_BACKEND"] = backend
    os.environ["RERANK_BACKEND"] = reranker
    from retrieval.backends import default_backend
    from retrieval.eval import evaluate
    from retrieval.rerank import get_reranker
    from retrieval.retriever import Retriever

    r = Retriever(backend=default_backend(), reranker=get_reranker(reranker))
    t0 = time.perf_counter()
    report = evaluate(retriever=r, k=k)
    elapsed = time.perf_counter() - t0
    row = dict(report.metrics)
    row["backend"] = f"{backend} + {reranker}"
    row["hit_rate"] = round(sum(1 for q in report.per_query if q["hit_rank"]) / (report.n or 1), 4)
    row["sec_per_query"] = round(elapsed / (report.n or 1), 3)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backends", nargs="*", default=["lexical", "memory-dense", "qdrant"])
    ap.add_argument("--reranker", default=None, help="force one reranker for all runs")
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = []
    for b in args.backends:
        rr = args.reranker or ("lexical" if b == "lexical" else "cross-encoder")
        try:
            rows.append(_run(b, rr, args.k))
        except Exception as e:
            print(f"[skip] {b}: {type(e).__name__}: {str(e)[:100]}")

    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        return
    metric_keys = [k for k in rows[0] if k not in ("backend", "hit_rate", "sec_per_query")]
    header = f"{'backend':32}" + "".join(f"{m:>13}" for m in metric_keys) + f"{'hit_rate':>10}{'s/query':>9}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['backend']:32}" + "".join(f"{r[m]:>13.4f}" for m in metric_keys)
              + f"{r['hit_rate']:>10.4f}{r['sec_per_query']:>9.3f}")


if __name__ == "__main__":
    main()
