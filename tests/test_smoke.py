"""Smoke tests — fast, no network, no API keys.

These prove the modules import + the core data path works.
Run with:  pytest -q
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_crm_profiles_load():
    for name in ["max_mueller", "helga_schmidt", "thomas_weber_fleet"]:
        p = REPO / "data" / "crm" / f"{name}.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["policyholder"]["name"]
        assert data["policy"]["policy_number"]


def test_pii_redact():
    from agent.pii_redact import redact
    sample = "policy DE-HUK-2024-884421 plate B-MM 4421 vin WVWZZZ1JZ3W386752"
    out = redact(sample)
    assert "884421" not in out
    assert "[POLICY]" in out
    assert "[PLATE]" in out
    assert "[VIN]" in out


def test_pii_redact_extended():
    """Aikido-bounty patterns: credit card, social security, health card,
    multi-segment phone, IBAN, DOB, email — none of these should leak even
    when they appear in a single transcript line."""
    from agent.pii_redact import redact

    # Credit card with separators
    out = redact("My card 4242 4242 4242 4242.")
    assert "4242" not in out, f"credit card leaked: {out!r}"
    assert "[CARD]" in out

    # Credit card without separators
    out = redact("Card no 4111111111111111 expires.")
    assert "4111111111111111" not in out
    assert "[CARD]" in out

    # IBAN
    out = redact("DE89 3704 0044 0532 0130 00 is mine.")
    assert "3704" not in out
    assert "[IBAN]" in out

    # German Sozialversicherungsnummer
    out = redact("SVNR 12 030484 W 023 handed over.")
    assert "030484" not in out
    assert "[SVNR]" in out

    # Multi-segment phone
    out = redact("Phone +49 172 555 0100 anytime.")
    # The full digit sequence shouldn't survive — at minimum the last group
    # (which the older regex was missing) must be redacted.
    assert "0100" not in out, f"phone tail leaked: {out!r}"
    assert "[PHONE]" in out

    # Email
    out = redact("Send to max.mueller@email.de please.")
    assert "max.mueller" not in out
    assert "[EMAIL]" in out

    # DOB ISO format
    out = redact("DOB 1984-03-15 confirmed.")
    assert "1984" not in out
    assert "[DOB]" in out


def test_claim_state_priorities():
    from agent.claim_state import ClaimState, PILLARS
    s = ClaimState(call_id="t")
    assert len(s.unfilled_pillars()) == len(PILLARS)
    s.fill("injuries", "no injuries")
    assert "injuries" not in dict(s.unfilled_pillars())
    s.flag_fraud("delayed_reporting", "three weeks", "high")
    assert s.fraud_risk_score() >= 4


def test_extractor_stub_path():
    from extraction.gliner2_service import ExtractionService
    svc = ExtractionService()
    out = svc.extract(
        "I was on the A4 today, plate K-AB 1234, the police came, "
        "I have whiplash, three weeks ago I noticed the dent."
    )
    # In stub mode we should still pull at least a couple of these:
    keys = set(out["pillars"]) | set(out["fraud"])
    assert {"other_party_plate", "road_type"} <= keys or svc.mode == "gliner"


def test_prompt_builder_includes_crm():
    from agent.claim_state import ClaimState
    from agent.prompts import build_jamie_system_prompt
    crm = json.loads((REPO / "data" / "crm" / "max_mueller.json").read_text())
    p = build_jamie_system_prompt(crm, ClaimState(call_id="t"))
    # The prompt must inline the CRM
    assert "Max Müller" in p
    assert "Volkswagen" in p
    # ...and must include the load-bearing rules.  Phrasings updated for
    # the multi-domain pivot ("CONTEXT" not "CRM", but functionally same).
    assert "QUOTE THE CONTEXT" in p
    # Rule 1 shifted from "ALWAYS ACKNOWLEDGE..." (which was producing
    # mechanical echo-back) to "REACT NATURALLY" — varied human beats,
    # ban echo of caller's exact words.  Same load-bearing intent, new
    # keyword.
    assert "REACT NATURALLY" in p
    assert "NEVER ASK FOR DATA SHOWN" in p
    assert "CAPTURE OPPORTUNISTICALLY" in p


def test_prompt_rules_section_is_tight():
    """Guard against rule-creep that dilutes instruction salience.  We
    bumped the cap to 2500 when the multi-domain rewrite added the
    'always acknowledge' rule (worth the chars — directly addresses the
    'list-walker' criticism)."""
    from agent.prompts import _PERSONA_AND_RULES
    assert len(_PERSONA_AND_RULES) < 3600, (
        f"rules section is {len(_PERSONA_AND_RULES)} chars — keep it under 3600 "
        "or add a justification.  Long rules = diluted instructions = repetition.  "
        "Bumped 2500 → 2700 for Rule 9 (address-vs-incident-location), then "
        "2700 → 3600 for the multi-domain pivot: Rule 10 (out-of-bounds / off-topic "
        "handling) and Rule 11 (conclude within 7-8 exchanges).  Both are "
        "load-bearing — they fix the agent rambling off-domain and never closing "
        "the call."
    )


def test_claim_state_to_dict_is_json_serializable():
    """asked_pillars is a set; ClaimState.to_dict must convert it to a
    list so json.dumps doesn't blow up at transcript save time."""
    import json as _json
    from agent.claim_state import ClaimState
    s = ClaimState(call_id="t")
    s.mark_asked({"injuries", "vehicle_drivable"})
    d = s.to_dict()
    raw = _json.dumps(d)  # must not raise
    assert "injuries" in raw
    assert "vehicle_drivable" in raw


