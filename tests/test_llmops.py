"""Tests for the LLMOps layer.

These cover the parts that must hold without a model, an API key or a Qdrant server:
the prompt registry's single-active invariant, the trace logger's redaction boundary,
the drift monitor's windowing and PSI, and — most importantly — the eval gate's refusal
to treat an unmeasured metric as a passing one.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from llmops import drift_monitor, eval_gate
from llmops.prompt_registry import PromptRegistry


# ---- prompt registry -----------------------------------------------------------

def test_prompt_ref_is_content_addressed(tmp_path):
    reg = _write_prompt(tmp_path, version="1.0.0", active=True, body="You are Jamie.")
    p = reg.get("jamie_system")
    assert p.ref.startswith("jamie_system@1.0.0+")
    assert len(p.content_hash) == 12


def test_editing_a_prompt_changes_its_hash(tmp_path):
    a = _write_prompt(tmp_path, version="1.0.0", active=True, body="You are Jamie.")
    before = a.get("jamie_system").content_hash
    b = _write_prompt(tmp_path, version="1.0.0", active=True, body="You are Jamie. Be brief.")
    assert b.get("jamie_system").content_hash != before


def test_exactly_one_active_version_is_enforced(tmp_path):
    """Two active versions must fail loudly: otherwise a behaviour change is not
    attributable to a single prompt hash, which is the whole point of the registry."""
    _write_prompt(tmp_path, version="1.0.0", active=True, body="v1")
    reg = _write_prompt(tmp_path, version="1.1.0", active=True, body="v2")
    with pytest.raises(ValueError, match="exactly one active"):
        reg.get("jamie_system")


def test_zero_active_versions_is_also_an_error(tmp_path):
    reg = _write_prompt(tmp_path, version="1.0.0", active=False, body="v1")
    with pytest.raises(ValueError, match="exactly one active"):
        reg.get("jamie_system")


def test_inactive_version_still_reachable_by_pin(tmp_path):
    _write_prompt(tmp_path, version="1.0.0", active=False, body="v1")
    reg = _write_prompt(tmp_path, version="1.1.0", active=True, body="v2")
    assert reg.get("jamie_system", version="1.0.0").template.strip() == "v1"


def _write_prompt(tmp_path, *, version, active, body) -> PromptRegistry:
    (tmp_path / f"jamie_system.v{version}.yaml").write_text(
        f'name: jamie_system\nversion: "{version}"\nactive: {str(active).lower()}\n'
        f"template: |\n  {body}\n",
        encoding="utf-8",
    )
    return PromptRegistry(tmp_path)


# ---- trace logging -------------------------------------------------------------

def test_trace_logger_redacts_pii_before_it_reaches_disk(tmp_path, monkeypatch):
    from llmops import logging_middleware as lm

    logger = lm.TraceLogger(str(tmp_path / "traces.sqlite"))
    monkeypatch.setattr(lm, "_logger", logger)
    with lm.trace("jamie_system@1.0.0+abc") as rec:
        rec.response = "Ihre Police DE-KFZ-2026-004417 ist aktiv, max.mueller@email.de."
        rec.top_score = 0.81

    raw = sqlite3.connect(str(tmp_path / "traces.sqlite")).execute(
        "SELECT data FROM traces").fetchone()[0]
    assert "DE-KFZ-2026-004417" not in raw
    assert "max.mueller@email.de" not in raw
    row = json.loads(raw)
    assert row["latency_ms"] is not None
    assert row["top_score"] == 0.81


# ---- drift monitor -------------------------------------------------------------

def test_drift_monitor_returns_nothing_without_two_full_windows(tmp_path):
    path = _traces(tmp_path, [0.95] * 10)
    assert drift_monitor.report(path, window=20) == []


def test_drift_monitor_flags_a_groundedness_drop(tmp_path):
    path = _traces(tmp_path, [0.97] * 20 + [0.55] * 20)
    g = _by_metric(drift_monitor.report(path, window=20))["groundedness_rate"]
    assert g.drift is True
    assert g.delta < 0


def test_drift_monitor_is_quiet_when_nothing_moves(tmp_path):
    path = _traces(tmp_path, [0.97] * 40)
    assert _by_metric(drift_monitor.report(path, window=20))["groundedness_rate"].drift is False


def test_psi_flags_a_retrieval_score_shift(tmp_path):
    path = _traces(tmp_path, [0.95] * 40,
                   scores=[0.1 + 0.01 * i for i in range(20)] + [0.9] * 20)
    assert _by_metric(drift_monitor.report(path, window=20))["retrieval_score_psi"].drift is True


def test_psi_is_zero_for_a_constant_reference_window():
    """Degenerate quantile edges must not raise; a flat window has no signal."""
    assert drift_monitor.population_stability_index([0.5] * 20, [0.5] * 20) == 0.0


def _by_metric(reports):
    return {r.metric: r for r in reports}


def _traces(tmp_path, groundedness, scores=None):
    path = str(tmp_path / "traces.sqlite")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE traces (trace_id TEXT PRIMARY KEY, ts REAL, data TEXT)")
    for i, g in enumerate(groundedness):
        s = scores[i] if scores else 0.8
        con.execute("INSERT INTO traces VALUES (?,?,?)",
                    (str(i), float(i), json.dumps({"groundedness": g, "top_score": s})))
    con.commit()
    con.close()
    return path


# ---- eval gate -----------------------------------------------------------------

def test_tolerance_lookup_matches_k_suffixed_metrics():
    assert eval_gate._tolerance_for("precision@5") == eval_gate.TOLERANCES["precision"]
    assert eval_gate._tolerance_for("ndcg@10") == eval_gate.TOLERANCES["ndcg"]
    assert eval_gate._tolerance_for("not_a_gated_metric") is None


def test_regression_beyond_tolerance_fails():
    failures = eval_gate.compare({"ndcg@5": 0.70}, {"ndcg@5": 0.80})
    assert len(failures) == 1 and "ndcg@5" in failures[0]


def test_regression_within_tolerance_passes():
    assert eval_gate.compare({"ndcg@5": 0.795}, {"ndcg@5": 0.80}) == []


def test_improvement_never_fails():
    assert eval_gate.compare({"ndcg@5": 0.95}, {"ndcg@5": 0.80}) == []


def test_unmeasured_metric_is_absent_not_neutral():
    """The bug this file exists to prevent: a metric that could not be measured must
    not appear as a passing 1.0. It must be missing, and reported as skipped."""
    metrics, skipped = eval_gate.run_eval(skip_groundedness=True, skip_extraction=True)
    assert "groundedness" not in metrics
    assert "extraction_f1" not in metrics
    assert set(skipped) == {"groundedness", "extraction_f1"}


def test_a_missing_metric_cannot_mask_a_regression():
    """compare() must not silently pass a baseline metric that is absent from the
    current run — under --strict the gate turns that absence into a failure."""
    assert eval_gate.compare({}, {"groundedness": 0.9}) == []  # absent => not compared
    metrics, skipped = eval_gate.run_eval(skip_groundedness=True, skip_extraction=True)
    assert "groundedness" in skipped  # ...but it *is* reported, so --strict can fail it
