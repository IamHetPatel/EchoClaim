"""Text-mode end-to-end demo.

Run this once the bridge is up; type as the caller, watch Jamie reply, watch
the dashboard fill in.  Works without ANY API keys (Gemini falls back to a
deterministic stub, Tavily falls back to a stub, GLiNER falls back to regex).

Usage:
    # terminal 1
    uvicorn bridge.server:app --port 8765 --reload

    # terminal 2 — open dashboard/index.html in your browser

    # terminal 3
    python scripts/run_demo_text.py --crm max_mueller
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# load .env if available so demo reads keys without manual export
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(REPO / ".env", override=True)
except Exception:
    pass

from agent.claim_state import ClaimState
from agent.brain import make_brain
from agent.prompts import build_jamie_system_prompt, opening_line
from agent.intent import classify_jamie_question
from agent.pii_redact import redact
from extraction.gliner2_service import ExtractionService
from extraction.gemini_extractor import GeminiExtractor
from bridge.client import publish as bridge_publish
from tools.tavily_lookup import DISPATCH as TAVILY_DISPATCH
from tools.coverage_lookup import DISPATCH as COVERAGE_DISPATCH

# All callable tools Jamie can invoke in the text demo.
TOOL_DISPATCH = {**TAVILY_DISPATCH, **COVERAGE_DISPATCH}


def load_crm(name: str) -> dict:
    path = REPO / "data" / "crm" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# Trigger heuristics: when should Jamie call a Tavily lookup proactively?
# Cheap rules — the real LLM tool-call path is in voice/livekit_agent.py.
def _maybe_tool_calls(user_text: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    lower = user_text.lower()
    for kw in ("a4", "a5", "a9", "a10", "autobahn", "berlin", "münchen", "munich",
              "stuttgart", "köln", "cologne", "hauptstraße"):
        if kw in lower:
            out.append(("tavily_lookup_weather", {"location": user_text[:80]}))
            break
    if "drivable" in lower or "kann nicht fahren" in lower or "totaled" in lower:
        out.append(("tavily_lookup_towing", {"location": user_text[:80]}))
    # Coverage questions -> ground the answer in cited policy clauses.
    coverage_kw = (
        "covered", "cover", "deckt", "gedeckt", "versichert", "zahlt", "übernimmt",
        "übernommen", "selbstbeteiligung", "vollkasko", "teilkasko", "kasko",
        "parkschaden", "parkschäden", "diebstahl", "entwendung", "vandalismus",
    )
    if any(kw in lower for kw in coverage_kw):
        out.append(("coverage_lookup", {"query": user_text[:200]}))
    return out


def _maybe_emotional_mode(user_text: str, current: str) -> str:
    lower = user_text.lower()
    if any(w in lower for w in ("crying", "shaking", "scared", "panik", "weine", "i can't", "i don't know what to do")):
        return "distressed"
    if any(w in lower for w in ("highway noise", "traffic", "loud", "static", "[noise]")):
        return "noisy"
    return current


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crm", default=os.environ.get("DEMO_CRM_PROFILE", "max_mueller"))
    parser.add_argument("--no-bridge", action="store_true",
                        help="don't publish to the WebSocket bridge")
    args = parser.parse_args()

    crm = load_crm(args.crm)
    state = ClaimState(call_id=f"text-demo-{args.crm}")
    brain = make_brain()
    # Default to FNOL when running interactively without a scenario file.
    from agent.domain import load_domain
    domain = load_domain("insurance_fnol")
    extractor = GeminiExtractor.for_domain(domain, fallback=ExtractionService())

    print(f"\n  CRM:        {args.crm}")
    print(f"  Gemini:     {'live' if brain._real else 'stub fallback'}")
    print(f"  Extractor:  {extractor.mode}")
    print(f"  Bridge:     {'OFF' if args.no_bridge else 'http://localhost:8765/publish'}")
    print( "  Tip:        type 'quit' to end the call.\n")

    async def emit(ev: dict) -> None:
        if not args.no_bridge:
            await bridge_publish(ev)

    await emit({"type": "call_start", "crm": crm})

    # Jamie speaks first
    opener = opening_line(crm)
    print(f"Jamie: {opener}\n")
    await emit({"type": "transcript", "speaker": "jamie", "text": opener})

    history: list[dict[str, str]] = [
        {"role": "model", "text": opener},
    ]
    tool_results: list[dict] = []

    while True:
        try:
            user = input("You:   ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user.lower() in ("quit", "exit", ":q"):
            break

        await emit({"type": "transcript", "speaker": "caller", "text": redact(user)})

        # Emotional mode + tool decisions
        new_mode = _maybe_emotional_mode(user, state.emotional_mode)
        if new_mode != state.emotional_mode:
            state.set_mode(new_mode)
            await emit({"type": "emotional_state", "state": new_mode})

        for name, args_ in _maybe_tool_calls(user):
            await emit({"type": "tool_call", "name": name, "args": args_})
            fn = TOOL_DISPATCH[name]
            result = await asyncio.to_thread(fn, **args_)
            await emit({"type": "tool_result", "name": name, "result": result})
            tool_results.append({"name": name, "result": result})

        # Extract pillars from caller text → state + bridge
        extr = await asyncio.to_thread(extractor.extract, user)
        for label, info in extr["pillars"].items():
            state.fill(label, info["text"], confidence=info["score"])
            await emit({"type": "entity", "label": label,
                        "value": info["text"], "confidence": info["score"]})
        for label, info in extr["fraud"].items():
            state.flag_fraud(label, info["text"])
            await emit({"type": "fraud_signal", "signal": label,
                        "severity": "medium", "evidence": info["text"]})

        # Generate Jamie's reply (streaming).  We pass her own most-recent
        # line into the system prompt so the "WHAT YOU JUST SAID" anchor
        # is salient — burying it in `history` alone wasn't strong enough.
        last_jamie = next(
            (h["text"] for h in reversed(history) if h["role"] == "model"),
            None,
        )
        sys_prompt = build_jamie_system_prompt(
            crm, state,
            last_jamie_reply=last_jamie,
            tool_results=tool_results,
        )
        chunks: list[str] = []
        sys.stdout.write("Jamie: ")
        sys.stdout.flush()
        async for piece in brain.stream_reply(sys_prompt, history, user):
            sys.stdout.write(piece)
            sys.stdout.flush()
            chunks.append(piece)
        print("\n")

        reply = "".join(chunks).strip()
        history.append({"role": "user", "text": user})
        history.append({"role": "model", "text": reply})

        # Track which pillars Jamie asked about — anti-repetition.
        asked_now = classify_jamie_question(reply)
        if asked_now:
            state.mark_asked(asked_now)

        await emit({"type": "transcript", "speaker": "jamie", "text": reply})

    # Wrap up
    await emit({"type": "call_end", "claim_json": state.to_dict()})
    print("\n--- Final claim state ---")
    print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run())
