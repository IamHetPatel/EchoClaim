# Retrieval

Grounds the assistant's coverage answers in the policy corpus instead of generating them.
A coverage question is answered with a retrieved, cited clause. If nothing matches with
confidence, the tool reports low confidence so the agent declines to assert coverage.

## Pipeline

```
corpus (data/policies/*.md)
  -> chunker      structure-first split on German § / Teil markers, token-window fallback
  -> embedder     versioned (model id + dim travel with the vector); content-hash cache
  -> index        Qdrant collection with named vectors (one per embedding version)
  -> retriever    recall, rerank, cited chunks, plus a low-confidence signal
  -> tool         coverage_lookup(query, product_code) returns cited clauses
```

Each chunk keeps the metadata that doubles as its citation and its filter keys:
`clause_id`, `section_path`, `doc_type`, `product_code`, `lang`.

## Backends

Recall runs over one of three interchangeable backends (`RETRIEVAL_BACKEND`):

| Backend | Recall | Needs |
|---|---|---|
| `qdrant` | dense ANN over BGE-M3 vectors | Qdrant server + sentence-transformers |
| `memory-dense` | dense cosine in numpy | sentence-transformers (no server) |
| `lexical` | BM25 over clause text | nothing (stdlib + numpy) |

`auto`, the default, uses Qdrant when it is reachable and falls back to the lexical
backend otherwise. The lexical path tokenizes with stopword filtering and light German
stemming so singular/plural and case variants match. It is deterministic, which is what
makes the evaluation reproducible. The dense path is the real semantic matcher.

Embeddings have two backends (`EMBED_BACKEND`): `sentence-transformers` (BGE-M3) and
`hash` (deterministic, dependency-free) for offline tests and reproducible runs.

## Reranking, and why `auto` is the fast one

Recall is followed by a rerank pass (`RERANK_BACKEND`): `cross-encoder`
(`bge-reranker-v2-m3`) or `lexical`.

`auto` resolves to **lexical**, deliberately. The cross-encoder is a 568M-parameter model
that scores every (query, candidate) pair. Measured on this corpus on CPU:

| Stage | Time |
|---|---|
| BGE-M3 embed + Qdrant ANN | 456 ms |
| `bge-reranker-v2-m3` rerank of 27 candidates | 28,270 ms |
| lexical rerank | 8 ms |

That is 98% of query latency for a large quality gain (nDCG@5 0.32 → 0.80). Worth it
offline; impossible inside a phone call. An earlier version returned the cross-encoder
whenever `sentence_transformers` merely happened to be importable, so installing the
embedding dependency silently put a 28-second rerank in the live voice path. Evaluation
and CI now opt in explicitly; the agent leaves it on `auto`.

On a GPU the same model is roughly 90 ms per 100 pairs, so this is a CPU-serving
constraint, not a property of the model.

## Usage

```bash
# Ingest the corpus. --dry-run stops before Qdrant and writes a manifest that records
# the embedding version; --recreate drops the collection first for a hermetic run.
python -m retrieval.ingest --dry-run
EMBED_BACKEND=hash python -m retrieval.ingest --dry-run     # fully offline
TORCH_DEVICE=cpu EMBED_BACKEND=sentence-transformers \
  python -m retrieval.ingest --recreate                     # real vectors into Qdrant

# Evaluate retrieval quality against the golden set
python -m retrieval.eval                 # precision@k / recall@k / MRR / nDCG
python -m retrieval.eval --k 3 --json

# Compare recall backends on the same golden set
TORCH_DEVICE=cpu python -m retrieval.compare_backends

# The tool the agent calls
python tools/coverage_lookup.py
```

Point ids are derived from `(doc_id, clause_id)` via uuid5, so re-ingesting the same
corpus updates points in place instead of inserting duplicates.

```python
from retrieval.tool import coverage_lookup
result = coverage_lookup("Ist ein Parkschaden in der Vollkasko gedeckt?", product_code="KK-300")
# -> {"summary": "Laut KK-300:§ 6 ...", "citations": [...], "low_confidence": False}
```

## Versioning and migration

Vectors are written under a Qdrant named vector keyed by embedding version (`emb_v1`), and
the embedding model id and dimension are recorded with the index. Because two named
vectors can coexist in one collection, a new embedding model can be introduced with
dual-write plus backfill and an atomic read cutover. That is the basis for zero-downtime
migration.

## Configuration

All settings are environment-overridable. See [config.py](config.py). Common ones:

| Variable | Default | Purpose |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant endpoint |
| `RETRIEVAL_BACKEND` | `auto` | `auto` / `qdrant` / `memory-dense` / `lexical` |
| `EMBED_BACKEND` | `sentence-transformers` | `sentence-transformers` / `hash` |
| `TOP_K_RECALL` / `TOP_K_FINAL` | `50` / `6` | candidates before / after rerank |
| `RERANK_BACKEND` | `auto` | `auto` / `cross-encoder` / `lexical` (see above) |
| `TORCH_DEVICE` | unset | force `cpu` when the GPU cannot hold both models |
| `CORPUS_DIR` | `data/policies` | corpus location |
| `GOLDEN_SET_PATH` | `data/eval/golden_set.jsonl` | evaluation set |

## Tests

```bash
pytest tests/test_retrieval.py tests/test_retrieval_query.py tests/test_retrieval_eval.py
```

These cover chunking, the corpus loader, both embedder backends, lexical recall and
rerank, the `coverage_lookup` tool (including the refusal path), the ranking metrics, and
an end-to-end quality bar. They run offline, with no model download or Qdrant server.
