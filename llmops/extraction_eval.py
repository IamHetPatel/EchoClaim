"""Extraction F1 for the CI gate.

Reuses ``extraction.benchmark`` rather than reimplementing scoring, so the number the
gate blocks on is the same number the benchmark table reports. The gate scores the
extractor that actually serves the live path (GLiNER2, loaded from
``extraction.gliner2_service``), not the highest-F1 model in the benchmark — a gate
should watch the thing in production.

Raises ``ExtractionUnavailable`` when the model cannot be loaded, so the gate can skip
the metric explicitly instead of substituting a passing score.
"""
from __future__ import annotations

import argparse
import json


class ExtractionUnavailable(RuntimeError):
    """The extractor could not be loaded; the metric is unmeasurable, not passing."""


def extraction_f1() -> float:
    """Mean label-level F1 of the live extractor over the benchmark eval set."""
    try:
        from extraction.benchmark import EVAL_DATA, _f1
        from extraction.gliner2_service import ExtractionService
    except Exception as e:
        raise ExtractionUnavailable(f"cannot import extraction stack: {e}") from e

    try:
        svc = ExtractionService()
    except Exception as e:
        raise ExtractionUnavailable(f"cannot load extraction model: {e}") from e

    scores = []
    for ex in EVAL_DATA:
        out = svc.extract(ex["text"])
        merged = {**out["pillars"], **out["fraud"]}
        scores.append(_f1({k: v["text"] for k, v in merged.items()}, ex["gold"]))
    return round(sum(scores) / (len(scores) or 1), 4)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    f1 = extraction_f1()
    print(json.dumps({"extraction_f1": f1}) if args.json else f"extraction_f1 {f1:.4f}")


if __name__ == "__main__":
    main()
