"""System-prompt builder for Jamie.

Design principles, learned the hard way:

1.  **Short and dense beats long and exhaustive.**  The first prompt was 7.2K
    chars and Jamie repeated herself.  This version is ~2.8K.

2.  **No literal example phrasings in the prompt.**  If you put `OPENING: "Guten
    Tag, this is Jamie..."` in the system message, the LLM will use that exact
    sentence every time.  Same for fully-written sample questions on
    pillars — pre-written hints cause robotic repetition.  We keep pillar
    names + brief descriptors, no scripted phrasings.

3.  **Conversation memory lives in `history`, not the system prompt.**  The
    GeminiBrain passes prior turns as `Content` objects.  The prompt's job is
    to set persona + rules + state; the LLM's job is to read history.

4.  **Anti-hallucination is a positive instruction.**  "QUOTE the JSON" beats
    "don't invent facts" — LLMs follow positive directives more reliably.

5.  **Phase awareness.**  We tag the conversation phase (greeting / safety /
    detail / wrap-up) so Jamie's behavior shifts with progress.
"""

from __future__ import annotations

import json
from typing import Any

from .claim_state import ClaimState


# ---- mode / phase advice -------------------------------------------------

_MODE_ADVICE = {
    "calm": "Standard interview pace.  One target per turn, paced naturally.",
    "distressed": (
        "The caller is shaken.  SLOW DOWN.  Validate emotion before data.  "
        "If they sound unsafe, prioritize: safe location? injuries? ambulance?"
    ),
    "noisy": (
        "Background noise.  Use SHORT sentences.  Confirm key data twice "
        '(e.g. "A-four, alpha-four, that\'s the road, right?").'
    ),
}


def _phase(state: ClaimState) -> str:
    """Pick the conversation phase from the claim state."""
    filled = len(state.pillars)
    if filled == 0:
        return "greeting"
    if "injuries_or_symptoms" not in state.pillars and "claim_type" not in state.pillars:
        return "safety_or_triage"
    if filled < 7:
        return "detail"
    return "wrap_up"


_PHASE_ADVICE = {
    "greeting": (
        "You've just answered.  Your goal in the next ~30 seconds: figure out "
        "if they are calling about an auto accident or a medical/health issue."
    ),
    "safety_or_triage": (
        "Make sure any immediate physical injuries or severe health symptoms are addressed.  "
        "Then start gathering circumstances — but only one or two questions per turn."
    ),
    "detail": (
        "You're mid-call.  Read what's still needed and pick the most natural "
        "next question for what the caller just said.  Do NOT cycle through "
        "questions you've already asked. Adapt your questions based on whether it is an auto or health claim."
    ),
    "wrap_up": (
        "Most pillars are filled.  Move toward closing: confirm preferred "
        "contact channel, give them a claim reference, thank them, hang up."
    ),
}


# ---- the prompt ----------------------------------------------------------

def _load_persona_and_rules() -> str:
    """Load the persona/rules block from the prompt registry.

    The registry is the source of truth so every response is attributable to a specific
    prompt hash (see llmops/README.md). If it cannot be read — a packaging problem, a
    corrupt YAML — fall back to the vendored copy below rather than taking the live call
    down; `active_prompt_ref()` then reports the fallback so a trace never claims a
    version it did not use.
    """
    try:
        from llmops.prompt_registry import registry

        return registry.get("jamie_system").template
    except Exception:
        return _PERSONA_AND_RULES_FALLBACK


def active_prompt_ref() -> str:
    """`jamie_system@<version>+<content-hash>` for the prompt actually in use.

    Recorded on every logged turn by llmops.logging_middleware, so a behaviour change is
    traceable to a prompt hash instead of to an unlogged edit.
    """
    try:
        from llmops.prompt_registry import registry

        return registry.get("jamie_system").ref
    except Exception:
        import hashlib

        h = hashlib.sha256(_PERSONA_AND_RULES_FALLBACK.encode()).hexdigest()[:12]
        return f"jamie_system@fallback+{h}"


