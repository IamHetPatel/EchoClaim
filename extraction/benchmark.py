"""GLiNER2 vs. Gemini-structured-output benchmark.

This is the artifact we hand the Pioneer/Fastino judges:

    Model              | Latency  | $/call | F1 (15 labels)
    -----------------------------------------------------
    GLiNER2 zero-shot  | ~50ms    | $0.000 | ~0.71
    GLiNER2 fine-tuned | ~50ms    | $0.000 | ~0.89  ← target
    Gemini 3 Flash JSON| ~900ms   | $0.0015| ~0.93

The numbers are filled in by actually running the bench at hackathon time —
the script only needs `GOOGLE_API_KEY` for the Gemini side; GLiNER runs free.

Run:  python extraction/benchmark.py
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from statistics import mean

# Load .env so GOOGLE_API_KEY is available when run as `python -m extraction.benchmark`.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
except Exception:
    pass

from .gliner2_service import ExtractionService, CLAIM_LABELS, FRAUD_LABELS

# tiny in-repo eval set — extend at hackathon time with synthetic data
EVAL_DATA: list[dict] = [
    {
        "text": (
            "Yeah um I was driving the Golf on the A4 near Köln-Ost about, "
            "I think 8 in the morning, it was pouring rain and this guy in a "
            "BMW with plate K-AB 1234 changed lanes without looking. The police "
            "came, the case number is 2026-04-25-7711. I might have whiplash."
        ),
        "gold": {
            "incident_location": "A4 near Köln-Ost",
            "incident_datetime": "8 in the morning",
            "other_party_plate": "K-AB 1234",
            "police_case_number": "2026-04-25-7711",
            "injuries_or_symptoms": "whiplash",
        },
    },
    {
        "text": (
            "Honestly I noticed the dent like three weeks ago but I'm only "
            "reporting it now. I parked it in front of the house, the plate is "
            "B-MM 4421, no other car involved. The car still drives fine."
        ),
        "gold": {
            "delayed_reporting": "three weeks ago",
            "vehicle_drivable": "yes",
        },
    },
    {
        "text": (
            "The other driver — Klaus, he's actually my brother-in-law — admitted "
            "it was his fault at the scene. We didn't call the police. His insurer "
            "is HUK-Coburg, I think."
        ),
        "gold": {
            "fault_admission": "his fault",
            "known_to_other_party": "brother-in-law",
            "other_party_insurer": "HUK-Coburg",
        },
    },
]


def _f1(pred: dict, gold: dict) -> float:
    """Loose label-level F1 — credit if a gold label is present in pred."""
    if not gold:
        return 1.0
    tp = sum(1 for k in gold if k in pred)
    fp = sum(1 for k in pred if k not in gold)
    fn = sum(1 for k in gold if k not in pred)
    if tp == 0:
        return 0.0
    p = tp / (tp + fp)
    r = tp / (tp + fn)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def _bench_gliner_with(svc: ExtractionService, label: str) -> dict:
    f1s, latencies = [], []
    for ex in EVAL_DATA:
        t0 = time.perf_counter()
        out = svc.extract(ex["text"])
        latencies.append((time.perf_counter() - t0) * 1000)
        merged = {**out["pillars"], **out["fraud"]}
        f1s.append(_f1({k: v["text"] for k, v in merged.items()}, ex["gold"]))
    return {
        "name": label,
        "latency_ms": round(mean(latencies), 1),
        "cost_per_call_usd": 0.0,
        "f1": round(mean(f1s), 3),
    }


def bench_gliner() -> dict:
    """Benchmark the default GLiNER (zero-shot from public models)."""
    svc = ExtractionService()
    return _bench_gliner_with(
        svc, f"GLiNER zero-shot ({svc.mode}: {svc.model_name or 'regex-stub'})"
    )


def bench_gliner_finetuned() -> dict | None:
    """Benchmark the fine-tuned model produced by extraction/finetune_gliner.py.

    Returns None if no fine-tuned model has been trained yet — keeps the
    benchmark useful before the Pioneer fine-tune step has been run."""
    repo_root = Path(__file__).resolve().parent.parent
    candidates = [
        repo_root / "models" / "jamie-gliner-v1",
        repo_root / "models" / "jamie-gliner",  # legacy name
    ]
    for path in candidates:
        # GLiNER saves the config as gliner_config.json (not the standard
        # transformers config.json), so check for either.
        if path.exists() and (
            (path / "gliner_config.json").exists()
            or (path / "config.json").exists()
        ):
            svc = ExtractionService(model_name=str(path))
            return _bench_gliner_with(
                svc, f"GLiNER fine-tuned (jamie-fnol → {path.name})"
            )
    return None


def bench_gemini() -> dict | None:
    if not os.environ.get("GOOGLE_API_KEY"):
        return None
    try:
        from google import genai            # type: ignore
        from google.genai import types       # type: ignore
    except Exception:
        return None
    client = genai.Client()
    # Try the rolling alias first, then fall back through pinned versions —
    # same rotation pattern as agent/gemini_client.py.  Free-tier quota tends
    # to hit one model bucket at a time, so rotation usually unsticks us.
    candidates = [
        os.environ.get("GEMINI_MODEL"),
        "gemini-flash-latest",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]
    seen: set[str] = set()
    candidates = [c for c in candidates if c and not (c in seen or seen.add(c))]

    schema_prompt = (
        "Extract these labels (subset only if present) into JSON: "
        + ", ".join(CLAIM_LABELS + FRAUD_LABELS)
        + ".  Return strict JSON, keys = labels, values = literal strings from the text."
    )

    for model in candidates:
        f1s, latencies = [], []
        try:
            for ex in EVAL_DATA:
                t0 = time.perf_counter()
                resp = client.models.generate_content(
                    model=model,
                    contents=[ex["text"]],
                    config=types.GenerateContentConfig(
                        system_instruction=schema_prompt,
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                latencies.append((time.perf_counter() - t0) * 1000)
                try:
                    pred = json.loads(resp.text)
                except Exception:
                    pred = {}
                f1s.append(_f1(pred, ex["gold"]))
        except Exception as e:
            short = str(e).split("\n", 1)[0][:80]
            print(f"  [bench-gemini] {model} failed: {short} — trying next model", flush=True)
            continue
        # Rough cost: 0.50/M input + 3.00/M output (Gemini Flash pricing).
        return {
            "name": f"Gemini structured ({model})",
            "latency_ms": round(mean(latencies), 1),
            "cost_per_call_usd": 0.0015,
            "f1": round(mean(f1s), 3),
        }
    print("  [bench-gemini] all models exhausted (likely free-tier 429) — skipping Gemini row")
    return None


def main() -> None:
    rows = [bench_gliner()]
    ft = bench_gliner_finetuned()
    if ft:
        rows.append(ft)
    g = bench_gemini()
    if g:
        rows.append(g)

    out_path = Path(__file__).parent / "benchmark_results.json"
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    print(f"\n{'Model':40} {'Latency (ms)':>14} {'Cost ($/call)':>14} {'F1':>8}")
    print("-" * 80)
    for r in rows:
        print(f"{r['name']:40} {r['latency_ms']:>14} {r['cost_per_call_usd']:>14.4f} {r['f1']:>8.3f}")
    print(f"\nSaved → {out_path}")


if __name__ == "__main__":
    main()
