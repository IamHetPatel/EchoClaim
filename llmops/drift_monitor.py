"""Drift and hallucination monitoring over the logged traces.

Compares a recent window of traces against a reference window on:

* **groundedness rate** — mean judge groundedness. Falls when the model starts
  asserting coverage the retrieved clauses do not support.
* **retrieval score distribution** — population stability index over the top rerank
  score. Moves when the corpus, the index or the embedding version shifts underneath
  the agent, usually *before* groundedness visibly degrades.

This is the half that makes telemetry a learning signal rather than a dashboard: a PSI
shift is an early warning that the next eval-gate run is about to regress.

Run::

    python -m llmops.drift_monitor --window 50
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass


@dataclass
class DriftReport:
    metric: str
    reference: float
    recent: float
    delta: float
    drift: bool

    def line(self) -> str:
        flag = "  <-- DRIFT" if self.drift else ""
        return (f"{self.metric:24} ref={self.reference:.3f} "
                f"recent={self.recent:.3f} delta={self.delta:+.3f}{flag}")


def _load(path: str) -> list[dict]:
    con = sqlite3.connect(path)
    try:
        rows = con.execute("SELECT data FROM traces ORDER BY ts").fetchall()
    finally:
        con.close()
    return [json.loads(r[0]) for r in rows]


def _mean(xs: list) -> float:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def population_stability_index(ref: list[float], rec: list[float], bins: int = 10) -> float:
    """PSI for the retrieval-score distribution. >0.2 => meaningful shift."""
    import numpy as np

    ref = [x for x in ref if x is not None]
    rec = [x for x in rec if x is not None]
    if not ref or not rec:
        return 0.0
    edges = np.quantile(ref, [i / bins for i in range(bins + 1)])
    edges[0], edges[-1] = -np.inf, np.inf
    # Quantile edges collapse when the reference window is near-constant; dedupe so
    # np.histogram does not raise on non-monotonic bins.
    edges = np.unique(edges)
    if len(edges) < 3:
        return 0.0
    ref_h = np.histogram(ref, bins=edges)[0] / len(ref)
    rec_h = np.histogram(rec, bins=edges)[0] / len(rec)
    eps = 1e-6
    return float(np.sum((rec_h - ref_h) * np.log((rec_h + eps) / (ref_h + eps))))


def report(path: str = "logs/traces.sqlite", window: int = 200,
           groundedness_floor: float = 0.9, psi_threshold: float = 0.2) -> list[DriftReport]:
    """Compare the last ``window`` traces against the ``window`` before them.

    Returns ``[]`` when there are fewer than ``2 * window`` traces — there is nothing to
    compare against yet, which is a different condition from "no drift".
    """
    rows = _load(path)
    if len(rows) < 2 * window:
        return []
    ref, rec = rows[-2 * window:-window], rows[-window:]

    g_ref = _mean([r.get("groundedness") for r in ref])
    g_rec = _mean([r.get("groundedness") for r in rec])
    reports = [DriftReport("groundedness_rate", g_ref, g_rec, g_rec - g_ref,
                           drift=(g_rec < groundedness_floor or g_ref - g_rec > 0.05))]

    psi = population_stability_index([r.get("top_score") for r in ref],
                                     [r.get("top_score") for r in rec])
    reports.append(DriftReport("retrieval_score_psi", 0.0, psi, psi, drift=psi > psi_threshold))
    return reports


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="logs/traces.sqlite")
    ap.add_argument("--window", type=int, default=200)
    args = ap.parse_args()
    reports = report(args.path, window=args.window)
    if not reports:
        print(f"not enough traces in {args.path} for a {args.window}-trace window "
              f"(need {2 * args.window})")
        return
    for r in reports:
        print(r.line())


if __name__ == "__main__":
    main()
