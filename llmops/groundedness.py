"""End-to-end groundedness: retrieve -> answer -> judge.

This closes the loop the retrieval metrics cannot. precision@k tells you the right
clause was *retrieved*; it says nothing about whether the answer the caller hears
actually follows from it. Groundedness measures that second hop.

Flow, per golden query:

1. ``Retriever`` recalls and reranks -> citations (clause_id + text).
2. The answerer is asked the question with only those citations in context, at
   temperature 0, and told to decline rather than guess when they do not cover it.
3. ``llmops.judge`` scores the answer against the citations it was given.

Both model calls are temperature 0, so re-running on an unchanged index and unchanged
prompt reproduces the same score. That is what makes the number gate-able.

Run standalone::

    python -m llmops.groundedness --sample 8
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, asdict

from .judge import JudgeUnavailable, complete, judge

_ANSWER_SYSTEM = """You are a German motor-insurance claims assistant.
Answer the caller's question using ONLY the numbered clauses provided.
Cite the clause id you relied on, in square brackets.
If the clauses do not answer the question, say a specialist will confirm — do not guess.
Answer in German, in at most three sentences."""

@dataclass
class GroundednessRow:
    query: str
    answer: str
    citations: list[str]
    groundedness: float
    faithfulness: float
    rationale: str


def _answer(question: str, citations: list[str]) -> str:
    """Generate the answer under test, on the same backend and temperature as the judge."""
    context = "\n".join(f"{i}. {c}" for i, c in enumerate(citations, start=1))
    return complete(f"Klauseln:\n{context}\n\nFrage: {question}", system=_ANSWER_SYSTEM).strip()


def evaluate_groundedness(
    golden: list[dict] | None = None,
    *,
    retriever=None,
    sample: int | None = None,
    retrievals: dict[str, object] | None = None,
) -> tuple[float, float, list[GroundednessRow]]:
    """Return (mean_groundedness, mean_faithfulness, rows).

    Raises ``JudgeUnavailable`` if the judge or answerer cannot run — the caller must
    decide what an unmeasurable metric means, rather than getting a fake 1.0.
    """
    from retrieval.eval import load_golden
    from retrieval.retriever import Retriever

    golden = golden if golden is not None else load_golden()
    if sample:
        golden = golden[:sample]

    rows: list[GroundednessRow] = []
    for ex in golden:
        res = (retrievals or {}).get(ex["query"])
        if res is None:
            retriever = retriever or Retriever()
            res = retriever.retrieve(
                ex["query"], product_code=ex.get("product_code"), lang=ex.get("lang", "de")
            )
        citations = [c.cite() for c in res.chunks]
        answer = _answer(ex["query"], citations)
        scores = judge(answer, citations)
        rows.append(GroundednessRow(
            query=ex["query"], answer=answer, citations=[c.clause_id for c in res.chunks],
            groundedness=scores.groundedness, faithfulness=scores.faithfulness,
            rationale=scores.rationale,
        ))

    n = len(rows) or 1
    return (
        round(sum(r.groundedness for r in rows) / n, 4),
        round(sum(r.faithfulness for r in rows) / n, 4),
        rows,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=None, help="limit to first N queries")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    g, f, rows = evaluate_groundedness(sample=args.sample)
    if args.json:
        print(json.dumps({"groundedness": g, "faithfulness": f,
                          "rows": [asdict(r) for r in rows]}, ensure_ascii=False, indent=2))
        return
    print(f"groundedness {g:.4f}   faithfulness {f:.4f}   over {len(rows)} queries")
    for r in rows:
        print(f"  {r.groundedness:.2f}  {r.query[:56]}")


if __name__ == "__main__":
    main()
