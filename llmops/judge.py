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
    """Backend that *scores* the answer."""
    return os.getenv("JUDGE_BACKEND", "gemini")


def answer_backend_name() -> str:
    """Backend that *generates* the answer under test.

    Defaults to the judge backend only for backwards compatibility. In a real evaluation
    this should be whatever the live agent runs on, and it must differ in family from the
    judge — see ``family_conflict``.
    """
    return os.getenv("ANSWER_BACKEND") or backend_name()


# Which model family a backend belongs to. Judges from the same family as the generator
# systematically over-reward it (self-enhancement / family bias), so the two must differ.
_FAMILY = {"gemini": "google", "ollama": "local-oss"}


def family_of(backend: str, model: str | None = None) -> str:
    if backend == "ollama" and model:
        # Ollama serves many families; name the model so e.g. gemma-on-Ollama is not
        # mistaken for a different family than Gemini.
        head = model.split(":", 1)[0].lower()
        for fam, keys in {"google": ("gemma",), "meta": ("llama",), "qwen": ("qwen",),
                          "mistral": ("mistral", "mixtral")}.items():
            if any(k in head for k in keys):
                return fam
        return "local-oss"
    return _FAMILY.get(backend, backend)


def family_conflict() -> str | None:
    """Return a warning when the judge shares a model family with the generator.

    The bias is well documented: a judge scores its own family's style as higher quality,
    so a same-family groundedness number is inflated by an unknown amount. This does not
    raise -- a same-family run is still informative -- but it must never pass silently.
    """
    gen_b, judge_b = answer_backend_name(), backend_name()
    gen_f = family_of(gen_b, os.getenv("ANSWER_MODEL"))
    judge_f = family_of(judge_b, os.getenv("JUDGE_MODEL"))
    if gen_f != judge_f:
        return None
    return (f"judge and generator share model family {judge_f!r} "
            f"(generator={gen_b}, judge={judge_b}); groundedness is biased upward")


def _call_gemini(prompt: str, *, system: str | None = None, model: str | None = None) -> str:
    if not os.environ.get("GOOGLE_API_KEY"):
        raise JudgeUnavailable("GOOGLE_API_KEY is not set")
    try:
        from google import genai
        from google.genai import types
    except Exception as e:  # pragma: no cover - import guard
        raise JudgeUnavailable(f"google-genai not installed: {e}") from e

    client = genai.Client()
    models = [m for m in [model, os.environ.get("JUDGE_MODEL"), *_GEMINI_MODELS] if m]
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


def _call_ollama(prompt: str, *, model: str | None = None) -> str:
    try:
        import requests
    except Exception as e:  # pragma: no cover - import guard
        raise JudgeUnavailable(f"requests not installed: {e}") from e

    model = model or os.getenv("JUDGE_MODEL", "qwen2.5:7b-instruct")
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


def complete(prompt: str, *, system: str | None = None, backend: str | None = None,
             model: str | None = None) -> str:
    """One-shot completion on the configured backend, temperature 0.

    Shared by the judge and by the answer-under-test generator in
    ``llmops.groundedness`` so both halves of the groundedness measurement run on the
    same backend selection and the same determinism guarantee.
    """
    backend = backend or backend_name()
    if backend == "gemini":
        return _call_gemini(prompt, system=system, model=model)
    if backend == "ollama":
        return _call_ollama(prompt if system is None else f"{system}\n\n{prompt}", model=model)
    raise JudgeUnavailable(f"unknown backend '{backend}'")


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
