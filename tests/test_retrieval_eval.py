"""Retrieval PR3 tests: metric correctness + end-to-end eval over the golden set.

The metric functions are checked against hand-computed values; the end-to-end run uses
the deterministic lexical backend so the numbers are reproducible (the property the PR5
CI eval gate relies on).
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from retrieval.backends import LexicalBackend
from retrieval.eval import (
    evaluate, load_golden, mrr, ndcg_at_k, precision_at_k, recall_at_k,
)
from retrieval.rerank import LexicalReranker
from retrieval.retriever import Retriever

REPO = Path(__file__).resolve().parent.parent
CORPUS = str(REPO / "data" / "policies")


# ---- metric functions ----------------------------------------------------------

def test_precision_recall():
    assert precision_at_k(["a", "b", "c"], {"a", "c"}, 3) == pytest.approx(2 / 3)
    assert recall_at_k(["a", "x", "y"], {"a", "b"}, 3) == pytest.approx(0.5)
    assert recall_at_k(["x"], set(), 3) == 0.0  # no relevant -> 0, no ZeroDivision


def test_mrr():
    assert mrr(["x", "a", "y"], {"a"}) == pytest.approx(0.5)
    assert mrr(["a"], {"a"}) == 1.0
    assert mrr(["x", "y"], {"a"}) == 0.0


def test_ndcg():
    assert ndcg_at_k(["a", "x"], {"a"}, 2) == pytest.approx(1.0)               # relevant first -> ideal
    assert ndcg_at_k(["x", "a"], {"a"}, 2) == pytest.approx(1 / math.log2(3))  # relevant second
    assert ndcg_at_k(["x", "y"], {"a"}, 2) == 0.0


# ---- end-to-end ----------------------------------------------------------------

def _lexical_retriever() -> Retriever:
    return Retriever(backend=LexicalBackend.from_corpus(CORPUS), reranker=LexicalReranker())


def test_golden_set_loads_and_matches_corpus():
    golden = load_golden(str(REPO / "data" / "eval" / "golden_set.jsonl"))
    assert len(golden) >= 10
    # every referenced clause id must actually exist in the corpus
    from retrieval.ingest import load_and_chunk
    corpus_ids = {c.clause_id for c in load_and_chunk(CORPUS)}
    for ex in golden:
        for cid in ex["relevant_clause_ids"]:
            assert cid in corpus_ids, f"golden set references missing clause {cid!r}"


def test_eval_quality_on_golden_set():
    """A floor for the *lexical* backend, which is the only one that runs offline.

    The golden set is deliberately adversarial — most queries use caller wording rather
    than clause wording, and the corpus carries near-miss distractors — so BM25 scores
    around MRR 0.31 on it, not the 1.0 the previous one-query-per-clause set produced.
    A saturated metric cannot detect a regression, so the low number is the point.

    These thresholds only catch a hard break (a broken tokenizer, an empty index). The
    real quality bar is the dense stack, enforced by the CI eval gate against a committed
    baseline; it needs a model download and so cannot live in the offline suite.
    """
    golden = load_golden(str(REPO / "data" / "eval" / "golden_set.jsonl"))
    report = evaluate(golden, retriever=_lexical_retriever(), k=5)
    assert report.n == len(golden)
    assert report.metrics["mrr"] >= 0.25
    assert report.metrics["recall@5"] >= 0.30
    assert report.metrics["ndcg@5"] >= 0.25


def test_eval_is_reproducible():
    golden = load_golden(str(REPO / "data" / "eval" / "golden_set.jsonl"))
    a = evaluate(golden, retriever=_lexical_retriever(), k=5).metrics
    b = evaluate(golden, retriever=_lexical_retriever(), k=5).metrics
    assert a == b, "deterministic backend must give identical metrics across runs"
