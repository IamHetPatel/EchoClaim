# EchoClaim

A phone-based first-notice-of-loss (FNOL) claims-intake assistant for a German motor
insurer. The assistant, Jamie, answers an inbound call, works from what the insurer
already knows about the caller, gathers the remaining claim details in conversation, and
writes everything down as structured data while the call is still going. Coverage answers
are grounded in the policy wording and cited. The conversation and the structured
extraction run in parallel so the dialogue stays natural.

## Architecture

```
Inbound call -> Gradium STT -> GeminiBrain -> Gradium TTS -> Caller
                                  |  (Gemini 2.5 Flash, known-context injection,
                                  |   function-calling tools, model fallback chain)
                                  v
                       transcript fans out in parallel
                                  v
        GLiNER2 extractor -> 15 claim pillars + 5 fraud signals -> WS bridge -> dashboard
```

A retrieval subsystem backs the conversation. Policy and regulation documents are chunked
on German `§`/`Teil` markers, embedded, and indexed. A `coverage_lookup` tool fetches and
cites the exact clause before Jamie states any coverage fact, and reports low confidence
(so Jamie declines to answer) when nothing matches well.

## Stack

| Layer | Component |
|---|---|
| Speech | Gradium STT / TTS |
| Conversation | Gemini 2.5 Flash, with automatic fallback to 2.0 / 1.5 Flash |
| Context & tools | Known-context CRM injection; Tavily real-time lookup; `coverage_lookup` retrieval |
| Extraction | `fastino/gliner2-base-v1` (fine-tuned), benchmarked against LLM structured output |
| Retrieval | BGE-M3 embeddings, `bge-reranker-v2-m3`, Qdrant, plus a dependency-free BM25 fallback for offline use |
| Telephony | LiveKit rooms, Twilio SIP |
| Services | FastAPI WebSocket bridge, React dashboard |
| Privacy | PII redaction on transcripts and logs |

## Repository layout

```
agent/         System prompt, claim-state tracker, Gemini client
voice/         LiveKit + Gradium production voice loop (and a mic-only quickstart)
telephony/     Twilio SIP / LiveKit room glue
extraction/    GLiNER2 microservice + benchmark vs. LLM structured output
tools/         Real-time lookups exposed as function calls (Tavily, coverage_lookup)
retrieval/     RAG over the policy corpus: chunking, embedding, index, retriever, eval
llmops/        Prompt registry, LLM judge, CI eval gate, trace logging, drift monitor
bridge/        FastAPI WebSocket bridge to the dashboard
dashboard/     React dashboard
data/          Mock CRM profiles, the policy corpus, and the retrieval golden set
tests/         Unit + adversarial conversation tests
.github/       CI: test suite, and the eval gate that blocks quality regressions
scripts/       run_demo_text.py and other operator commands
```

## Quick start (text mode, no telephony, no API keys)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/run_demo_text.py --crm max_mueller
```

This runs Jamie against typed input with the GLiNER2 extractor live and the dashboard
updating over WebSocket. Coverage questions trigger `coverage_lookup`, which cites the
matching policy clause. No paid infrastructure is needed.

For the voice loop and Twilio SIP setup, see [telephony/README.md](telephony/README.md).

## Retrieval

The retrieval subsystem (`retrieval/`) runs locally with no paid services. See
[retrieval/README.md](retrieval/README.md). Quick checks:

```bash
python -m retrieval.ingest --dry-run     # chunk + embed the corpus, write a manifest
python -m retrieval.eval                 # precision@k / recall@k / MRR / nDCG
```

Retrieval quality is measured against a golden set of coverage questions, each mapped to
the clause it should return (`data/eval/golden_set.jsonl`). The lexical backend and the
hash embedder are deterministic, so the metrics are reproducible.

## Evaluation and CI

Two workflows run in CI. `tests.yml` runs the unit suite on the offline paths (BM25
backend, hash embedder) — no model download, no server, no API key. `llm-eval.yml` stands
up Qdrant, ingests the committed corpus, and runs the eval gate, which fails the build if
a gated metric regresses past its tolerance band. See [llmops/README.md](llmops/README.md).

Retrieval quality is measured against a golden set of caller questions, each mapped to
the clause it should return (`data/eval/golden_set.jsonl`). The set is deliberately
adversarial: most queries are phrased the way a caller would speak rather than the way
the clause is written, and the corpus carries near-miss distractors (three different
deductible clauses, two disagreeing territorial-scope clauses, three exclusion clauses
that all mention racing). Measured over 32 queries against a live Qdrant:

| Recall backend | precision@5 | recall@5 | MRR | nDCG@5 |
|---|---|---|---|---|
| BM25 lexical | 0.094 | 0.359 | 0.314 | 0.323 |
| BGE-M3 + `bge-reranker-v2-m3` | 0.219 | 0.839 | 0.805 | 0.798 |

Reproduce with `python -m retrieval.compare_backends`. The gap is the point of the dense
stack: BM25 cannot connect a caller saying "gegen einen Hirsch gefahren" to a clause that
says "Zusammenstoß mit Haarwild". Four queries still miss at k=5, which is deliberate —
a saturated eval cannot detect a regression.

## Status

Built: the voice loop, known-context injection, GLiNER2 extraction with a benchmark, the
tool layer, the dashboard, the retrieval subsystem (structure-aware ingest, a Qdrant
named-vector index, query plus rerank, the cited `coverage_lookup` tool, ranking-metric
evaluation), and the LLMOps layer (prompt registry, LLM-judge groundedness, the CI eval
gate, PII-redacted trace logging, drift monitoring).

Not yet done: zero-downtime embedding-model migration. The index already stores vectors
under named versions so two embedding models can coexist, which is what the migration
builds on, but the introduce / dual-write / backfill / shadow-eval / cutover / rollback
sequence is not implemented or rehearsed. Drift monitoring is implemented and unit-tested
but has not run over a production trace volume.

## License

See [LICENSE](LICENSE).
