# Critical path — 17 hours to submission

You started this doc at **19:30**, deadline **14:00 next day** (= ~18.5h elapsed). Pitch video probably eats 2–3 of those. Net working time for code = ~12h. So we cut everything that isn't in the demo or the bounty narrative.

## What MUST work in the demo (non-negotiable)

1. **Auto-runner plays a scripted call end-to-end** with Gemini, GLiNER, Tavily, the dashboard updating live.  → Already works.
2. **Jamie's quality scores are good** — `eval_jamie.py` shows ≥7/10 on no_repetition, no_hallucination, naturalness.  → In progress; the asked-pillars fix that just landed should move repetition above 7.
3. **Voice actually comes out of the laptop in Jamie's voice** — Gradbot quickstart against the laptop mic.  → Need to validate; gradbot needs Python ≥3.12 (you have 3.14, should work).
4. **Lovable dashboard looks like enterprise insurance software**, not a hack.  → Single-file React works as fallback; regen via Lovable using `dashboard/lovable_prompt.md` if time allows.

## What's NICE-to-have (drop if behind schedule)

- Pioneer fine-tune of GLiNER2 with synthetic data (the bounty narrative still works with zero-shot — the F1 table can use the zero-shot weights).
- Twilio SIP wired to a real phone (you said laptop-mic only is fine).
- Multi-juror automated Turing eval with Anthropic (the Anthropic key is dead, use the Gemini-judge `eval_jamie.py` instead — it's already running and giving signal).

## Hour-by-hour budget

| Time   | Task                                    | Status | Ship criteria |
|--------|-----------------------------------------|--------|---------------|
| 19:30  | Repetition fix (asked-pillars)          | DONE   | smoke tests pass, eval rerun shows ≥7/10 |
| 20:00  | Pull, re-run `run_demo_auto.py`, eval   | NEXT   | both transcripts in `--all` show climbing scores |
| 20:30  | Tighten Tavily trigger heuristics       |        | Tavily fires at most once per location, not per turn |
| 21:00  | Voice loop — Gradbot laptop-mic         |        | you hear Jamie reply through speakers |
| 22:30  | Lovable dashboard regen + screenshots   |        | dashboard/index.html or lovable build looks enterprise |
| 23:30  | Aikido screenshots (before/after)       |        | docs/aikido/{baseline,fixed}.png saved |
| 00:00  | Pioneer benchmark (zero-shot is fine)   |        | extraction/benchmark_results.json updated |
| 00:30  | `entire enable && entire dispatch`      |        | docs/build_journal.md has 2-3 dispatch summaries |
| 01:00  | Full README polish, README → judges     |        | bounty section names every artifact |
| 02:00  | Sleep                                   |        | — |
| 06:00  | Wake, fresh `eval_jamie.py --all`       |        | 3+ transcripts, all ≥7/10 across the board |
| 07:00  | Pitch video script                      |        | docs/pitch.md w/ 3-min beat sheet |
| 09:00  | Pitch video record + edit               |        | mp4 in repo or linked |
| 11:30  | Final commit + push                     |        | everything in main branch |
| 13:00  | Buffer / hot-fix any submission issue   |        | — |
| 14:00  | DEADLINE                                |        | — |

## Pitch video beat sheet (3 minutes)

We pre-write this so when 09:00 rolls around the recording goes in one take.

- **0:00–0:20** — Hook: the call starts. Show the dashboard. "Jamie just answered the phone. Watch."
- **0:20–1:30** — Live call playback (use `run_demo_auto.py --pace slow`). Highlight: she knows the caller's name, doesn't ask for the policy number, and references real road conditions from Tavily.
- **1:30–2:00** — Cut to the dashboard. The 15 pillars fill in real-time. Final claim JSON exports.
- **2:00–2:20** — Aikido tab: clean security report. "GDPR Article 9 health data — security wasn't optional from commit zero."
- **2:20–2:45** — Pioneer benchmark: GLiNER2 vs Gemini structured. "48ms, free, 89% F1 — replaces a $0.018/call structured-output call."
- **2:45–3:00** — Entire dispatch summary. "Our build itself was AI-documented. Every decision Jamie's developers made is captured here."

## What's deferred or canceled

- **Twilio SIP / phone number** — laptop mic only for the demo.
- **Anthropic juror bot** — credit dead, replaced with `eval_jamie.py` (Gemini judge).
- **Pioneer fine-tune** — the F1 narrative works with zero-shot GLiNER2, since the bounty story is "free, fast, fine-tunable" and we're shipping the fastino model that Pioneer fine-tunes.
- **Multiplexing demo** — we have the script, but if Gradbot laptop-mic eats all the voice time, we drop the multiplex demo from the pitch and keep it as the README "production scale" claim.

## If you're falling behind at any checkpoint

Cut in this order:
1. Pioneer fine-tune → keep zero-shot
2. Lovable regeneration → keep single-file React
3. Multi-juror eval → keep one Gemini-judge run
4. Aikido AI AutoFix run → keep the baseline-scan screenshot

Never cut:
- The auto-runner working
- Jamie sounding like Jamie
- The dashboard updating live during the demo
