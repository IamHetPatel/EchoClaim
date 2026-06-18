# Sequential build runbook — one layer at a time

> "Don't try to set everything at once. Order matters."
> — paraphrasing the user's experience advice that this runbook is built around.

Each step has three parts:

1. **Verify** — prove the layer below works in isolation
2. **Build** — wire the new layer onto what's already proven
3. **Checkpoint** — a one-line success criterion you have to hit before moving on

If a checkpoint fails, stop. Fix the layer you just built. Don't add the next thing on top of broken plumbing.

---

## Step 0 · Foundation (already done)

Everything below assumes:

- `python3 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt` (succeeds — gradbot 0.1.6 is real, not 0.2.0)
- `cp .env.example .env` and fill keys as you have them
- `python scripts/verify_keys.py` shows ✓ Tavily and ✓ Gemini at minimum

**Checkpoint:** `verify_keys.py` shows at least `✓ Gemini` and `✓ Tavily` green.

---

## Step 1 · LiveKit (working audio path)

**Goal:** prove a LiveKit room can carry audio between your browser and a worker process. No Jamie yet — just plumbing.

### Verify
- `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` set in `.env`
- LiveKit project provisioned at https://cloud.livekit.io

### Build
```bash
# install if not present
pip install "livekit-agents[gradium]>=1.4,<2.0"

# generate a tiny "echo" worker — repeats whatever it hears
livekit-agents create echo_test
# or use the example from the LK docs: agents.JobContext + ctx.room.local_participant
```

For laptop-mic-only mode you don't even need that — just connect the browser playground to your room URL and confirm you hear yourself echoed.

### Checkpoint
You speak into your laptop mic, the browser playground plays it back. Audio path proven.

---

## Step 2 · Gradium (Jamie's voice, no brain yet)

**Goal:** Gradium TTS speaks a hardcoded sentence in Jamie's voice. No Gemini, no STT, just text → audio out.

### Verify
- `GRADIUM_API_KEY` set
- `GRADIUM_VOICE_ID` set (from studio.gradium.ai → Voices → Copy ID)
- `python scripts/verify_keys.py` shows `✓ Gradium GradiumClient constructed OK`

### Build
The simplest test — a 4-line script using the **real** `GradiumClient` API (not the bogus `AsyncClient` we had before):

```python
import asyncio, os
from gradium import GradiumClient, TTSSetup
async def speak():
    c = GradiumClient(api_key=os.environ["GRADIUM_API_KEY"])
    setup = TTSSetup(voice_id=os.environ["GRADIUM_VOICE_ID"], output_format="wav")
    stream = await c.tts_stream(setup, "Hi, this is Jamie from Vorsicht claims.")
    with open("/tmp/jamie_test.wav", "wb") as f:
        async for chunk in stream.iter_bytes():
            f.write(chunk)
asyncio.run(speak())
```

Then `afplay /tmp/jamie_test.wav` (macOS).

The pre-built filler audio comes from this same path — once Step 2 works, run `python fillers/generate_fillers.py` to bake the 20 filler clips.

### Checkpoint
You hear Jamie speak the test sentence. Voice timbre is "claims rep, slightly overworked, warm" — not robotic. If she sounds wrong, swap `voice_id`.

---

## Step 3 · Gemini (the brain talks back, text-only)

**Goal:** Gemini 2.5 Flash plays Jamie based on the system prompt. Text in, text out, no voice yet.

### Verify
- `verify_keys.py` shows `✓ Gemini` (auto-probes 2.5 → 2.0 → 1.5 if your `.env` model name fails)
- `.env` has `GEMINI_MODEL=gemini-2.5-flash`

### Build
```bash
# terminal 1 — the bridge fan-out
uvicorn bridge.server:app --port 8765 --reload

# terminal 2 — open dashboard/index.html in your browser

# terminal 3 — the text-mode conversation
python scripts/run_demo_text.py --crm max_mueller
```

Type as the caller. Watch the dashboard's transcript panel + 15-pillar checklist update live.

