# LLMOps

Versioned prompts, an eval gate in CI, PII-redacted trace logging, and drift monitoring.

```
prompt_registry.py     versioned + content-hashed prompts (semver, exactly one active)
judge.py               LLM-as-judge: groundedness / faithfulness / correctness
groundedness.py        end-to-end harness: retrieve -> answer -> judge
extraction_eval.py     extraction F1 of the live extractor, reusing extraction/benchmark
eval_gate.py           run the metrics, fail CI on regression vs baseline
logging_middleware.py  trace(): per-turn PII-redacted log (prompt ref, citations, scores)
drift_monitor.py       rolling drift report from the trace log
```

## What is different from classic ML CI

You cannot gate on exact-match assertions when the output is probabilistic. So the gate
compares **eval metrics and an LLM judge** against a committed baseline, and is kept
non-flaky by three things: a frozen eval set, temperature 0 on every model call, and
explicit tolerance bands (`eval_gate.TOLERANCES`).

Four metrics are gated:

| Metric | Source | Tolerance |
|---|---|---|
| `precision@k` | `retrieval.eval` over the golden set | 0.02 |
| `ndcg@k` | `retrieval.eval` over the golden set | 0.02 |
| `groundedness` | `llmops.groundedness` (retrieve → answer → judge) | 0.05 |
| `extraction_f1` | `llmops.extraction_eval` over the benchmark set | 0.02 |

Retrieval is deterministic by construction, so it gets tight bands. Groundedness is a
sampled LLM score, so it gets a wider one.

## Unmeasurable is not passing

If the judge has no reachable backend, or the extractor will not load, that metric is
**absent** from the run and reported with the reason it could not be measured. It is
never filled in with a neutral passing value:

```
current: { "precision@5": 0.2188, "ndcg@5": 0.7984 }
  ! groundedness NOT MEASURED -> JudgeUnavailable: GOOGLE_API_KEY is not set
```

Under `--strict` — how CI runs it — a gated metric that could not be measured fails the
build. A gate that substitutes 1.0 for a metric it did not compute is a gate that always
passes, which is worse than no gate, because it reads as a green check.

## Prompt registry

Prompts are YAML artifacts under `prompts/`, each with a semver and a content hash.
`registry.get("jamie_system")` raises unless **exactly one** version is marked active, so
a behaviour change is always attributable to a specific prompt hash rather than to an
unlogged edit. Reference form: `jamie_system@1.0.0+6b1a8da455ca`.

To change a prompt: add `jamie_system.v1.1.0.yaml` with `active: true`, set `active: false`
on the previous file, and let the gate run before it merges.

## Local use

```bash
# Retrieval metrics only — no key, no model, no server.
python -m llmops.eval_gate --skip-groundedness --skip-extraction

# The full gate. Needs a judge backend and a built index.
export JUDGE_BACKEND=ollama JUDGE_MODEL=llama3.2:latest   # or gemini + GOOGLE_API_KEY
python -m llmops.eval_gate --update-baseline              # first time
python -m llmops.eval_gate                                # gate (CI runs this --strict)

python -m llmops.groundedness --sample 8                  # inspect judge output directly
python -m llmops.drift_monitor --window 50                # drift from logs/traces.sqlite
```

## Judge backends

`JUDGE_BACKEND` selects `gemini` (default) or `ollama`. Both run at temperature 0.

The judge quality bound matters when reading the number: a small local model
(llama3.2:3b) separates a grounded answer from a hallucinated one, but its *faithfulness*
score does not discriminate reliably. Use it for a local signal; CI runs the Gemini judge
via the `GOOGLE_API_KEY` repository secret.

## Trace logging and drift

`trace()` wraps a model call and writes one row per turn — prompt ref, retrieved clause
ids, response, latency, top rerank score — through `agent.pii_redact.redact`, so raw PII
never reaches disk. `drift_monitor` reads those rows back and compares a recent window
against a reference window on mean groundedness and on the PSI of the retrieval score
distribution. PSI usually moves first: the corpus or the embedding version shifts under
the agent before groundedness visibly degrades.

The monitor returns nothing until there are `2 * window` traces. That is "not enough data
to compare", which is a different state from "no drift", and it is reported as such.
