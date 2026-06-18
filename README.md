# EchoClaim

A phone-based first-notice-of-loss (FNOL) claims-intake assistant for a German motor
insurer. The assistant — *Jamie* — answers an inbound call, works from what the insurer
already knows about the caller, gathers the remaining claim details conversationally, and
documents everything as structured data in real time. Coverage answers are grounded in the
policy wording and cited, and the conversation and the structured extraction run in
parallel so the dialogue stays natural.

## Architecture

```
Inbound call ─▶ Gradium STT ─▶ GeminiBrain ─▶ Gradium TTS ─▶ Caller
                                  │  (Gemini 2.5 Flash, known-context injection,
                                  │   function-calling tools, model fallback chain)
                                  ▼
                       transcript fans out in parallel
                                  ▼
        GLiNER2 extractor ─▶ 15 claim pillars + 5 fraud signals ─▶ WS bridge ─▶ dashboard
```

The live conversational loop is supported by a **retrieval** subsystem: policy and
regulation documents are chunked structure-first (on German `§`/`Teil` markers), embedded,
and indexed; a `coverage_lookup` tool retrieves and cites the exact clause before Jamie
states any coverage fact, and refuses to assert coverage when there is no confident match.

## Stack

| Layer | Component |
|---|---|
| Speech | Gradium STT / TTS |
| Conversation | Gemini 2.5 Flash, with automatic fallback to 2.0 / 1.5 Flash |
| Context & tools | Known-context CRM injection; Tavily real-time lookup; `coverage_lookup` retrieval |
| Extraction | `fastino/gliner2-base-v1` (fine-tuned), benchmarked against LLM structured output |
| Retrieval | BGE-M3 embeddings + `bge-reranker-v2-m3` + Qdrant, with a dependency-free BM25 fallback for offline use |
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
bridge/        FastAPI WebSocket bridge to the dashboard
dashboard/     React dashboard
data/          Mock CRM profiles, the policy corpus, and the retrieval golden set
tests/         Unit + adversarial conversation tests
scripts/       run_demo_text.py and other operator commands
```

## Quick start (text mode — no telephony, no API keys)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/run_demo_text.py --crm max_mueller
```

Runs Jamie against typed input with the GLiNER2 extractor live and the dashboard updating
over WebSocket. Coverage questions trigger `coverage_lookup`, which cites the matching
policy clause. No paid infrastructure required.

For the voice loop and Twilio SIP setup, see [telephony/README.md](telephony/README.md).

## Retrieval

The retrieval subsystem (`retrieval/`) runs locally with no paid services — see
[retrieval/README.md](retrieval/README.md). Quick checks:

```bash
python -m retrieval.ingest --dry-run     # chunk + embed the corpus, write a manifest
python -m retrieval.eval                 # precision@k / recall@k / MRR / nDCG
```

Retrieval quality is measured against a golden set of coverage questions mapped to the
clause each should return (`data/eval/golden_set.jsonl`). The lexical backend and the
hash embedder are deterministic, so the metrics are reproducible.

## Status

Built: the voice loop, known-context injection, GLiNER2 extraction with a benchmark, the
tool layer, the dashboard, and the retrieval subsystem (structure-aware ingest, a
Qdrant named-vector index, query + rerank, the cited `coverage_lookup` tool, and the
ranking-metric evaluation).

Next: an LLMOps layer (versioned prompt registry, LLM-judge groundedness scoring,
PII-redacted trace logging, a CI eval gate, and drift monitoring) and zero-downtime
embedding-model migration. The retrieval index already stores vectors under named
versions so two embedding models can coexist, which is what the migration builds on.

## License

See [LICENSE](LICENSE).
