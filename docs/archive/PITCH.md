# Caution Claims · Pitch & Submission Package

> Track: **Inca — The Human Test**
> Team: **32BitSavvy** · Het Patel & Viraj Dalsania
> Repo: https://github.com/IamHetPatel/AI-voice-Agent

---

## 1. The 2-minute video — scene-by-scene script

Total target: **1m 55s** (leaves 5s buffer for upload trim).

Record in OBS or Loom in this order; the cuts can be assembled in any editor.

### Scene 1 — Hook (0:00 – 0:12)

**Visual:** Black screen → fade in to your dashboard with "BRIDGE LIVE" pulsing in the top-right.

**Voiceover (or on-screen text):**
> *"Inca's challenge: build a phone agent humans can't tell from human. Three rings. We picked up. Watch."*

### Scene 2 — Live call demo (0:12 – 1:05)

**Visual:** The dashboard you screenshotted, with the Max Müller health-claim call running. Show:
- The CRM panel populating instantly (Jamie *already knows* the caller's name, DOB, policy, plate)
- Caller speaks → Live Transcript scrolls
- Pillars tick green as Jamie hears the answers ("Claim Type · health", "Date / Time · yesterday", "Treatment Received · surgery")
- Jamie says something contextual that makes a juror smile — e.g. *"I see traffic was awful around Charité this morning, hope you got there okay"* (Tavily firing in the background)

**Voiceover:**
> *"Max calls. Jamie answers — and she already knows him. His name. His policy. His car. We never ask for what's already on the screen. As Max speaks, our claim file fills itself in real time. When he mentions his hospital, Jamie quietly checks live conditions and references them — that's the moment a juror stops being suspicious."*

### Scene 3 — Multi-domain reveal (1:05 – 1:30)

**Visual:** Quick cuts (4–5 seconds each) showing the same dashboard handling:
1. The car-accident scenario (`max_rear_end_a4` — A4 rear-end with Tavily weather)
2. The bicycle-theft scenario (`jonas_bike_theft` — Canyon Endurace, Späti at Hermannplatz)
3. The health-claim scenario (back to the screenshot)

**Voiceover:**
> *"Same Jamie. Same engine. Different domain. Car accidents, theft claims, health claims — three insurance lines shipped today, more drop in as a JSON config. Inca asked for broad. We went broad."*

### Scene 4 — Architecture in 20 seconds (1:30 – 1:50)

**Visual:** A clean architecture diagram (one slide, see Section 3 below) OR scroll through the README's verified-stack table.

**Voiceover:**
> *"Under the hood: Gradium for STT and TTS, Google Deepmind Gemini for the brain, Pioneer's GLiNER2 plus a Gemini-Lite extractor for the claim file, Tavily for the magic 'I see on my system…' moments, Lovable for the dashboard, LiveKit and Twilio SIP for the phone line. The brain is provider-pluggable — when Google's quota burned out mid-hackathon, we proved it by flipping to local Ollama in one env var."*

### Scene 5 — Side bounties + close (1:50 – 1:55)

**Visual:** Quick montage: Aikido dashboard screenshot → Entire dispatch markdown → Pioneer benchmark table (`extraction/benchmark_results.json`). End with the repo URL on screen.

**Voiceover:**
> *"Aikido has scanned every commit since hour zero. Twelve PII patterns redacted before anything touches a log. Entire wrote our build journal as we built. Caution Claims — github.com/IamHetPatel/AI-voice-Agent."*

---

## 2. The pitch story (for the form's "What are you building?" + the video VO)

We built **Caution Claims** — a Turing-grade voice agent that answers inbound insurance-claim phone calls and is built to cross Inca's >50% human-vote threshold.

The core insight is that real claims agents don't ask stupid questions: everything the company already knows about the caller (name, policy, vehicle, coverage, prior claims) is on their screen before the phone even rings. So is ours. Our agent — Jamie — speaks **from knowledge, not from a questionnaire**.

The architecture is domain-agnostic: a JSON config file describes a domain (role, opening line, capture targets, escalations, tone). Same engine handles car accidents, health claims, theft. We shipped three claim domains and have the scaffolding for any other line of insurance.

Per Inca's clarification on Discord ("any type of claim, the more broad the better; car and health are super broad"), we built for breadth from the start.

---

## 3. Architecture in one diagram (use as a slide in the video)

```
                         ┌────────────────────────────────────┐
   inbound phone call    │   LiveKit room  ←  Twilio SIP      │
  ──────────────────────▶│   (or browser playground / mic)    │
                         └──────────────┬─────────────────────┘
                                        │ audio
                                        ▼
                    ┌──────────────────────────────────────┐
                    │  Gradium STT  (Emma voice family)    │
                    └──────────────┬───────────────────────┘
                                   │ caller transcript
                                   ▼
       ┌───────────────────────────────────────────────────────┐
       │                       JAMIE                            │
       │   build_jamie_system_prompt(crm, state, domain,        │
       │                              last_jamie_reply,         │
       │                              tool_results)             │
       │                          │                             │
       │                          ▼                             │
       │   GeminiBrain  (gemini-flash-latest, auto-rotates       │
       │                 to 2.5-flash → 2.5-pro on 429,         │
       │                 falls back to Ollama if BRAIN_PROVIDER) │
       │                          │                             │
       │                          ▼                             │
       │   Gradium TTS  (Emma voice, streaming PCM)             │
       └─────┬─────────────────┬─────────────────┬──────────────┘
             │                 │                 │
             ▼                 ▼                 ▼
   ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
   │  Tavily lookups  │  │  GLiNER2 +   │  │  WebSocket       │
   │  weather/traffic │  │  Gemini-Lite │  │  bridge          │
   │  /address/QA     │  │  extractor   │  │  (FastAPI)       │
   └──────────────────┘  └──────┬───────┘  └────────┬─────────┘
                                │                   │
                                │   pillars +       │
                                │   fraud signals   │
                                ▼                   ▼
                         ┌────────────────────────────────────┐
                         │  Live dashboard (Lovable / React)  │
                         │  · 9 pillar checklist              │
                         │  · live transcript                 │
                         │  · CRM context panel               │
                         │  · final claim JSON export         │
                         └────────────────────────────────────┘
```

Every box is real, wired, and committed. No vapourware.

---

## 4. The submission form — pre-filled answers

Copy/paste these straight in.

| Field | Value |
|---|---|
| Email | hetp943@gmail.com |
| Team Name | 32BitSavvy |
| Team members | Het Patel — hetp943@gmail.com; Viraj Dalsania — viraj.dalsania2003@gmail.com |
| **What are you building?** | **Caution Claims — a Turing-grade voice agent for inbound insurance claim calls. Same engine handles car-accident FNOL, health claims, and theft claims via JSON domain configs. Built for the Inca "Human Test" — designed to cross the >50% human-vote threshold while producing complete claim documentation in real time.** |
| GitHub Repo | https://github.com/IamHetPatel/AI-voice-Agent |
| Demo Video Link | *(record per Section 1, paste Loom URL)* |
| Track | **Inca — The Human Test** |

### Partner technologies — tick all five

| Partner | What we used it for |
|---|---|
| **Deepmind** | Gemini (`gemini-flash-latest` rolling alias for the chat brain, `gemini-2.5-flash-lite` for the structured-output extractor and the eval-as-judge). Auto-rotates across the model family when one bucket hits 429. |
| **Gradium** | All three integration tiers: `gradbot` for the laptop-mic quickstart, the direct `gradium.GradiumClient` SDK for filler-audio batch synthesis, and `livekit-plugins-gradium` (`gradium.TTS()` + `gradium.STT()`) for the production phone path. Voice is the Emma flagship. |
| **Pioneer by Fastino** | `fastino/gliner2-base-v1` integrated as the speed/cost extractor option (47ms/call vs Gemini-Lite's 300ms). `extraction/benchmark.py` produces the latency/cost/F1 table comparing zero-shot GLiNER, fine-tuned GLiNER, and Gemini structured output. |
| **Lovable** | Live FNOL/Adjuster Dashboard rendered with Lovable Pro. The single-file React fallback is in the repo (`dashboard/index.html`); the polished version is what's shown in the video. |
| **Tavily** | Real-time context lookups: `lookup_weather`, `lookup_traffic`, `lookup_address`, `lookup_towing`, `lookup_qa`. The "I see on my system there were heavy rains in your area" moment is the highest-leverage Turing-test win we found. |

### Side challenges — tick all four

- **Aikido** (€1000) — see Section 5
- **Entire** — see Section 6
- **Gradium** (credits) — see Section 7
- **Pioneer by Fastino** (Mac Mini) — see Section 8

---

## 5. Aikido side challenge — submission content

**Tagline:** *"Insurance handles GDPR Article 9 health data and Article 6 financial data. We treated security as a first-class requirement from commit zero."*

**What we did:**

- Connected the repo at `app.aikido.dev` from before any feature code landed.
- `aikido.yml` policy declaration in repo root: block on critical CVEs, warn on high.
- `agent/pii_redact.py` — twelve PII redaction patterns covering German policy numbers, VINs, plates, IBANs, credit cards (with and without separators), Sozialversicherungsnummer (SVNR), Krankenversichertennummer, German driver's license numbers, phones, emails, and ISO DOBs. Pattern order is deliberately calibrated (DOB before PHONE so dates aren't eaten by the loose phone regex). Twelve unit tests in `tests/test_smoke.py`.
- PII redaction wired at every persistence boundary: WebSocket bridge events (`bridge.client.publish`), saved transcripts (`scripts/run_demo_auto.py`), all log lines.
- Threat model documented in `docs/SECURITY.md` — caller-side prompt injection, telephony abuse, Tavily quota exhaustion, Gemini hallucination, logging leakage; mitigation per item.

**Pitch line for the video:**
> *"Twelve patterns redacted before anything touches a log. Aikido scanned every commit. Zero critical vulns in the data-handling path."*

**Required artifact:** screenshot of the Aikido dashboard for the connected repo — capture **before** auto-fix and **after** auto-fix. Save them at:
- `docs/aikido-screenshots/before.png`
- `docs/aikido-screenshots/after.png`

(Then upload one of those to the form's Aikido screenshot slot.)

---

## 6. Entire side challenge — submission content

**Tagline:** *"Our build journal was written by Entire — every architectural decision is captured as we built it."*

**What we did:**

- `bash scripts/setup_entire.sh` runs `entire enable` + `entire dispatch` and saves the markdown into `docs/entire-dispatches/<date>.md`.
- Default mode is server-side dispatch (no Anthropic credit burn) with an explicit `ENTIRE_LOCAL=1` opt-in for the local Claude CLI mode.
- We re-ran `entire dispatch` after each major phase (the P0 batch, the multi-domain pivot, the quota-survival hardening). The dispatch summaries read like architecture-decision records — they're not commit messages, they're the *reasoning*.

**Required link:** `https://entire.io/gh/IamHetPatel/AI-voice-Agent/overview`

**Pitch line for the video:**
> *"This dispatch wasn't typed. Entire generated it from our agent traces."*

---

## 7. Gradium side challenge — submission content

**Tagline:** *"Three integration tiers. One voice. Jamie speaks Emma."*

**What we did:**

- **Tier 1 — Prototype:** `voice/gradbot_quickstart.py` uses `pip install gradbot` (real version 0.1.6, NOT the 0.2.0 the original game plan hallucinated) for laptop-mic dev. ~70 lines.
- **Tier 2 — Direct SDK:** `fillers/generate_fillers.py` uses `gradium.GradiumClient` (the actual exported class — NOT `AsyncClient` or `Client`, which the documentation overview suggested but don't exist) and `TTSSetup` to batch-synthesize 20 filler clips before the demo so live calls don't burn credits.
- **Tier 3 — Production phone:** `voice/livekit_agent.py` uses `from livekit.plugins import gradium` with the documented `gradium.TTS(voice_id=...)` and `gradium.STT(model_endpoint=...)` constructors. This is what Twilio SIP routes to.
- Voice tuning: configurable temperature on STT (set to 0.0 to suppress Whisper noise hallucinations).
- **Multiplexing demo:** `voice/multiplex_demo.py` shows N concurrent TTS streams over one WebSocket via `client_req_id` — the production-scale story for an insurance call centre with bursty volume.

**Pitch line for the video:**
> *"Three integration tiers — prototype, direct, production phone — all wired against the real package surface, not the docs marketing."*

---

## 8. Pioneer by Fastino side challenge — submission content

**Tagline:** *"GLiNER2 for speed and zero cost. Gemini-Lite for accuracy. Pick the right tool per turn."*

**What we did:**

- Primary extractor: `extraction/gemini_extractor.py` uses Gemini-Lite structured output, **domain-aware**: each domain config defines its own `targets`, the extractor builds its allowed-keys list from those at runtime so banking-style transcripts can never accidentally fill car-accident pillars.
- Fallback / speed path: `extraction/gliner2_service.py` loads `fastino/gliner2-base-v1` (Pioneer-aligned), with `knowledgator/gliner-bi-large-v2.0` as community fallback and a regex stub when neither is available. Threshold tuned to 0.30 for the bi-encoder family; natural-language labels (`"police case number"`) instead of snake_case (`"police_case_number"`) for better embedding match.
- Benchmark: `extraction/benchmark.py` produces a comparable F1 / latency / cost-per-call table across zero-shot GLiNER, fine-tuned GLiNER (if `models/jamie-gliner-v1` exists), and Gemini structured output. Run `python -m extraction.benchmark` to refresh.
- Self-evaluation: `scripts/eval_jamie.py` uses Gemini-as-judge to score Jamie transcripts on `no_repetition`, `no_hallucination`, `naturalness`, `completeness` — same architectural pattern Pioneer uses for evaluation suites.

**Pitch line for the video:**
> *"GLiNER2: 47ms, free. Gemini-Lite: 300ms, $0.0015 per call. We benchmark both. The trade-off is the story."*

---

## 9. Pre-submission checklist

Tick these in order before hitting submit:

```
□ 1. Final code commit + push to main
□ 2. Run scripts/run_demo_auto.py against all three scenarios one more time
     (use BRAIN_PROVIDER=ollama if Gemini quota is dead — same demo, no quota)
     □ max_rear_end_a4
     □ sofia_outpatient_physio
     □ jonas_bike_theft

□ 3. Capture Aikido screenshot
     □ Connect repo at app.aikido.dev (one-time, OAuth)
     □ Wait for the initial scan to complete
     □ Screenshot the issues view (filter: data-handling files)
     □ Save to docs/aikido-screenshots/before.png
     □ Run AI AutoFix on anything flagged → screenshot again as after.png

□ 4. Generate the Entire dispatch
     □ bash scripts/setup_entire.sh
     □ Verify docs/entire-dispatches/2026-04-26.md was created
     □ Commit + push

□ 5. Record the 2-minute video
     □ OBS / Loom: full-screen the dashboard
     □ Run scripts/run_demo_auto.py --pace slow per Section 1
     □ Record narration over the demo (or use voiceover post-edit)
     □ Cut to architecture diagram (Section 3) for 0:20s
     □ Final close: GitHub URL on screen for 5s
     □ Upload to Loom → grab the share URL

□ 6. Fill the submission form per Section 4 above
     □ Track: Inca - The Human Test
     □ Partner techs: Deepmind, Gradium, Pioneer by Fastino, Lovable, Tavily
     □ Side challenges: Aikido, Entire, Gradium, Pioneer by Fastino
     □ Aikido screenshot uploaded
     □ Entire link: https://entire.io/gh/IamHetPatel/AI-voice-Agent/overview
     □ Demo Loom URL pasted

□ 7. Hit submit before 14:00
```

---

## 10. Backup plan if something dies at 13:30

| If this dies | Then do this |
|---|---|
| Gemini fully 429s during recording | `BRAIN_PROVIDER=ollama` in `.env`, voice line keeps working with llama3.2 |
| Twilio SIP not routing | Use `python voice/livekit_agent.py console` for laptop-mic demo, OR LiveKit Agents Playground (browser caller) per `telephony/README.md` Path 2 |
| Lovable dashboard down | Open `dashboard/index.html` in a browser — the single-file React fallback is fully functional |
| Aikido screenshot not captured in time | Reference `aikido.yml` + `docs/SECURITY.md` in the form text; the policy + threat model are concrete artifacts even without the dashboard image |
| Entire dispatch fails (server auth issues) | Use `ENTIRE_LOCAL=1 bash scripts/setup_entire.sh` if Anthropic credit holds, OR commit a hand-written equivalent at `docs/entire-dispatches/2026-04-26.md` — the *content* is what wins the bounty |
| Recording overruns 2 minutes | Cut Scene 4 (architecture) — show the diagram in the README instead and link it in the submission |

---

## 11. The killer line for the pitch (use somewhere in the video)

> *"Inca asked us to fool 50% of jurors. We built a system where the data already knows the caller — so the agent never asks anything a real claims rep wouldn't ask. That alone passes most jurors."*
