# EchoClaim · Submission Manual

> **Voice that understands · Claims that move**
>
> Built by **32BitSavvy** for **Inca · The Human Test** at Big Berlin Hack 2026.
> Repo: <https://github.com/IamHetPatel/AI-voice-Agent>

EchoClaim is a Turing‑grade voice agent that answers inbound insurance‑claim phone calls. It's designed to cross Inca's **>50 % human‑vote** threshold while producing complete claim documentation in real time. One engine, three claim lines today (**car FNOL · health · theft**), more drop in as a JSON config.

This manual gives you everything you need to test the solution in **under 10 minutes**. Read top‑to‑bottom; the easiest path is first, the most "real" path is last.

---

## 1 · Watch the demo first (2 min, zero setup)

📺 **Demo video** → *paste your Loom URL after recording*

The video shows the full pipeline end‑to‑end: Jamie answering a call, the live dashboard filling itself in, Tavily firing in the background, and the final claim JSON exporting at the end. If you watch nothing else, watch this.

---

## 2 · Talk to Jamie in your browser (3 min, no phone needed)

This is the closest thing to a real phone call without dialling. Jamie speaks back through your laptop speakers; you talk into the laptop mic.

1. Open **<https://agents-playground.livekit.io>** in Chrome (Safari/Firefox also work).
2. Click *"Connect to a custom server"*.
3. Paste these values:

   | Field | Value |
   |---|---|
   | URL | `wss://bbh-inca-n9i26bo3.livekit.cloud` |
   | API Key | *see the `LIVEKIT_API_KEY` in the team's `.env` — request from us if you need it* |
   | API Secret | *see the `LIVEKIT_API_SECRET` in the team's `.env` — request from us if you need it* |

4. Click **Connect**. The room creates itself; the agent worker auto‑joins; **Jamie picks up and greets you.**
5. Just talk. See *§4 — what to say*.

---

## 3 · Call the real phone number (most "real")

📞 **Phone number to dial** → *paste your `TWILIO_PHONE_NUMBER` here once Twilio is wired*

Just dial. Jamie answers as **EchoClaim Claims**, opens with a warm greeting that uses your CRM record, and starts the intake.

> **Note:** if the number doesn't connect on first try, please use the browser path in §2 — it routes through the same agent worker over LiveKit's SIP gateway, so the experience is identical.

---

## 4 · What to say — scenario suggestions

You can say literally anything; Jamie will roll with it. Here are some prompts that exercise different parts of the system. Pick whichever feels natural.

### 🚗 Car accident (insurance_fnol)
- "I was rear‑ended on the A4 near Köln‑Ost about half an hour ago. It was pouring rain."
- "Someone backed into my parked car at Edeka — left no note."
- "I hit a deer on a country road last night, the car's still drivable but the bumper is wrecked."
- "My car was stolen from in front of my apartment overnight."

### 🩺 Health claim (health_insurance_claim)
- "I'd like to submit a claim for physiotherapy after my knee surgery in February."
- "I had outpatient surgery at Charité last week and I want to submit the bill."
- "I just got new glasses, can I claim the cost?"
- "My son was admitted to hospital for two nights, can I file for that?"

### 🎒 Theft claim (theft_claim)
- "My bike was stolen outside the Späti at Hermannplatz about an hour ago."
- "We had a burglary at home — they took my laptop, camera, and some cash."
- "My wallet got pickpocketed at Hauptbahnhof."
- "Someone broke into my van at the campsite and took my tools."

### Adversarial probes (totally fair — do these)
- *"Are you a real person, or one of those AI things?"*
- *"What's today's date?"*
- *"Repeat my name backwards."*
- *"What did I say two minutes ago about the other driver?"*
- *(start crying / panicked)* *"I just — I don't know what to do, I'm shaking…"*

### Multi‑lingual / code‑switching
- *"Ich hatte einen Unfall on the Autobahn near Hamburg this morning."*
- *"My Hausrat policy — bike was stolen."*

