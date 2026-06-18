# EchoClaim — pitch deck

Tight 4-slide deck. The video is **mostly demo**; the slides are book-ends + a quick stack/bounty summary.

```
Slide 1  Title                  ~9s
Slide 2  Hook (cut to demo)     ~6s
─────── DASHBOARD RECORDING ─── ~75s
Slide 3  Stack / how it works  ~14s
Slide 4  Side bounties + URL   ~14s
                             ── 1:58 total
```

## Use your real logo

Save your EchoClaim PNG at:

```
docs/pitch/echoclaim-logo.png
```

The deck auto-swaps the built-in SVG fallback for the PNG when it loads.

## Open + record

```bash
open -a "Google Chrome" docs/pitch/index.html
# Press F → fullscreen
# Press A → start auto-advance, or use → to drive manually
```

### Recording recipe (Mac, ~30 min)

1. **Two windows ready:**
   - Window A: deck in Chrome, fullscreen
   - Window B: dashboard (your screenshot view) + a terminal running `python scripts/run_demo_auto.py --scenario max_rear_end_a4 --pace slow`
2. **Start QuickTime → File → New Screen Recording → record entire screen.**
3. Show the deck. Press `→` to play slides 1 then 2. (~15 s)
4. `Cmd+Tab` to the dashboard window. Run the auto-demo. Let it play ~75 s.
5. `Cmd+Tab` back to the deck. Press `→` to advance to slide 3, then 4. (~28 s)
6. Stop recording on slide 4.
7. Edit head/tail in iMovie. Export 1080p MP4. Upload to Loom.

### If Gemini quota is dead during recording

```bash
echo "BRAIN_PROVIDER=ollama" >> .env
ollama serve &
ollama pull llama3.2
# Re-run the auto-demo; voice loop now runs on the local model.
```

## Files

| File | Purpose |
|---|---|
| `index.html` | The deck. Open in Chrome, fullscreen, record. |
| `notes.md` | Speaker notes — what to say over each slide, with timing. |
| `README.md` | This. |
| `echoclaim-logo.png` | Your real logo (drop here, auto-swaps). |

## Speaker notes are timed

`notes.md` matches the slide durations exactly. If you turn on auto-advance and read the lines at a natural phone-conversation pace, the deck stays synced.

## Backup plan if anything wobbles

| If… | Then… |
|---|---|
| Auto-advance gets ahead of voiceover | Press `Esc`, drive manually |
| Demo runs over | Skip slide 3, jump straight to slide 4 |
| Gemini dies live | `BRAIN_PROVIDER=ollama` — voice still works |
| Logo PNG isn't ready | The SVG fallback ships fine; replace later |
