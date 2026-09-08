"""LLM-as-judge: groundedness / faithfulness / answer correctness.

Groundedness is the one that matters in insurance: every coverage statement in the
answer must be traceable to a retrieved clause. A confident wrong answer about a
deductible is worse than no answer.

Backends are pluggable via ``JUDGE_BACKEND``:

* ``gemini``  (default) — the same provider the agent runs on, temperature 0.
* ``ollama``           — a local OSS model, for offline runs.

Both run at temperature 0 so a re-run of the gate on unchanged inputs produces the same
scores. That determinism is what lets the CI gate use tolerance bands instead of
retry-until-green.

If no backend is reachable, ``judge`` raises ``JudgeUnavailable``. It deliberately does
*not* return a neutral passing score — a gate that silently substitutes 1.0 for a metric
it could not measure is a gate that always passes. Callers decide whether an unmeasurable
metric is a skip or a hard failure; see ``eval_gate.py``.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass


class JudgeUnavailable(RuntimeError):
    """No judge backend was reachable. Never silently downgraded to a passing score."""


@dataclass
class JudgeScores:
    groundedness: float       # 0..1: claims supported by provided citations
    faithfulness: float       # 0..1: no contradictions with citations
    answer_correctness: float | None  # 0..1 vs reference, if a reference is given
    rationale: str


_RUBRIC = """You are a strict evaluator for an insurance claims assistant.
Given the ANSWER and the CITATIONS it was supposed to rely on, score 0.0-1.0:
- groundedness: fraction of factual/coverage claims in ANSWER supported by CITATIONS.
- faithfulness: 1.0 if nothing in ANSWER contradicts CITATIONS, lower otherwise.
- answer_correctness: vs REFERENCE if provided, else null.
An answer that declines to state coverage because the citations do not cover the
question is fully grounded; do not penalise an honest refusal.
Return ONLY JSON: {"groundedness":x,"faithfulness":x,"answer_correctness":x|null,"rationale":"..."}
"""

# Same rotation as agent/gemini_client.py: free-tier quota burns one model bucket at a
# time, so rotating usually unsticks a 429 without failing the build.
_GEMINI_MODELS = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


def backend_name() -> str:
    return os.getenv("JUDGE_BACKEND", "gemini")


def _call_gemini(prompt: str, *, system: str | None = None) -> str:
    if not os.environ.get("GOOGLE_API_KEY"):
        raise JudgeUnavailable("GOOGLE_API_KEY is not set")
    try:
        from google import genai
        from google.genai import types
    except Exception as e:  # pragma: no cover - import guard
        raise JudgeUnavailable(f"google-genai not installed: {e}") from e

    client = genai.Client()
    models = [m for m in [os.environ.get("JUDGE_MODEL"), *_GEMINI_MODELS] if m]
    last: Exception | None = None
    for model in models:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    # JSON mode only for the judge; the answer generator wants prose.
                    response_mime_type=None if system else "application/json",
                    temperature=0,  # determinism: the gate compares against a baseline
                ),
            )
            return resp.text or ""
        except Exception as e:
            last = e
            continue
    raise JudgeUnavailable(f"all Gemini judge models failed; last error: {last}")


def _call_ollama(prompt: str) -> str:
    try:
        import requests
    except Exception as e:  # pragma: no cover - import guard
        raise JudgeUnavailable(f"requests not installed: {e}") from e

    model = os.getenv("JUDGE_MODEL", "qwen2.5:7b-instruct")
    try:
        r = requests.post(
            os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate"),
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0}},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["response"]
    except Exception as e:
        raise JudgeUnavailable(f"ollama backend unreachable: {e}") from e


def complete(prompt: str, *, system: str | None = None) -> str:
    """One-shot completion on the configured backend, temperature 0.

    Shared by the judge and by the answer-under-test generator in
    ``llmops.groundedness`` so both halves of the groundedness measurement run on the
    same backend selection and the same determinism guarantee.
    """
    backend = backend_name()
    if backend == "gemini":
        return _call_gemini(prompt, system=system)
    if backend == "ollama":
        return _call_ollama(prompt if system is None else f"{system}\n\n{prompt}")
    raise JudgeUnavailable(f"unknown judge backend '{backend}'")


def _call_backend(prompt: str) -> str:
    backend = backend_name()
    if backend == "gemini":
        return _call_gemini(prompt)
    if backend == "ollama":
        return _call_ollama(prompt)
    raise JudgeUnavailable(f"unknown judge backend '{backend}'")


def available() -> bool:
    """Cheap reachability probe, so the gate can report *why* it skipped a metric."""
    try:
        judge("ok", ["[TEST] ok"])
        return True
    except JudgeUnavailable:
        return False


def judge(answer: str, citations: list[str], reference: str | None = None) -> JudgeScores:
    payload = {"ANSWER": answer, "CITATIONS": citations, "REFERENCE": reference}
    raw = _call_backend(_RUBRIC + "\n\n" + json.dumps(payload, ensure_ascii=False))
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise JudgeUnavailable(f"judge returned no parsable JSON: {raw[:200]!r}")
    d = json.loads(m.group(0))
    return JudgeScores(
        groundedness=float(d.get("groundedness", 0.0)),
        faithfulness=float(d.get("faithfulness", 0.0)),
        answer_correctness=(
            None if d.get("answer_correctness") is None else float(d["answer_correctness"])
        ),
        rationale=str(d.get("rationale", "")),
    )
