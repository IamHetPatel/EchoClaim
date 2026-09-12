# HPC batch jobs

SLURM scripts for the two jobs worth moving off a laptop. Both are optional: the repo
runs end to end on CPU without them.

| Script | Job |
|---|---|
| `embed_corpus.sbatch` | Embed the corpus on a GPU. Relevant to the migration backfill, the one genuinely compute-heavy step — see [../retrieval/README.md](../retrieval/README.md). |
| `finetune_quantize_gliner.sbatch` | Fine-tune and quantize the GLiNER2 extractor (`extraction/finetune_gliner.py`). |

Reranking is the other candidate: `bge-reranker-v2-m3` costs ~2.8 s/query on CPU against
~90 ms per 100 pairs on a GPU, which is the difference between "evaluation only" and
"usable in the call path". See [../docs/EVAL.md](../docs/EVAL.md).
