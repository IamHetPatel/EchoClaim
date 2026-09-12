"""CI eval gate — the thing that makes this 'CI/CD for LLMs'.

On any change to prompts, model config, retrieval or extraction, CI runs this. It
computes the gated metrics and FAILS (nonzero exit) if any regresses past its tolerance
band versus the committed baseline. Gating is on probabilistic metrics and an LLM judge,
not exact-match asserts — that is the difference from classic ML CI.

Four gated metrics, all measured, none stubbed:

===================  =====================================================
``precision@k``      retrieval: right clause in the top k        (retrieval.eval)
``ndcg@k``           retrieval: right clause ranked high         (retrieval.eval)
``groundedness``     answer follows from cited clauses           (llmops.groundedness)
``extraction_f1``    live extractor over the benchmark set       (llmops.extraction_eval)
===================  =====================================================

Determinism: retrieval is reproducible by construction (fixed index, deterministic
rerank), and both model calls run at temperature 0. Re-running on unchanged inputs
reproduces the numbers, which is what makes tolerance bands meaningful rather than a
retry-until-green lottery.

**Unmeasurable is not passing.** If the judge has no API key or the extractor will not
load, that metric is reported as ``null`` and excluded from the comparison, and the run
prints why. Under ``--strict`` (how CI runs it) an unmeasurable gated metric fails the
build outright. The one thing this file must never do is substitute a neutral 1.0 for a
metric it did not measure — that is a gate that always passes.

Usage::

    python -m llmops.eval_gate                      # compare against baseline
    python -m llmops.eval_gate --strict             # CI: unmeasurable => failure
    python -m llmops.eval_gate --update-baseline    # after an intended improvement
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_BASELINE = "data/eval/baseline.json"

# Regressions larger than these (absolute) fail the build. Retrieval metrics are
# deterministic so they get tight bands; the judge is a sampled LLM score, so it gets a
# wider one.
TOLERANCES = {
    "precision": 0.02,
    "ndcg": 0.02,
    "groundedness": 0.05,
    "extraction_f1": 0.02,
}


def _tolerance_for(metric: str) -> float | None:
    """Map a concrete metric name (``precision@5``) to its tolerance band."""
    base = metric.split("@", 1)[0]
    return TOLERANCES.get(base)


def run_eval(golden_path: str | None = None, *, sample: int | None = None,
             skip_groundedness: bool = False, skip_extraction: bool = False) -> tuple[dict, dict]:
    """Compute the gated metrics.

    Returns ``(metrics, skipped)`` where ``skipped`` maps a metric name to the reason it
    could not be measured. Skipped metrics are absent from ``metrics`` — never present
    with a filler value.
    """
    from retrieval.eval import evaluate, load_golden
    from retrieval.retriever import Retriever

    golden = load_golden(golden_path)

    # Cross-encoder reranking dominates runtime (~28 s/query on CPU). The ranking metrics
    # and the groundedness harness ask for the same retrievals, so do them once.
    cache: dict[str, object] = {}

    class _Memoizing:
        def __init__(self, inner):
            self._inner = inner

        def retrieve(self, query, **kw):
            if query not in cache:
                cache[query] = self._inner.retrieve(query, **kw)
            return cache[query]

    retriever = _Memoizing(Retriever())
    report = evaluate(golden, retriever=retriever)
    k = report.k
    metrics: dict[str, float] = {
        f"precision@{k}": report.metrics[f"precision@{k}"],
        f"ndcg@{k}": report.metrics[f"ndcg@{k}"],
    }
    skipped: dict[str, str] = {}

    if skip_groundedness:
        skipped["groundedness"] = "explicitly skipped (--skip-groundedness)"
    else:
        try:
            from .groundedness import evaluate_groundedness
            g, _f, _rows = evaluate_groundedness(golden, sample=sample, retrievals=cache)
            metrics["groundedness"] = g
        except Exception as e:
            skipped["groundedness"] = f"{type(e).__name__}: {e}"

    if skip_extraction:
        skipped["extraction_f1"] = "explicitly skipped (--skip-extraction)"
    else:
        try:
            from .extraction_eval import extraction_f1
            metrics["extraction_f1"] = extraction_f1()
        except Exception as e:
            skipped["extraction_f1"] = f"{type(e).__name__}: {e}"

    return metrics, skipped


def provenance() -> dict:
    """What the numbers depend on, recorded alongside them.

    A groundedness score is only comparable against a baseline produced by the *same*
    judge; llama3.2:3b and Gemini Flash do not agree on a scale. The retrieval metrics
    likewise depend on the embedder and reranker. Storing this with the baseline lets the
    gate refuse a comparison that would be meaningless instead of reporting a phantom
    regression.
    """
    import hashlib
    from pathlib import Path as _P

    from retrieval.config import settings
    from . import judge as _judge

    golden = _P(settings.golden_set_path)
    return {
        "judge_backend": _judge.backend_name(),
        "judge_model": os.getenv("JUDGE_MODEL", "<default>"),
        "embed_backend": settings.embed_backend,
        "rerank_backend": os.getenv("RERANK_BACKEND", "auto"),
        "retrieval_backend": os.getenv("RETRIEVAL_BACKEND", "auto"),
        "active_version": settings.active_version,
        "eval_k": settings.eval_k,
        "golden_set_sha256": (
            hashlib.sha256(golden.read_bytes()).hexdigest()[:16] if golden.exists() else None
        ),
    }


# Metrics whose value is only meaningful under the judge that produced it.
_JUDGE_DEPENDENT = {"groundedness"}


def provenance_mismatches(current: dict, baseline_meta: dict) -> list[str]:
    """Provenance differences that make a metric comparison invalid."""
    out = []
    for key in ("judge_backend", "judge_model", "embed_backend", "rerank_backend",
                "active_version", "eval_k", "golden_set_sha256"):
        if key in baseline_meta and baseline_meta[key] != current.get(key):
            out.append(f"{key}: now {current.get(key)!r}, baseline {baseline_meta[key]!r}")
    return out


def compare(current: dict, baseline: dict) -> list[str]:
    failures = []
    for metric, value in current.items():
        tol = _tolerance_for(metric)
        if tol is None or metric not in baseline:
            continue
        drop = baseline[metric] - value
        if drop > tol:
            failures.append(
                f"{metric}: {value:.4f} vs baseline {baseline[metric]:.4f} "
                f"(drop {drop:.4f} > tolerance {tol})"
            )
    return failures


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    ap.add_argument("--golden", default=None, help="defaults to settings.golden_set_path")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="a gated metric that could not be measured fails the build")
    ap.add_argument("--sample", type=int, default=None,
                    help="limit groundedness to the first N queries")
    ap.add_argument("--skip-groundedness", action="store_true")
    ap.add_argument("--skip-extraction", action="store_true")
    args = ap.parse_args()

    current, skipped = run_eval(
        args.golden, sample=args.sample,
        skip_groundedness=args.skip_groundedness, skip_extraction=args.skip_extraction,
    )
    print("current:", json.dumps(current, indent=2))
    for metric, reason in skipped.items():
        print(f"  ! {metric} NOT MEASURED -> {reason}")

    if args.update_baseline:
        if skipped and args.strict:
            print("\nrefusing to write a baseline with unmeasured metrics under --strict")
            sys.exit(2)
        Path(args.baseline).parent.mkdir(parents=True, exist_ok=True)
        doc = {"metrics": current, "provenance": provenance()}
        Path(args.baseline).write_text(json.dumps(doc, indent=2) + "\n")
        print(f"baseline updated -> {args.baseline}")
        return

    if not Path(args.baseline).exists():
        print(f"\nno baseline at {args.baseline}; create one with --update-baseline")
        sys.exit(2)

    doc = json.loads(Path(args.baseline).read_text())
    baseline = doc.get("metrics", doc)          # tolerate a pre-provenance baseline
    baseline_meta = doc.get("provenance", {})

    drift = provenance_mismatches(provenance(), baseline_meta)
    if drift:
        print("\n  ! baseline provenance differs from this run:")
        for d in drift:
            print("    -", d)

    # A judge-dependent metric cannot be compared across judges: llama3.2 and Gemini do
    # not share a scale, so the delta would measure the judge, not the system.
    judge_changed = any(d.startswith(("judge_backend", "judge_model")) for d in drift)
    if judge_changed:
        for m in _JUDGE_DEPENDENT & set(current):
            print(f"    -> not gating {m}: baseline was scored by a different judge")
            current.pop(m)

    failures = compare(current, baseline)

    if args.strict:
        for metric in TOLERANCES:
            missing = [m for m in baseline if m.split("@", 1)[0] == metric and m not in current]
            for m in missing:
                failures.append(f"{m}: not measured ({skipped.get(metric, 'unknown reason')})")

    if failures:
        print("\nEVAL GATE FAILED:")
        for f in failures:
            print("  -", f)
        sys.exit(1)

    note = f" ({len(skipped)} metric(s) not measured)" if skipped else ""
    print(f"\nEVAL GATE PASSED{note}")


if __name__ == "__main__":
    main()