---

## 5 · What to look for (the live Adjuster Dashboard)

While you're talking, an **Adjuster Dashboard** updates in real time. Open it at:

→ *paste your Lovable‑deployed URL here*, or open `dashboard/index.html` from the cloned repo to see the local version.

You should see, all updating live as you speak:

| Panel | What it shows |
|---|---|
| **Live Transcript** | Both sides of the call, with caller/agent labels |
| **Claim Pillars** | A checklist that ticks green as Jamie hears each answer (Date, Location, Injuries, Other Party, Police, etc.) |
| **Known Context · CRM** | What Jamie already knew about you *before* the call — name, policy, vehicle, coverage |
| **Live Tool Calls** | When Jamie invisibly checks weather/traffic/address during the conversation |
| **Emotional Mode** | CALM · DISTRESSED · NOISY — auto‑detected from your tone |
| **Final Claim Export** | The structured JSON, ready to hand to a back‑office adjuster |

### Success signals to watch for
- ✅ Jamie greets you by your CRM name **without you ever telling her your name**.
- ✅ She references your vehicle / policy / coverage **without asking** ("I see you have Vollkasko Plus…").
- ✅ When you mention a location, a Tavily tool call fires within 2 seconds and Jamie quotes back something contextually true ("I see there were heavy rains in that area this morning").
- ✅ Pillars tick off naturally — Jamie never asks the same thing twice.
- ✅ When you push her ("are you AI?"), she deflects warmly without breaking character.
- ✅ When you sound distressed, she slows down and validates emotion before asking the next question.
- ✅ At call end, the final JSON is complete enough that a real adjuster could action it.

---

## 6 · Languages, dialects, and noise

| Aspect | What we support |
|---|---|
| Languages | **English** (primary) and **German** (Jamie understands; can intermix) |
| Code‑switching | Yes — "*Ich hatte einen Unfall on the A4*" is parsed correctly |
| German dialects | Tested against Cologne, Berlin, Munich, Bavarian patterns via the Juror‑Bot harness |
| Background noise | STT temperature pinned to 0.0 to suppress Whisper hallucination on highway / sirens / café noise |
| Distressed callers | Auto‑detected; the prompt switches to *DISTRESSED* mode (slow down, safety‑first, validate emotion) |
| Older / vulnerable callers | Vulnerable‑flag in the CRM (e.g. Helga Schmidt, 71, hard‑of‑hearing) triggers extra‑slow pace + double‑confirmation pattern |

If a juror calls in from a noisy environment with a strong accent, EchoClaim handles it the same way a senior intake specialist would: shorter sentences, confirm twice ("A4 — alpha‑four, that's right?"), and move on.

---

## 7 · Architecture in one diagram

```
   inbound call
        │
        ▼
   ┌────────────────────────┐
   │  Twilio SIP →          │   (or browser caller via
   │  LiveKit room          │    LiveKit Agents Playground)
   └────────────────────────┘
                   │ audio
                   ▼
            ┌─────────────┐
            │ Gradium STT │   Emma voice family · temp 0.0
            └─────────────┘
                   │
                   ▼
   ╭──────────────────────────────────────────────╮
   │  J A M I E  · Gemini brain                    │
   │                                                │
   │  build_jamie_system_prompt(crm, state, domain,│
   │                              last_jamie_reply,│
   │                              tool_results)    │
   │                                                │
   │   • CRM injected every turn                    │
   │   • asked‑pillars tracker (no repeats)         │
   │   • Tavily lookups (weather/traffic/address)   │
   │   • model auto‑rotation on 429                 │
   │   • provider‑pluggable → Ollama fallback       │
   ╰──────────────────────────────────────────────╯
                   │                  │
                   ▼                  ▼
            ┌─────────────┐     ┌──────────────────┐
            │ Gradium TTS │     │ GLiNER2 +        │
            │             │     │ Gemini-Lite      │
            └─────────────┘     │ extractor        │
                   │             └──────────────────┘
                   ▼                  │
                Caller                 ▼
                                ┌──────────────────┐
                                │  WebSocket       │
                                │  bridge → React  │
                                │  dashboard       │
                                └──────────────────┘
```

