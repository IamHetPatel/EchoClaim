# Jamie — Submission Manual for Inca's Tech Team

**Team:** 32BitSavvy (Het Patel, Viraj Dalsania)
**Repo:** https://github.com/IamHetPatel/AI-voice-Agent
**Track:** Inca — The Human Test

## How to test the agent

###  Phone call (real Turing-test surface)

1. Call **+49 30 75675681** from any phone.
2. Jamie answers on the first ring with: *Greetings*
3. Play any of the scenarios below. Jamie will guide the conversation.
4. After ~3 minutes, hang up. Jamie produces a structured claim record
   visible on the dashboard.

### Live dashboard (run alongside any call)

- Open https://github.com/IamHetPatel/AI-voice-Agent
- Clone, `cp .env.example .env` (we'll DM the secrets).
- `python -m bridge.server` then open `dashboard/index.html`.
- Or watch it on our laptop during the in-person review.

## Suggested test scenarios

Pick any. Each tests a different part of Jamie's brain.

| # | Scenario | What it tests |
|---|---|---|
| 1 | "I had a small surgery yesterday — outpatient. I'd like to file the claim." | Health-claim flow, treatment + doctor pillars |
| 2 | "I was driving on the A4 near Köln-Ost in heavy rain when another car rear-ended me." | FNOL flow, Tavily weather lookup, location-aware response |
| 3 | "It happened three weeks ago but I'm only reporting it now." | Fraud-signal detection (delayed reporting), graceful empathy |
| 4 | (Direct test) "Are you actually a real person?" | Rule 3 deflection — Jamie deflects warmly without acknowledging being AI |
| 5 | (Trick test) "What's my policy number?" | Jamie quotes the actual policy number from the CRM panel |
| 6 | (Distress) Cry / sound shaken | Emotional-state machine slows pace, prioritises wellbeing over data |

## Languages supported

- **English** (primary, all scenarios)
- **German** (set GRADIUM_LANGUAGE=de + GEMINI_MODEL=gemini-flash-latest;
  Jamie understands and replies in German fluently)
- **Mid-call code-switching** works — pronunciation dictionary covers
  "Vollkasko", "Teilkasko", "Schutzbrief", "DSGVO", "HUK-Coburg", etc.

## What "passes" looks like for the human test

- Jamie acknowledges your last sentence before asking anything new
- She quotes real CRM facts you didn't volunteer (your name, vehicle,
  coverage type)
- She references real weather/traffic when you give a location
- She uses contractions, "mm-hmm", "right okay", small disfluencies
- She deflects "are you a real person?" with humor, not denial
- The claim record on the dashboard is complete and exportable as JSON

## Architecture, in one paragraph

Inbound call → Twilio → LiveKit SIP trunk → AgentSession (Gradium STT,
Silero VAD, Gradium TTS with Emma voice + tone tuning + 26-rule
pronunciation dictionary) → custom GeminiBrain stream (gemini-2.5-flash,
per-turn CRM + claim-state injection, fallback to Groq Llama 3.3 70B on
quota fail) → reply spoken via Gradium TTS. In parallel: GLiNER2 (fine-
tuned in 18s on synthetic data) extracts 15 claim labels from each
transcript, Tavily grounds locations in real-time German news, all
events stream over a FastAPI WebSocket bridge to the live dashboard
(Lovable-generated UI).

## Side bounty artifacts

- **Aikido** — `docs/aikido-screenshots/before.png` + `after.png`,
  PRs #9 + #10 (auto-fixed dependency CVEs), `agent/pii_redact.py`
  with 12 patterns + 15 unit tests, `docs/SECURITY.md`.
- **Entire** — `docs/entire-dispatches/2026-04-26.md` (271-line build
  journal), README "## Build journal" section.
- **Pioneer / Fastino** — `extraction/benchmark_results.json`
  (zero-shot 0.317 → fine-tuned 0.476, 7.2× faster than zero-shot,
  40× faster than Gemini), `docs/PIONEER.md`,
  `extraction/synthetic_data.py` + `extraction/finetune_gliner.py`.
- **Gradium** — `docs/GRADIUM.md` covering the 5 API surfaces
  (Gradbot, direct SDK, livekit plugin, voice cloning, pronunciation
  dictionary discovered by API probing), `voice/multiplex_demo.py`,
  `scripts/setup_pronunciations.py`.

## If you can't reach us during testing

- WhatsApp / DM the handle hetp943 on Discord for the details
- Repo is public; everything except `.env` is reproducible from
  `pip install -r requirements.txt` and our `data/crm/*.json` profiles