# Component design notes

The contracts the core modules satisfy. Useful as a map of responsibilities and as a
specification when changing or reimplementing a piece.

## Voice pipeline

`voice/livekit_agent.py` wires the production loop on `livekit-agents`: `gradium.TTS()`
for speech out, Gradium STT (LiveKit default STT as fallback), and `GeminiBrain` as the
LLM, inside an `AgentSession` with Silero VAD. Per turn it (a) accepts inbound audio from
a LiveKit room, (b) regenerates the system prompt via
`agent.prompts.build_jamie_system_prompt(crm, state)`, (c) forks the latest user
transcript to `extraction.gliner2_service.ExtractionService` and publishes entity events
to `bridge.client.publish`, and (d) plays pre-generated filler audio from
`fillers/audio/*.pcm` when the LLM stalls beyond ~400ms.

## Known-context system prompt

`agent.prompts.build_jamie_system_prompt(crm, state)` returns the system prompt as a
single string. It inlines the full CRM JSON under a "do not ask for these fields" header,
inlines the live `ClaimState` (filled vs. unfilled pillars, emotional mode), forbids the
agent from disclosing it is automated, requires confirming physical safety before data
collection, describes the available tool calls and how to phrase them in speech, and keeps
replies to one or two spoken-style sentences (no markdown, no lists). It is rebuilt every
turn so the agent reads from authoritative state rather than memory.

## Extraction microservice

`extraction.gliner2_service.ExtractionService` loads `fastino/gliner2-base-v1`, falls back
to `knowledgator/gliner-bi-large-v2.0`, and falls back to a regex stub if `gliner` isn't
installed. It exposes `extract(text) -> {pillars, fraud, elapsed_ms, mode, model}`. The
15 claim labels and 5 fraud labels are derived from the module-level `HUMAN_TO_ID` /
`FRAUD_HUMAN_TO_ID` maps (`CLAIM_LABELS`, `FRAUD_LABELS`). A streaming entry point pushes
`{type: "entity", ...}` and `{type: "fraud_signal", ...}` events to the bridge.

## Adversarial conversation harness

`tests/juror_bot.py` simulates adversarial calls (rotating personas) between a scripted
caller and the agent (text-only, via `GeminiBrain` + `build_jamie_system_prompt`). After
each call it asks a judge model for a strict-JSON verdict
`{verdict, confidence, reasoning}`, writes results to `tests/juror_results.json`/`.csv`,
and prints the pass rate. It runs without an API key (deterministic stubs), so it can run
in CI.

## PII redactor

`agent/pii_redact.py` exposes `redact(text)` and `redacted_dict(d)`, replacing German
policy numbers, VINs, plates, phones, IBANs, dates of birth, emails, and related
identifiers with bracketed tokens. It includes a `__main__` self-test. It is the
single boundary every persistence path passes through. See [SECURITY.md](SECURITY.md).