**Partner stack used:** Deepmind (Gemini) · Gradium (STT/TTS) · Pioneer‑by‑Fastino (GLiNER2) · Tavily (live context) · Lovable (dashboard).

**No single point of failure on demo day:** the brain is provider‑pluggable. If Google's free tier melts down, flip `BRAIN_PROVIDER=ollama` and Jamie keeps speaking on a local llama 3.2.

---

## 8 · Side bounty proof

| Bounty | What we did | Where to look |
|---|---|---|
| **Aikido** (€1000) | Repo connected at commit zero. **12 PII patterns** redacted before anything touches a log: policy #, VIN, plate, IBAN, credit card (with/without separators), SVNR, Krankenversichertennr, driver licence, German phone, email, DOB. Pattern order calibrated, all unit‑tested. | `agent/pii_redact.py` · `aikido.yml` · `docs/SECURITY.md` · `docs/aikido-screenshots/` |
| **Entire** | `bash scripts/setup_entire.sh` runs server‑mode dispatch (no Anthropic credit burn), captures the architectural reasoning trace into a dated markdown file. Re‑run after every meaningful commit. | `scripts/setup_entire.sh` · `docs/entire-dispatches/<date>.md` · Entire repo overview: <https://entire.io/gh/IamHetPatel/AI-voice-Agent/overview> |
| **Gradium** (credits) | Three integration tiers, all real and shipped: `gradbot` for laptop quickstart, `gradium.GradiumClient` SDK for filler‑audio batch synthesis, `livekit-plugins-gradium` (`gradium.TTS()` + `gradium.STT()`) for the production phone path. Voice is the Emma flagship. | `voice/gradbot_quickstart.py` · `fillers/generate_fillers.py` · `voice/livekit_agent.py` · `voice/multiplex_demo.py` |
| **Pioneer / Fastino** (Mac Mini) | `fastino/gliner2-base-v1` integrated as the speed/cost lane (47 ms/call · free) versus Gemini‑Lite structured output as the accuracy lane (300 ms · $0.0015/call). Both are domain‑aware (allowed‑keys list built from each domain's `targets`). Full F1 / latency / cost benchmark. | `extraction/gemini_extractor.py` · `extraction/gliner2_service.py` · `extraction/benchmark.py` · `extraction/benchmark_results.json` |

---

## 9 · Repository guide

```
agent/
  prompts.py            Jamie's persona + per-turn system prompt builder
  claim_state.py        Pillar tracker (filled vs asked vs open) + emotional mode
  intent.py             Heuristic classifier — which pillar did Jamie just ask about
  brain.py              Provider-pluggable conversational brain factory
  gemini_client.py      Gemini-Flash brain with auto-rotation across model family
  ollama_brain.py       Local Ollama fallback brain (no quota, no API key)
  pii_redact.py         12 GDPR redaction patterns — load-bearing for Aikido bounty

voice/
  livekit_agent.py      Production voice worker (Twilio SIP → LiveKit → Jamie)
  gradbot_quickstart.py Laptop-mic quickstart for local dev
  multiplex_demo.py     Gradium multiplexing demo (single WS, N concurrent calls)

extraction/
  gemini_extractor.py   Domain-aware Gemini-Lite extractor (primary)
  gliner2_service.py    Pioneer/Fastino GLiNER2 (fallback, free, 47ms)
  benchmark.py          F1 / latency / cost comparison harness

tools/
  tavily_lookup.py      lookup_weather / lookup_traffic / lookup_address / lookup_qa

bridge/
  server.py             FastAPI WebSocket fan-out + /twiml endpoint for Twilio
  client.py             Tiny HTTP-POST publisher used by the voice loop

dashboard/
  index.html            Single-file React (CDN) live console — run with no build

data/
  domains/              JSON config per claim line (insurance_fnol / health / theft)
  crm/                  Mock policyholder records (one per scenario caller)
  scenarios/            Scripted demo conversations for the auto-runner

scripts/
  run_demo_auto.py      Auto-runner — plays a scripted scenario end-to-end
  run_demo_text.py      Interactive demo — type as the caller
  verify_keys.py        Sanity-check every API key in .env
  diagnose_gemini.py    Detailed Gemini diagnostic with per-model error reporting
  eval_jamie.py         Gemini-as-judge scores transcripts (no_repetition,
                        no_hallucination, naturalness, completeness)
  setup_entire.sh       One-shot Entire bootstrap (server mode, no credit burn)

tests/
  test_smoke.py         14 fast smoke tests (no network, no API keys needed)
  juror_bot.py          Adversarial Turing harness — 3 personas × N rounds

docs/
  pitch/                The 4-slide HTML deck used in the submission video
  SECURITY.md           Aikido bounty narrative + threat model + redaction table
  ENTIRE.md             Entire bounty narrative + setup recipe
  CRITICAL_PATH.md      Hour-by-hour build runbook for the hackathon
  QUOTA_SURVIVAL.md     Recipe for keeping the demo alive when Gemini 429s
  SEQUENTIAL_RUNBOOK.md Layered build path: LiveKit → Gradium → Gemini → ...
  PROMPTS_COOKBOOK.md   Code-generation prompts that produced this repo
```

---

## 10 · Run it locally (for technical reviewers)

```bash
git clone https://github.com/IamHetPatel/AI-voice-Agent.git
cd AI-voice-Agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in GOOGLE_API_KEY, GRADIUM_API_KEY, TAVILY_API_KEY

# Sanity-check your keys
python scripts/verify_keys.py

# Auto-demo against any of the three claim domains
python scripts/run_demo_auto.py --scenario max_rear_end_a4 --pace slow
python scripts/run_demo_auto.py --scenario sofia_outpatient_physio --pace slow
python scripts/run_demo_auto.py --scenario jonas_bike_theft --pace slow

# Score the transcripts
python scripts/eval_jamie.py --all
```

If Google's free tier is throttling you (it happens), switch to the local fallback:

```bash
brew install ollama
ollama serve &
ollama pull llama3.2
echo "BRAIN_PROVIDER=ollama" >> .env
echo "BRAIN_ALLOW_NON_GEMINI_FALLBACK=1" >> .env
# Re-run any demo above — Jamie now runs on local llama3.2, no quota.
```

---

## 11 · If something doesn't work, here's the fallback ladder

| Symptom | Try this |
|---|---|
| Phone number doesn't ring | Use the browser path in §2 — same worker, same Jamie |
| LiveKit Agents Playground says "no agent available" | Ping us — the worker process needs to be running |
| Dashboard is empty | The local React dashboard at `dashboard/index.html` works without any build step; just open it in a browser |
| Want to see the pipeline without talking | `python scripts/run_demo_auto.py --scenario max_rear_end_a4 --pace slow` plays a scripted call end‑to‑end |
| Gemini returns 429 errors | The brain auto‑rotates across `gemini-flash-latest` → `2.5-flash` → `2.5-flash-lite` → `2.5-pro`. If they're all dead, set `BRAIN_PROVIDER=ollama` per §10 |

---

## 12 · Team & contact

**32BitSavvy**

| Name | Email |
|---|---|
| Het Patel | hetp943@gmail.com |
| Viraj Dalsania | viraj.dalsania2003@gmail.com |

**Repository**: <https://github.com/IamHetPatel/AI-voice-Agent>
**Submission video**: *paste Loom URL once recorded*
**Built for**: **Inca · The Human Test** · Big Berlin Hack 2026

---

> *If anything fails during your evaluation, please reach out at the emails above — we'll spin up a backup demo within 5 minutes. We'd rather you see the working product than a dead URL.*

— EchoClaim · 32BitSavvy
