# Evaluation

How quality is measured, and what each number does and does not mean.

## The golden set

`data/eval/golden_set.jsonl` — 32 caller questions, each mapped to the clause ids that
should be retrieved, tagged `easy` / `medium` / `hard`. Seven require more than one clause.

It is deliberately adversarial in two ways.

**Queries are phrased as a caller speaks, not as the clause is written.** "Ich bin gegen
einen Hirsch gefahren" has to reach a clause that says "Zusammenstoß mit Haarwild".
There is no shared vocabulary, so lexical matching cannot get there.

**The corpus carries near-miss distractors.** Five documents, 27 clauses, containing on
purpose:

- three different deductible clauses — KK-300 §4 (150 €), RS-200 §2 (250 €), HP-100 §3
  (none) — plus SB-400 §1, which mentions 150 € for something else entirely
- two territorial-scope clauses that disagree, and say so
- three exclusion clauses that all mention racing
- five separate reporting-obligation clauses with different deadlines

So retrieving "a clause about a deductible" is not enough; it has to be the right one.

### Why the earlier numbers were meaningless

The previous golden set had 11 queries, one per clause, each phrased in the clause's own
vocabulary. Every query returned its answer at rank 1: MRR 1.0, nDCG 1.0, recall 1.0.

A metric pinned at its ceiling cannot detect a regression. Gating on it produces a green
check that means nothing. The current set leaves four queries failing at k=5 on the best
configuration, which is the point — there is room to move in both directions.

## Retrieval results

32 queries, k=5, measured against a live Qdrant. Reproduce with
`python -m retrieval.compare_backends`.

| Recall + rerank | precision@5 | recall@5 | MRR | nDCG@5 | hit rate | s/query |
|---|---|---|---|---|---|---|
| BM25 + lexical | 0.094 | 0.359 | 0.314 | 0.323 | 37.5% | ~0.00 |
| BGE-M3 + cross-encoder (in-memory) | 0.219 | 0.839 | 0.805 | 0.798 | 87.5% | 11.6 |
| BGE-M3 + cross-encoder (Qdrant) | 0.219 | 0.839 | 0.805 | 0.798 | 87.5% | 24.5 |

`precision@5` has a low ceiling by construction: most queries have one relevant clause,
so the best possible precision@5 is 0.2. Read MRR and nDCG instead.

Qdrant ANN and exact in-memory cosine agree to four decimals, which is the expected
result at this corpus size and a useful check that the index is wired correctly.

### The latency finding

Reranking is 98% of query time. On CPU, for one query over 27 candidates:

| Stage | Time |
|---|---|
| BGE-M3 embed + Qdrant ANN | 456 ms |
| bge-reranker-v2-m3 rerank | 28,270 ms |
| lexical rerank | 8 ms |

bge-reranker-v2-m3 is a 568M-parameter cross-encoder scoring every (query, candidate)
pair. It buys a large quality gain — nDCG 0.32 → 0.80 — and it cannot go anywhere near a
real-time phone call on CPU.

So `RERANK_BACKEND=auto` resolves to the **lexical** reranker, and the cross-encoder is
opt-in. An earlier version returned the cross-encoder whenever `sentence_transformers`
was merely importable, which meant installing the embedding dependency would silently put
a 28-second rerank in the live voice path. Eval and CI set it explicitly; the agent does
not.

Serving the cross-encoder in production would need a GPU, a smaller reranker, or a
tighter candidate list. That is not done.

## Groundedness

`llmops.groundedness` measures the second hop, which the ranking metrics say nothing
about: given the clauses that were retrieved, does the answer actually follow from them?

Per query: retrieve → generate an answer from only those citations at temperature 0 →
judge the answer against those citations.

Measured: **groundedness 0.703** over 32 queries, judged by llama3.2:3b via Ollama.

Read that with its caveat. The same run reported faithfulness 1.000 on all 32 queries —
a 3B judge does not discriminate on that dimension, so only the groundedness figure is
worth anything here. CI runs the Gemini judge instead.

Because judges do not share a scale, the baseline records which judge produced it, and
the gate refuses to compare a groundedness number across a judge change rather than
reporting a phantom regression.

## The gate

`llmops.eval_gate` compares the current run against `data/eval/baseline.json` and fails
the build when a metric drops past its tolerance. See [llmops/README.md](../llmops/README.md).

A metric that could not be measured is reported as absent with the reason, never as a
passing value. Under `--strict`, which is how CI runs it, that absence fails the build.

## Extraction

`llmops.extraction_eval` scores the extractor on the live path against
`extraction.benchmark`'s eval set.

Note on the committed benchmark numbers: five of the twelve gold labels referenced names
the extractor could never emit — three were renamed by the multi-domain pillar rename
(`accident_location` → `incident_location`, `accident_time` → `incident_datetime`,
`injury_description` → `injuries_or_symptoms`) and two were never in the label set at all.
They scored as guaranteed false negatives for every model, so the older F1 figures
understated all of them. Fixed; re-run `python -m extraction.benchmark` to regenerate.

## Running it

```bash
# Offline: no model, no server, no key.
python -m retrieval.eval
python -m pytest tests/ -q

# Full stack.
docker run -d -p 6333:6333 qdrant/qdrant:v1.12.1
TORCH_DEVICE=cpu EMBED_BACKEND=sentence-transformers python -m retrieval.ingest --recreate
TORCH_DEVICE=cpu RETRIEVAL_BACKEND=qdrant RERANK_BACKEND=cross-encoder \
  python -m retrieval.compare_backends

# The gate.
JUDGE_BACKEND=ollama JUDGE_MODEL=llama3.2:latest python -m llmops.eval_gate
```
