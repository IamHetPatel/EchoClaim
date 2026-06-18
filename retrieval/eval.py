"""Retrieval-quality evaluation: precision@k, recall@k, MRR, nDCG@k.

Runs the retriever over a golden set (JSONL of
``{"query", "relevant_clause_ids", "product_code"?, "lang"?}``) and reports ranking
metrics. The golden set is bootstrapped from the corpus clauses, then spot-checked.

Deterministic by construction: the lexical backend and the hash embedder are both
reproducible, so the numbers don't move between runs, which is what lets the PR5 CI
eval gate compare against a baseline. Run::

    python -m retrieval.eval                 # table over the default golden set
    python -m retrieval.eval --k 3 --json

See echoclaim-spine/BUILD_PLAN.md section 3.6.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .config import settings


def load_golden(path: str | None = None) -> list[dict]:
    p = Path(path or settings.golden_set_path)
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---- metrics (binary relevance) ------------------------------------------------

def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    top = retrieved[:k]
    return sum(1 for r in top if r in relevant) / k


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = retrieved[:k]
    return sum(1 for r in top if r in relevant) / len(relevant)


def mrr(retrieved: list[str], relevant: set[str]) -> float:
    for i, r in enumerate(retrieved, start=1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, r in enumerate(retrieved[:k], start=1) if r in relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


# ---- evaluation ----------------------------------------------------------------

@dataclass
class EvalReport:
    k: int
    n: int
    metrics: dict[str, float]
    per_query: list[dict]

    def pretty(self) -> str:
        lines = [f"Retrieval eval: {self.n} queries @ k={self.k}", "-" * 44]
        for name, val in self.metrics.items():
            lines.append(f"  {name:14} {val:.4f}")
        lines.append("-" * 44)
        for q in self.per_query:
            hit = "✓" if q["hit_rank"] else "·"
            lines.append(f"  {hit} rank={q['hit_rank'] or '-':>2}  {q['query'][:52]}")
        return "\n".join(lines)


def evaluate(golden: list[dict] | None = None, *, retriever=None, k: int | None = None) -> EvalReport:
    """Run the retriever over the golden set and average the ranking metrics."""
    from .retriever import Retriever

    golden = golden if golden is not None else load_golden()
    retriever = retriever or Retriever()
    k = k or settings.eval_k

    agg = {f"precision@{k}": 0.0, f"recall@{k}": 0.0, "mrr": 0.0, f"ndcg@{k}": 0.0}
    per_query: list[dict] = []
    for ex in golden:
        relevant = set(ex["relevant_clause_ids"])
        res = retriever.retrieve(
            ex["query"], product_code=ex.get("product_code"), lang=ex.get("lang", "de")
        )
        ids = [c.clause_id for c in res.chunks]
        p = precision_at_k(ids, relevant, k)
        r = recall_at_k(ids, relevant, k)
        m = mrr(ids, relevant)
        n = ndcg_at_k(ids, relevant, k)
        agg[f"precision@{k}"] += p
        agg[f"recall@{k}"] += r
        agg["mrr"] += m
        agg[f"ndcg@{k}"] += n
        hit_rank = next((i for i, cid in enumerate(ids, start=1) if cid in relevant), 0)
        per_query.append({"query": ex["query"], "hit_rank": hit_rank, "top": ids[:k]})

    n_q = len(golden) or 1
    metrics = {name: round(v / n_q, 4) for name, v in agg.items()}
    return EvalReport(k=k, n=len(golden), metrics=metrics, per_query=per_query)


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate retrieval quality over a golden set.")
    ap.add_argument("--golden", default=None, help="override GOLDEN_SET_PATH")
    ap.add_argument("--k", type=int, default=None, help="cutoff k (default EVAL_K)")
    ap.add_argument("--json", action="store_true", help="emit metrics as JSON")
    args = ap.parse_args()

    report = evaluate(load_golden(args.golden), k=args.k)
    if args.json:
        print(json.dumps({"k": report.k, "n": report.n, "metrics": report.metrics}, indent=2))
    else:
        print(report.pretty())


if __name__ == "__main__":
    main()