def test_intent_classifier_basic():
    """The asked-pillar tracker is the real fix for repetition.  Smoke
    a few representative Jamie utterances."""
    from agent.intent import classify_jamie_question
    assert classify_jamie_question("Are you okay? Anyone hurt?") == {"injuries"}
    assert classify_jamie_question("Is the car drivable?") == {"vehicle_drivable"}
    assert classify_jamie_question("Were the police called? Got a case number?") == {
        "police_involved", "police_case_number"
    }
    assert classify_jamie_question("Just so I have it noted.") == set()


def test_asked_pillars_excluded_from_open_targets():
    """If a pillar is in asked_pillars, it must NOT appear under
    'OPEN TARGETS' — that's what stops the list-walker pattern."""
    from agent.claim_state import ClaimState
    s = ClaimState(call_id="t")
    # Use the canonical pillar IDs (renamed to injuries_or_symptoms /
    # police_or_ambulance in the multi-domain rewrite). NOTE: the intent
    # classifier still emits the old short labels ("injuries"), so
    # mark_asked(classify(...)) doesn't currently exclude those pillars —
    # tracked separately; this unit test covers the exclusion mechanism itself.
    s.mark_asked({"vehicle_drivable", "injuries_or_symptoms"})
    summary = s.unfilled_summary_compact()
    open_section = summary.split("PARKED")[0]
    assert "vehicle_drivable" not in open_section
    assert "injuries_or_symptoms" not in open_section
    assert "PARKED" in summary


def test_unfilled_summary_has_no_scripted_questions():
    """Pre-written sample questions in the system prompt cause the LLM to
    reuse them verbatim every turn.  We removed the hint phrasings; this
    test guards against accidentally re-introducing them."""
    from agent.claim_state import ClaimState
    s = ClaimState(call_id="t")
    summary = s.unfilled_summary_compact()
    # Forbidden literal phrasings from the old hints:
    forbidden = ["Are you or anyone else hurt?", "When exactly did this happen?",
                 "Do you have the other party's license plate?",
                 "Were the police called?"]
    for f in forbidden:
        assert f not in summary, f"scripted question leaked: {f!r}"


def test_tavily_stub_runs():
    from tools.tavily_lookup import lookup_weather
    r = lookup_weather("A4 Köln")
    assert "summary" in r


def test_domains_loadable():
    """Every JSON in data/domains/ must parse into a DomainConfig."""
    from agent.domain import list_domains, load_domain, render_opening
    ids = list_domains()
    # Per Inca's clarification, all domains must be CLAIM types.
    assert "insurance_fnol" in ids
    assert "health_insurance_claim" in ids
    assert "theft_claim" in ids
    for did in ids:
        d = load_domain(did)
        assert d.targets, f"{did}: empty targets"
        assert d.role_label, f"{did}: missing role_label"
        rendered = render_opening(d, {"policyholder": {"name": "Test User"}})
        assert rendered and len(rendered) > 10, f"{did}: opening rendered empty"


def test_prompt_renders_per_domain():
    """The prompt must reflect the domain in its persona block."""
    from agent.claim_state import ClaimState
    from agent.domain import load_domain
    from agent.prompts import build_jamie_system_prompt
    crm = json.loads((REPO / "data" / "crm" / "sofia_health_claim.json").read_text())
    d = load_domain("health_insurance_claim")
    state = ClaimState(call_id="t", targets=list(d.targets))
    p = build_jamie_system_prompt(crm, state, domain=d)
    assert "Health" in p or "Allianz" in p
    assert "Sofia Richter" in p


def test_extractor_uses_domain_targets():
    """GeminiExtractor.for_domain must restrict its allowed-keys list to
    the domain's targets — banking shouldn't fill 'accident_location'."""
    from agent.domain import load_domain
    from extraction.gemini_extractor import GeminiExtractor
    d = load_domain("theft_claim")
    e = GeminiExtractor.for_domain(d, fallback=None)
    # Build the prompt for an arbitrary text and check the labels listed
    p = e._build_prompt("test")
    # Targets that SHOULD be in the prompt
    assert "incident_type" in p
    assert "items_stolen" in p
    # FNOL-specific labels that must NOT be in the prompt
    assert "accident_date" not in p
    assert "vehicle_drivable" not in p
