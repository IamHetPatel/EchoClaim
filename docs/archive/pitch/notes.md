# Speaker notes — EchoClaim · 2-minute pitch

**4 slides · ~43s of slide-time · ~75s for the live demo cut · total = 1:58.**

The slides are intentionally minimal — the demo carries the show. Read the lines below at a normal phone-conversation pace; the auto-advance timing is set to match.

---

## Slide 1 · Title (0:00 – 0:09)

> *"This is **EchoClaim** — voice that understands, claims that move. Our entry to Inca's Human Test."*

Hold for the logo + tagline to land.

---

## Slide 2 · The hook (0:09 – 0:15)

> *"Inca asked us to build a phone agent that fools jurors into voting human. So we built one that **already knows the caller** before they say a word. Watch."*

→ at the arrow, **CUT TO YOUR LIVE DASHBOARD RECORDING**.

---

## DEMO CUT (0:15 – 1:30) · ~75 seconds

This is the meat. Show your dashboard from the screenshot, with the call running:

- The CRM panel populates instantly — the agent already has the caller's name, policy, vehicle, coverage.
- Caller speaks → live transcript scrolls.
- Pillars tick green ("Claim Type", "Date / Time", "Treatment Received"…) as Jamie hears the answers.
- Tavily fires in the background — Jamie casually quotes a real local condition.
- Final claim JSON exports cleanly at the end of the call.

Optional voiceover during the demo (light touch, don't over-narrate):

> *"Jamie answers. She knows the caller's name, policy, vehicle. As Sofia speaks, the claim file fills itself in real time. When she names her hospital, Jamie quietly checks live conditions and references them — that's the moment a juror stops being suspicious."*

End the cut showing the FINAL CLAIM EXPORT panel with the JSON.

---

## Slide 3 · How it works (1:30 – 1:44)

> *"Under the hood, five steps. Twilio and LiveKit carry the call. Gradium does STT and TTS — Emma voice. Gemini is the brain, with CRM and tool results injected on every turn — and it auto-rotates models when Google's free tier dies. Tavily handles the magic 'I see on my system' moments. Pioneer's GLiNER2 plus a Gemini-Lite extractor pull the claim file into the Lovable dashboard. Five partners, all real, all shipped."*

---

## Slide 4 · Beyond the conversation (1:44 – 1:58)

> *"Beyond the conversation itself, four things we built around it. Twelve PII patterns redacted before anything touches a log — insurance is GDPR Article 9 health data. A build journal that captures why every decision was made, not just what changed. Voice that runs in three tiers — laptop, direct SDK, production telephony — all on the same voice. And two extraction lanes: forty-seven milliseconds free on-device for speed, three hundred milliseconds structured-output for accuracy. EchoClaim. github dot com slash IamHetPatel slash AI dash voice dash Agent."*

Hold the closing strip on screen for ~3 seconds with the URL visible.

---

## Auto-advance vs. manual

- Press **`A`** to start auto-advance — the deck times itself per the `data-dur` on each slide. Use this if you want hands-free.
- Or just press **`→`** at each beat. Recommended for the dashboard cut: turn off auto so you can hold slide 2 for as long as the demo runs.

## Logo

The deck draws a stylised SVG approximation of the EchoClaim logo by default. To use your real PNG, save it at:

```
docs/pitch/echoclaim-logo.png
```

The HTML auto-detects it on load and swaps the SVG out — no code change needed.

## Keyboard

| Key | Action |
|---|---|
| `→` / `Space` | Next slide |
| `←` | Previous slide |
| `A` | Toggle auto-advance |
| `F` | Toggle fullscreen |
| `?` | Hide / show the help hint |
| `Esc` | Cancel auto-advance |
