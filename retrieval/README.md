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

Recall is followed by a rerank pass (`RERANK_BACKEND`): `none`, `lexical`, or
`cross-encoder` (`bge-reranker-v2-m3`).

`auto` resolves to **`none`** — keep the recall model's ordering — on measurement. The cross-encoder is a 568M-parameter model
that scores every (query, candidate) pair. Measured on this corpus on CPU:

| Stage | Time (CPU, 27 candidates) |
|---|---|
| BGE-M3 embed + Qdrant ANN (warm) | 16 ms |
| lexical rerank | 0.5 ms |
| `bge-reranker-v2-m3` rerank, steady state | 2,776 ms |
| `bge-reranker-v2-m3` first call (torch warmup) | 5,182 ms |
| `bge-reranker-v2-m3` model load, one-off | 3,146 ms |

That is over 99% of query latency. Measure warm: an earlier figure of ~28 s was a cold
process, and folded model load and torch warmup into the first call.

Quality over the 32-query golden set with dense recall:

| rerank | MRR | nDCG@5 | ms/query |
|---|---|---|---|
| none (recall order) | 0.6953 | 0.7145 | 0.2 |
| lexical | 0.6120 | 0.6426 | 0.5 |
| TinyBERT-L-2 (4M, EN) | 0.3031 | 0.3167 | 22.7 |
| MiniLM-L-6 (22M, EN) | 0.3328 | 0.3436 | 221.1 |
| `bge-reranker-v2-m3` (568M, multilingual) | 0.8047 | 0.7984 | 2776.4 |

Three conclusions. **Lexical reranking is worse than none** — it discards the dense
model's ordering for keyword overlap, which is what fails on paraphrases; `auto` used to
return it. **English-only cross-encoders are not a shortcut** — the small ms-marco models
roughly halve MRR on German, landing below no reranking at all; language coverage, not
size, was the constraint. **The multilingual cross-encoder earns its +0.11 MRR and cannot
sit in a phone call.**

So `auto` resolves to `NoOpReranker`, and the cross-encoder is opt-in. On a GPU the same
model is roughly 90 ms per 100 pairs, so this is a CPU-serving constraint, not a property
of the model.

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
the model id and dimension are recorded with the index. Two named vectors coexist on one
point, so a new model can be built up while the old one keeps serving and the switch is a
pointer flip rather than a data move.

```bash
python -m retrieval.migrate status
python -m retrieval.migrate introduce   --to emb_v2     # 1. verify the slot
export DUAL_WRITE_EMBED_VERSION=emb_v2                  # 2. new ingests write both
python -m retrieval.migrate backfill    --to emb_v2     # 3. re-embed, resumable
python -m retrieval.migrate shadow-eval --to emb_v2     # 4. gate; exit 1 blocks
python -m retrieval.migrate cutover     --to emb_v2     # 5. flip the pointer
python -m retrieval.migrate rollback    --to emb_v1     # 6. flip it back
```

Reads never stop. Phases 1–4 do not change what reads serve; phase 5 is one metadata
write; phase 6 is the same write reversed. `cutover` refuses unless the target version
covers every point, and `shadow-eval` exits non-zero when the candidate loses on ndcg or
mrr, so `shadow-eval && cutover` is safe to run unattended.

**Qdrant cannot add a named vector to a live collection.** `update_collection` takes a
`VectorParamsDiff` — hnsw, quantization, on_disk, memory — with no way to introduce a
vector name. So `ensure_collection` creates a slot for every *registered* version up
front; an empty slot costs nothing, and it is what keeps the migration a pointer flip. If
a slot is genuinely missing, the collection has to be rebuilt and swapped by alias
(`switch_alias` applies the delete and create in one atomic operation).

## Configuration

All settings are environment-overridable. See [config.py](config.py). Common ones:

| Variable | Default | Purpose |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant endpoint |
| `RETRIEVAL_BACKEND` | `auto` | `auto` / `qdrant` / `memory-dense` / `lexical` |
| `EMBED_BACKEND` | `sentence-transformers` | `sentence-transformers` / `hash` |
| `TOP_K_RECALL` / `TOP_K_FINAL` | `50` / `6` | candidates before / after rerank |
| `RERANK_BACKEND` | `auto` | `auto` / `none` / `cross-encoder` / `lexical` (see above) |
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
