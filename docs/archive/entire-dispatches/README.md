# Entire dispatches

Each `<date>.md` file in this directory is the output of an
`entire dispatch` run — a markdown summary of agent-driven changes
since the previous capture.  Together they form the **Build journal**
the README links to and the artifact the Entire bounty pitch points
at.

## Capture flow

```bash
# Once per machine (idempotent):
bash scripts/setup_entire.sh

# After each meaningful commit (or end-of-session):
entire dispatch --since 24h > docs/entire-dispatches/$(date +%Y-%m-%d).md
git add docs/entire-dispatches/
git commit -m "entire: dispatch $(date +%Y-%m-%d)"
git push
```

## What a good dispatch captures

The dispatch is only useful if the agent prompts that produced the
commits were rich enough to leave reasoning behind.  Examples of
prompts that produce great `entire dispatch` output:

- *"Use `urchade/gliner_small-v2.1` for fine-tuning over the 530M
  bi-large because the small variant runs ~3.5× faster per step on
  M-series MPS, and the F1 lift from fine-tuning will more than
  compensate for the smaller zero-shot baseline.  Tradeoff: smaller
  models are more sensitive to dataset noise, so we'll generate ≥30
  synthetic transcripts before training."*

- *"Switch the LLM hop from livekit-plugins-google to
  livekit-plugins-openai pointed at Ollama — Gemini's per-day token
  bucket is exhausted on this project key for the next ~18h, and the
  Ollama path keeps the demo alive without quota anxiety.  Tradeoff:
  llama3.2 mangles OpenAI-style tool-call JSON, so we strip the
  function tools and fire Tavily heuristically instead."*

The dispatch reads these decisions out of the commit history's
reasoning traces (left there by Cursor / Claude Code / Codex) and
turns them into the architecture-decision-record style markdown that
sits in this folder.

## Why this matters for judging

Without committed dispatches, the `.entire/` directory looks
abandoned.  With committed dispatches, judges can `git clone` the
repo, open `docs/entire-dispatches/`, and read the actual
decision-by-decision narrative of how the system was built — exactly
the meta-story the Entire bounty rewards.
