# Entire — agentic-build provenance

`entire enable` registers the repo; `entire dispatch` captures the reasoning trace from your latest agent-driven changes (Cursor / Claude Code / Codex). **No API key required** — Entire is local-first.

## One-shot setup

```bash
bash scripts/setup_entire.sh
```

That script installs the CLI, runs `entire enable`, and runs the first `entire dispatch` capture. Re-run `entire dispatch` after every major commit (or wire it into a post-commit git hook) so reasoning stays current.

## Manual setup

```bash
# Once per laptop:
curl -fsSL https://entire.io/install.sh | bash

# Once per repo:
cd /path/to/AI-voice-Agent
entire enable

# After each meaningful commit / agent run:
entire dispatch
```

That registers the repo with Entire so every commit-time reasoning trace from Cursor / Claude Code / Codex is captured. The submission story is:

> "Our build process itself is AI-documented. Every architectural decision our agents made while building Jamie is captured by Entire — version-controlled *why* alongside the *what*."

## Architectural decisions worth capturing

If the team uses agents to land changes, write the prompts so the *reasoning* is rich enough for Entire to harvest. Examples:

- *"Use `fastino/gliner2-base-v1` for extraction over `knowledgator/gliner-bi-large-v2.0` because Pioneer is built around Fastino's GLiNER2 family — we win the Pioneer bounty narrative AND get a 5–8% F1 lift on insurance-domain entities. Tradeoff: weights are larger; we ship the base variant, not large."*
- *"Run filler audio injection any time we expect tool-call latency >400ms — Tavily round-trip averages 600–900ms; without filler, perceived latency crosses the uncanny-valley threshold."*
- *"Build the bridge as a separate FastAPI process rather than in-process so the dashboard survives an agent crash. Cost: one extra port; benefit: judges keep seeing live data even if the LLM hangs."*

## Submission narrative for the Entire prize

When the judges look at the repo, they should see Entire-generated reasoning artifacts that read like a real architecture doc. To make that happen:

1. After every meaningful commit, run `entire dispatch`.
2. Paste the most useful dispatch summaries into the README's `## Build journal` section verbatim.
3. In the demo, open the GitHub repo and say: *"Our entire technical documentation was written by Entire — every decision our agents made while building Jamie is version-controlled there, with the reasoning, not just the diff."*

That meta-narrative — an AI building an AI that passes as human, with its own reasoning transparently captured — is a genuinely compelling story for the judges.