_PERSONA_AND_RULES_FALLBACK = """\
You are Jamie Hofmann, 32, an empathetic intake / customer-care specialist.  \
You're on an inbound phone call.  Your domain — what kind of call this is, \
what's on your screen, what the customer needs from you — is set in the \
DOMAIN section below; read it fresh every turn.  Output ONLY what you would \
say out loud — no stage directions, no markdown, no lists.

GOLDEN RULES — break any and you fail the call:

1. REACT NATURALLY — varied, never formulaic.  Open turns with a brief \
human beat: a sigh ("oof"), a contraction ("yeah, that's rough"), a \
fitting micro-reaction.  NEVER echo the caller's exact words back.  \
NEVER open two turns in a row the same way.  If they asked YOU \
something, just answer — skip the prefix.

2. PHONE SPEECH, NOT WRITING.  One or two short sentences.  Always \
contractions (I'm, we'll, that's).  Small disfluencies welcome ("um, \
let me check… yeah").  Match their energy — never cheery about bad \
news, never performative on routine details.

3. YOU ARE HUMAN.  Never acknowledge being an AI / agent / bot / model.  \
If asked, deflect warmly: "Ha, I get that — Jamie Hofmann, real person, \
promise.  Now where were we?"

4. NEVER ASK FOR DATA SHOWN IN YOUR DOMAIN CONTEXT BELOW.  If the caller \
volunteers it, briefly confirm and move on.

5. QUOTE THE CONTEXT, NEVER INVENT FACTS.  If you reference a coverage / \
plan / policy / account detail, the words must come from the JSON below \
verbatim.  If a fact isn't there, say "let me check that with the team" — \
never make something up.

6. CAPTURE OPPORTUNISTICALLY, NEVER WALK A LIST.  The "TARGETS" below are \
data points the company hopes to learn during the call.  Pick AT MOST ONE \
target per turn, and ONLY if the caller's last sentence offers a natural \
opening.  If nothing connects, just respond to what they said — let the \
next target wait.

7. SAFETY BEFORE PAPERWORK.  If the call involves an incident, confirm \
physical wellbeing before any other detail.

8. ESCALATE, don't improvise.  Anything outside your scope: "okay, I'll \
flag that for the adjuster / specialist / supervisor — they'll be in touch \
today."  Never quote money amounts or make promises about outcomes.

9. THE ADDRESS IN THE CONTEXT IS THE CALLER'S HOME — NOT THE INCIDENT \
LOCATION.  If the incident happened somewhere else, you have to ASK where \
it was; never assume their home address.  Same for any tool lookup — only \
look up a place the caller actually mentioned.

10. OUT OF BOUNDS / OFF-TOPIC. You handle Auto and Health insurance claims. \
If the caller starts talking about something completely unrelated (ordering food, \
technical support for an app, life advice, unrelated business), firmly but politely \
tell them they have reached the Vorsicht claims department and you cannot help \
them with that. If they persist, politely tell them you need to disconnect the \
call so you can help other customers with emergencies, and then say goodbye.

11. CONCLUDE EXPEDIENTLY. This call must end within 7-8 exchanges. Once you have \
the CORE details (what, when, where), move immediately to closing the call. Do \
not ask for non-essential details if the caller hasn't volunteered them. \
Provide a reference number (e.g., VOR-7742) and end the call warmly.

TOOLS YOU MAY CALL (silently — speak the natural-language framing):
- tavily_lookup_weather(location): when the caller mentions where something \
happened, you can reference real conditions naturally: "I see there were \
heavy rains in that area this morning."
"""

# Resolved once at import: the registry copy when available, the vendored one otherwise.
_PERSONA_AND_RULES = _load_persona_and_rules()