### Checkpoint
- Jamie greets you using "Max" without you typing a name
- She doesn't ask for the policy number, plate, or VIN (Known-Context working)
- 5+ pillars tick off the checklist after a 4-turn conversation
- The fraud risk gauge moves if you mention "I noticed it three weeks ago"

---

## Step 4 · Twilio (skip for now)

You chose laptop-mic only for the demo, so skip this step. The runbook in `telephony/README.md` is ready when you want to point an actual phone number at the LiveKit room. Don't burn time on this if you're solo — the laptop-mic Gradbot demo + the Lovable dashboard is plenty for the Inca pitch.

If you change your mind later: ask INCA on Slack for their pre-provisioned number first; only buy a Twilio number if INCA can't give you one.

---

## Step 5 · Tavily (Jamie's invisible look-ups)

**Goal:** Jamie hears a location, invisibly looks up real weather, and quotes it back. This is the highest-leverage Turing trick.

### Verify
- `verify_keys.py` shows `✓ Tavily search returned 1 result`

### Build
Already wired in `tools/tavily_lookup.py`. The text-demo runner in Step 3 has rule-based triggers (mentions "A4", "Köln", etc. → fires `tavily_lookup_weather` automatically). To upgrade, port this to Gemini function-calling so Jamie decides when to look something up. That's a one-hour task once Step 3 is solid; do it before you switch to voice.

### Checkpoint
Type "I crashed on the A4 near Köln-Ost" → see a `tool_call` event appear in the dashboard's Tool Calls panel within ~2 seconds → Jamie's next reply references the actual weather. Juror impossible-to-tell moment.

---

## Step 6 · Fastino / Pioneer (extraction → Mac Mini bounty)

**Goal:** the GLiNER2 extractor populates the 15 pillars more accurately than the regex stub, and you have a benchmark table to show.

### Verify
- Pioneer / Fastino account active on their site
- `pip install gliner` succeeded (already in requirements.txt)

### Build
1. Pull weights: `python -c "from gliner import GLiNER; GLiNER.from_pretrained('fastino/gliner2-base-v1')"` once — caches them locally so subsequent runs are instant.
2. Run `python -m extraction.gliner2_service` — should print `mode: gliner` (not `stub`).
3. Optional: log into the Pioneer dashboard, generate ~200 synthetic insurance-claim training examples, fine-tune, and replace the model name in `gliner2_service.py` with your fine-tuned ID.
4. Run `python -m extraction.benchmark` — produces the latency / cost / F1 table for the bounty pitch.

### Checkpoint
Benchmark output shows GLiNER2 ≥ 0.85 F1 at <100ms per call. Even zero-shot you'll beat the regex stub's 0.44 by a wide margin. The bounty story is "free, fast, fine-tunable — vs. $0.018/call Gemini structured output."

---

## Step 7 · Aikido + Entire (polish, narrative)

These run alongside everything above but are usually best touched last so they reflect the actual final state.

### Aikido (€1000)
- App.aikido.dev → repo connected (already done)
- Run AI AutoFix on any flagged dependency vulns
- Take three screenshots: pre-fix dashboard / post-fix dashboard / CI gate showing aikido check
- Add the screenshots to `docs/aikido/` and reference them in the README's bounty section

### Entire
```bash
bash scripts/setup_entire.sh
```
Then after every meaningful commit, run `entire dispatch`. Paste the best summaries into a `## Build journal` section in the README.

### Checkpoint
- Aikido report screenshot saved
- README has at least one Entire-generated dispatch summary copy-pasted in
- Both bounty narratives have a one-line pitch in the README's bounty section

---

## What "done" looks like

By the time you're at the judging table:

- [ ] You can demo Jamie speaking via Gradium voice (laptop mic in → mic out)
- [ ] Lovable / single-file dashboard fills in the 15 pillars live
- [ ] Tavily look-up demo lands the "she's checking real systems" moment
- [ ] Aikido screenshot pinned in the README
- [ ] At least 2 Entire dispatch summaries in the README
- [ ] Pioneer benchmark table in the README
- [ ] `tests/juror_bot.py` ran at least once with stub-mode jurors and shows the harness working — even without ANTHROPIC_API_KEY

That's the whole stack on its feet. Now ship.
