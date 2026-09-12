# Where this design sits in 2026

The build plan was written against a 2025 landscape. This is a check of each major choice
against what is current as of September 2026, and what is worth changing.

Short version: **the stack choices hold up. The two things worth acting on are the
reranker (a latency problem we already measured) and judge calibration (a correctness
problem in how we measure).**

---

## Embeddings — BGE-M3 still fine, no longer top

BGE-M3 (568M, MIT, ~100 languages) remains a reasonable default. It is reported as the
most-used embedding model in production RAG per LangChain and LlamaIndex telemetry, and
sits in the "production baseline" tier of most 2026 comparisons — chosen for latency and
operational simplicity rather than for topping a leaderboard.

What has passed it:

| Model | Note |
|---|---|
| Qwen3-Embedding (0.6B / 4B / 8B) | Leads open-weight multilingual; ~119 languages; Apache 2.0 |
| EmbeddingGemma-300M | Roughly half BGE-M3's size, competitive quality — interesting for CPU serving |
| Gemini Embedding | Strong, but an API call per query in a latency-critical path |

**Verdict: no change.** Multilingual German coverage is the requirement and BGE-M3 has it;
MIT licensing is clean; it is already ingested and evaluated. The named-vector design
exists precisely so this can change later without a rewrite — swapping to
Qwen3-Embedding-0.6B is exactly the migration PR4 was meant to demonstrate.

Worth knowing: **EmbeddingGemma-300M** would be the candidate if embedding latency ever
became the constraint. It is not — recall is 456 ms and reranking is 28,000 ms.

---

## Reranking — this is the one to act on

We measured the cross-encoder at **98% of query latency** (28,270 ms of 28,726 ms, CPU,
27 candidates). Current benchmarks put `bge-reranker-v2-m3` at ~1100 pairs/s, ~90 ms per
100 pairs **on GPU** — so our number is the CPU penalty, not a flaw in the model.

Three options, in order of how well they fit what already exists:

**1. Late interaction (ColBERT-style) — the best fit.** Query and document are encoded
separately, like a bi-encoder, but every *token* keeps its own vector; relevance is the
sum over query tokens of their best match against document tokens. Document token vectors
are **precomputed at ingest**, so query time is dot products rather than a forward pass.

Reported: roughly 5–50 ms per query against a cross-encoder's 50–500 ms, at +3–8 nDCG over
a bi-encoder versus the cross-encoder's +5–15. One published profile has cross-encoder p50
collapsing to ~6.8 s at 30 QPS while late interaction holds ~21 ms.

It fits here because **Qdrant supports multivectors natively** with a `MAX_SIM` comparator
— the same named-vector mechanism already in `retrieval/index.py`:

```python
vectors_config={
    "emb_v1": models.VectorParams(size=1024, distance=models.Distance.COSINE),
    "colbert": models.VectorParams(
        size=128, distance=models.Distance.COSINE,
        multivector_config=models.MultiVectorConfig(
            comparator=models.MultiVectorComparator.MAX_SIM),
        hnsw_config=models.HnswConfigDiff(m=0),   # not used for multivectors
    ),
}
```

**2. A tiny cross-encoder.** `cross-encoder/ms-marco-TinyBERT-L-2` is ~4M parameters
against bge-reranker-v2-m3's 568M — ~140× smaller, built for CPU scoring. The cheapest
experiment: change one model id and re-run `compare_backends`. Quality cost unknown until
measured, which is exactly what the golden set is for.

**3. A GPU.** Solves it without changing the design, and does not help a laptop demo.

**Verdict: worth doing.** Option 2 is an afternoon and immediately measurable. Option 1 is
the architecturally right answer and reuses the named-vector work.

---

## LLM-as-judge — two documented flaws in our current setup

The 2026 literature converges on a checklist. Two items fail here.

**Family bias — a real flaw in our CI config.** A judge from the same model family as the
generator systematically over-rewards it; the standard mitigation is simply to use a
different family. Our `llm-eval.yml` uses **Gemini to generate the answer and Gemini to
judge it**. That is the documented failure mode, in our own configuration.

*Fix:* judge with a different family than the generator — a local Ollama model, or Claude,
against Gemini-generated answers.

**No calibration.** Judge scores are only trustworthy once measured against human labels.
The convention is Cohen's kappa ≥ 0.7 over a few hundred annotated samples, re-checked
periodically because judges drift over roughly 60–90 days. We have none. So
**groundedness 0.703 is a number, not yet a measurement** — we do not know its agreement
with a human reading the same answers.

One published example makes the risk concrete: a team shipped a groundedness judge, watched
dashboards glow green for three months, and later measured kappa at 0.31 — the judge had
been over-rewarding same-family outputs and under-penalising fluent hallucinations the
whole time.

Other items on the standard list, for completeness: mitigate length/verbosity bias in the
rubric; randomise order in any pairwise comparison; sample rather than score every span;
run judges async so they never add user-visible latency; track judge cost separately.

Our rubric already does one thing right — it tells the judge not to penalise an honest
refusal, which matters because refusing is the desired behaviour on a `low_confidence`
retrieval.

**Verdict: the different-family fix is small and should happen. Calibration is real work
and should be stated as missing until it is done** — which is what
[HANDBOOK.md §6.5](HANDBOOK.md#65-judge-caveats-that-are-not-yet-handled) does.

---

## What has not changed

- **Two-stage retrieval** (cheap recall → expensive rerank) is still the standard shape.
- **Structure-aware chunking** over fixed-length windows, especially for legal text.
- **Cited, grounded answers with an explicit refusal path** — now a compliance
  expectation in regulated domains, not just good practice.
- **Gating CI on statistical metrics with tolerance bands** rather than exact-match
  assertions.
- **Qdrant** remains a solid choice, and its multivector support makes it a better one
  than it was when the plan was written.

---

## Ranked next steps

| # | Change | Effort | Why |
|---|---|---|---|
| 1 | Judge from a different model family than the generator | Small | Fixes a documented bias in our own CI config |
| 2 | Try `ms-marco-TinyBERT-L-2` as the live reranker | Small | May put reranking back in the call path; measurable immediately |
| 3 | Implement PR4 (zero-downtime migration) | Medium | The build plan's centerpiece, still unbuilt |
| 4 | Wire `trace()` into the live turn | Small | Without it the drift monitor never has data |
| 5 | ColBERT multivectors as a second named vector | Medium | The architecturally right answer to §6.2 |
| 6 | Human-calibrate the judge (kappa ≥ 0.7) | Large | Turns groundedness from a number into a measurement |

---

*Reviewed September 2026. Sources: MTEB/MMTEB leaderboard summaries, Qdrant multivector
documentation, published reranker latency profiles, and 2026 LLM-as-judge practice guides.
Re-check before relying on the model comparisons — this area moves in months.*