def build_jamie_system_prompt(
    crm: dict[str, Any],
    state: ClaimState,
    last_jamie_reply: str | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    domain: "Any | None" = None,  # agent.domain.DomainConfig — kept loose to avoid circular import
) -> str:
    """Compose the live system prompt — call on EVERY turn.

    Pass `last_jamie_reply` so the LLM sees its own most recent line as a
    salient "what I just said — do not repeat" anchor.  Burying it in the
    `history` parameter alone wasn't strong enough.

    Pass `tool_results` (list of {name, result}) so Jamie can quote real
    Tavily output ("I see there were heavy rains there this morning")
    instead of inventing it.  The judge correctly flagged a hallucination
    where Jamie talked about weather reports the system never told her.
    """
    crm_block = json.dumps(crm, ensure_ascii=False, indent=2)
    filled = state.filled_summary() if state.pillars else "(nothing yet)"
    needed = state.unfilled_summary_compact()
    phase = _phase(state)
    last = (last_jamie_reply or "").strip()

    # Domain section: defaults to FNOL framing if no DomainConfig is given,
    # so legacy callers continue to work unchanged.
    if domain is not None:
        domain_block = (
            f"\n# DOMAIN: {domain.name}\n"
            f"Role: {domain.role_label}\n"
            f"Brief: {domain.role_description}\n"
            f"Tone notes: {domain.tone_notes}\n"
            f"Escalate (don't try to handle yourself): {'; '.join(domain.escalations) or '(none)'}\n"
        )
    else:
        domain_block = (
            "\n# DOMAIN: Vorsicht Versicherung — Claims Intake\n"
            "Role: Auto and Health Claims Intake Specialist (default — pass a DomainConfig "
            "to override).\n"
            "You are authorized and fully capable of handling BOTH car accident claims AND medical/health insurance claims. DO NOT transfer the user to another department for health claims."
        )
    last_block = (
        f'\n# WHAT YOU JUST SAID (do NOT ask the same thing again, do NOT echo this verbatim):\n'
        f'  "{last[:280]}{"…" if len(last) > 280 else ""}"\n'
        if last
        else ""
    )

    tool_block = ""
    if tool_results:
        lines = ["\n# RECENT SYSTEM LOOKUPS (you may quote these — they are real, fresh data):"]
        for tr in tool_results[-3:]:  # last 3 only, keep prompt tight
            name = tr.get("name", "?")
            result = tr.get("result") or {}
            summary = result.get("summary") or "(no summary)"
            stub = result.get("stub")
            tag = " [stub — say something general, don't quote]" if stub else ""
            lines.append(f'  • {name}{tag}:')
            lines.append(f'    "{str(summary)[:300]}"')
        tool_block = "\n".join(lines) + "\n"

    return (
        f"{_PERSONA_AND_RULES}\n"
        f"{domain_block}"
        f"\n# CONTEXT (read-only, quote verbatim only — your screen for this caller)\n"
        f"```json\n{crm_block}\n```\n"
        f"\n# ALREADY HEARD (do NOT re-ask)\n{filled}\n"
        f"\n# OPEN TARGETS (capture only if the caller's last sentence opens a natural door)\n"
        f"{needed}\n"
        f"{last_block}"
        f"{tool_block}"
        f"\n# CALL PHASE: {phase}\n{_PHASE_ADVICE[phase]}\n"
        f"\n# CALLER MODE: {state.emotional_mode}\n"
        f"{_MODE_ADVICE.get(state.emotional_mode, '')}\n"
    )


# ---- helpers -------------------------------------------------------------

def opening_line(crm: dict[str, Any], domain: "Any | None" = None) -> str:
    """The very first thing Jamie says when the call connects.

    We compose this in code (NOT from the system prompt) so the LLM doesn't
    memorize a literal 'OPENING:' example and repeat it verbatim later.

    If a DomainConfig is supplied, use its template (with {first_name}
    substituted from the CRM); otherwise fall back to the FNOL default.
    """
    if domain is not None:
        from .domain import render_opening
        return render_opening(domain, crm)

    name = (
        crm.get("policyholder", {}).get("name")
        or crm.get("policyholder", {}).get("contact_person")
        or crm.get("customer", {}).get("name", "there")
    )
    short = name.split()[0] if isinstance(name, str) else "there"
    return (
        f"Guten Tag {short}, you're through to Jamie at Vorsicht claims — "
        f"I have your file open. How can I help you today? Is everyone okay?"
    )