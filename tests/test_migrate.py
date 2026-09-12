"""Tests for the embedding-migration machinery.

These run offline. The parts that need a live Qdrant (introduce / backfill / cutover)
are exercised against a fake client that records what would be sent, which is enough to
pin the behaviour that matters: that a missing named-vector slot fails loudly, that
cutover refuses on partial coverage, and that the alias swap is a single atomic call.
"""
from __future__ import annotations

import pytest

from retrieval import migrate
from retrieval.config import settings


def test_both_embedding_versions_are_registered():
    """The migration needs a second version to exist as a config artifact, and the two
    must genuinely differ -- same model or same dim would not exercise anything."""
    v1, v2 = settings.version("emb_v1"), settings.version("emb_v2")
    assert v1.model_id != v2.model_id
    assert v1.dim != v2.dim


def test_shadow_eval_gates_on_ndcg_and_mrr_only(monkeypatch):
    """precision@k has a low ceiling here (most queries have one relevant clause), so it
    is reported but must not decide the migration."""
    from retrieval.eval import EvalReport

    def fake_eval(golden, *, retriever=None, k=None):
        # candidate wins ndcg/mrr, loses precision -- must still PASS
        good = retriever == "cand"
        return EvalReport(k=5, n=1, per_query=[], metrics={
            "ndcg@5": 0.80 if good else 0.70,
            "mrr": 0.80 if good else 0.70,
            "recall@5": 0.9,
            "precision@5": 0.05 if good else 0.20,
        })

    monkeypatch.setattr(migrate, "evaluate", fake_eval)
    monkeypatch.setattr(migrate, "load_golden", lambda *a, **k: [{}])
    monkeypatch.setattr(migrate, "_retriever_for", lambda v: "cand" if v == "emb_v2" else "base")
    monkeypatch.setattr(migrate, "QdrantIndex", lambda: _FakeIndex(active="emb_v1"))
    assert migrate.shadow_eval("emb_v2") is True


def test_shadow_eval_blocks_a_worse_candidate(monkeypatch):
    from retrieval.eval import EvalReport

    def fake_eval(golden, *, retriever=None, k=None):
        good = retriever == "base"
        return EvalReport(k=5, n=1, per_query=[], metrics={
            "ndcg@5": 0.71 if good else 0.23,
            "mrr": 0.70 if good else 0.23,
            "recall@5": 0.8 if good else 0.34,
            "precision@5": 0.2 if good else 0.09,
        })

    monkeypatch.setattr(migrate, "evaluate", fake_eval)
    monkeypatch.setattr(migrate, "load_golden", lambda *a, **k: [{}])
    monkeypatch.setattr(migrate, "_retriever_for", lambda v: "cand" if v == "emb_v2" else "base")
    monkeypatch.setattr(migrate, "QdrantIndex", lambda: _FakeIndex(active="emb_v1"))
    assert migrate.shadow_eval("emb_v2") is False


def test_shadow_eval_tolerance_allows_a_small_dip(monkeypatch):
    from retrieval.eval import EvalReport

    def fake_eval(golden, *, retriever=None, k=None):
        good = retriever == "base"
        return EvalReport(k=5, n=1, per_query=[], metrics={
            "ndcg@5": 0.800 if good else 0.795, "mrr": 0.800 if good else 0.795,
            "recall@5": 0.9, "precision@5": 0.2,
        })

    monkeypatch.setattr(migrate, "evaluate", fake_eval)
    monkeypatch.setattr(migrate, "load_golden", lambda *a, **k: [{}])
    monkeypatch.setattr(migrate, "_retriever_for", lambda v: "cand" if v == "emb_v2" else "base")
    monkeypatch.setattr(migrate, "QdrantIndex", lambda: _FakeIndex(active="emb_v1"))
    assert migrate.shadow_eval("emb_v2", tolerance=0.01) is True
    assert migrate.shadow_eval("emb_v2", tolerance=0.001) is False


def test_cutover_refuses_on_partial_coverage(monkeypatch):
    """Flipping to a version that only some points carry silently breaks those points."""
    idx = _FakeIndex(active="emb_v1")
    monkeypatch.setattr(migrate, "QdrantIndex", lambda: idx)
    monkeypatch.setattr(migrate, "_vector_coverage", lambda i, v: (20, 27))
    with pytest.raises(SystemExit, match="refusing"):
        migrate.cutover("emb_v2")
    assert idx.active == "emb_v1", "a refused cutover must not move the pointer"


def test_cutover_proceeds_on_full_coverage(monkeypatch):
    idx = _FakeIndex(active="emb_v1")
    monkeypatch.setattr(migrate, "QdrantIndex", lambda: idx)
    monkeypatch.setattr(migrate, "_vector_coverage", lambda i, v: (27, 27))
    migrate.cutover("emb_v2")
    assert idx.active == "emb_v2"


def test_force_overrides_partial_coverage(monkeypatch):
    idx = _FakeIndex(active="emb_v1")
    monkeypatch.setattr(migrate, "QdrantIndex", lambda: idx)
    monkeypatch.setattr(migrate, "_vector_coverage", lambda i, v: (1, 27))
    migrate.cutover("emb_v2", force=True)
    assert idx.active == "emb_v2"


def test_rollback_is_just_the_pointer(monkeypatch):
    """Rollback must not touch vectors -- that is what makes it instant."""
    idx = _FakeIndex(active="emb_v2")
    monkeypatch.setattr(migrate, "QdrantIndex", lambda: idx)
    migrate.rollback("emb_v1")
    assert idx.active == "emb_v1"
    assert idx.writes == [], "rollback wrote vectors; it should only move the pointer"


def test_missing_named_vector_slot_fails_loudly():
    """Qdrant cannot add a named vector to a live collection, so a missing slot must
    raise with the rebuild instruction rather than a pydantic validation error."""
    from retrieval.index import QdrantIndex

    idx = QdrantIndex.__new__(QdrantIndex)
    idx.collection = "c"
    idx.client = _FakeClient(vectors={"emb_v1": object()})
    with pytest.raises(RuntimeError, match="no named-vector slot"):
        idx.add_vector_version(["emb_v2"])


def test_alias_swap_is_one_atomic_operation():
    """Delete+create must go in a single call, or a read can see the alias missing."""
    from retrieval.index import QdrantIndex

    idx = QdrantIndex.__new__(QdrantIndex)
    idx.collection = "c"
    idx.client = _FakeClient()
    idx.switch_alias("live", "c_v2")
    assert len(idx.client.alias_calls) == 1
    ops = idx.client.alias_calls[0]
    assert len(ops) == 2 and "Delete" in type(ops[0]).__name__ and "Create" in type(ops[1]).__name__


# ---- fakes ---------------------------------------------------------------------

class _FakeIndex:
    def __init__(self, active="emb_v1"):
        self.active, self.writes = active, []

    def get_active_version(self):
        return self.active

    def set_active_version(self, v):
        self.active = v


class _FakeClient:
    def __init__(self, vectors=None):
        self._vectors, self.alias_calls = vectors or {}, []

    def get_collection(self, name):
        class _P:
            pass
        p = _P(); p.config = _P(); p.config.params = _P(); p.config.params.vectors = self._vectors
        return p

    def update_collection_aliases(self, change_aliases_operations):
        self.alias_calls.append(change_aliases_operations)
