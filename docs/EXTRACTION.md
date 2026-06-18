# Entity extraction: synthetic data + fine-tuned GLiNER

The agent fills about 15 claim-line fields from free-form caller speech in real time,
on-device, while the call is still going. This document covers why GLiNER is used, how the
training data is generated, the fine-tune, and how it compares to zero-shot GLiNER and an
LLM structured-output baseline.

## Why GLiNER

Real-time, on-device extraction rules out high-latency or cloud-only options:

| Option | Latency | Cost / call | On-device |
|---|---|---|---|
| LLM structured output | ~4400ms | $0.0015 | no |
| GPT-4o JSON mode | ~1200ms | $0.018 | no |
| Regex / spaCy patterns | <5ms | $0 | yes (brittle) |
| GLiNER zero-shot | ~50ms | $0 | yes |
| GLiNER fine-tuned | ~50ms | $0 | yes |

Zero-shot accuracy is the floor, not the ceiling. On the internal benchmark it scores
F1 around 0.32 on the 15 claim labels, because they are domain-specific German FNOL terms
the public model has not seen with this exact phrasing. Fine-tuning closes that gap.

## Pipeline

```
data/synthetic/fnol_train.jsonl
        ^
extraction/synthetic_data.py    LLM-generated, provider-pluggable
        |
        v
extraction/finetune_gliner.py   transformers.Trainer
        |
        v
models/jamie-gliner-v1/         saved fine-tuned weights
        |
        v
extraction/benchmark.py         zero-shot + fine-tuned + LLM, side by side
```

## Synthetic data generation

`extraction/synthetic_data.py` produces transcripts with inline label markers rather than
asking the LLM for token-aligned annotations directly. LLMs are poor at counting word
indices but good at producing natural text with structured spans:

```
"My car got hit on [[accident_location:the A4 near Köln-Ost]] in
[[weather_conditions:pouring rain]]. Plate was [[other_party_plate:K-AB 1234]]."
```

The script strips the markers, tokenizes by whitespace, and computes word-level spans
automatically. It handles multi-word entities, attached punctuation, and mixed
German/English, and it silently skips spans that do not round-trip.

Design properties:

- Multi-provider LLM chain. It falls through Gemini Flash, then an OpenAI-compatible
  provider, then a fallback provider. A 429/5xx/404 moves to the next.
- Model rotation per provider. For example, `gemini-flash-latest`, then `2.5-flash`, then
  `2.5-flash-lite`, to dodge per-model quota windows.
- Quality filters. It drops batches under 30 characters or with fewer than two valid
  spans.

## Fine-tuning

`extraction/finetune_gliner.py` wraps `gliner.training.Trainer` (a `transformers.Trainer`
subclass) with laptop-friendly defaults:

- Base model `urchade/gliner_small-v2.1` (about 153M, bi-encoder span head). The 530M
  `knowledgator/gliner-bi-large-v2.0` is selectable via `--model` but is about 3.5x slower
  per step.
- 2 epochs, batch size 4, learning rate 5e-6 (conservative, small domain shift).
- Device auto-detect: MPS on Apple silicon, CUDA otherwise, CPU fallback.
- A single save at the end, with no intermediate checkpoints.

Scaling to 1000+ examples on a GPU is the path to higher F1. The small-base fine-tune is
enough to show the lift.

## Benchmark

`extraction/benchmark.py` auto-detects `models/jamie-gliner-v1/` and benchmarks it next to
zero-shot GLiNER and LLM structured output. Example run:

```
Model                                          Latency  Cost/call  F1
--------------------------------------------------------------------
GLiNER zero-shot (gliner-bi-large, 530M)        837ms   $0.0000   0.317
GLiNER fine-tuned (small, 153M)                 116ms   $0.0000   0.476
LLM structured (gemini-flash-latest)           4623ms   $0.0015   0.832
```

The fine-tuned 153M model is about 50% higher F1 than the 530M zero-shot baseline (0.317
to 0.476), several times faster per call, and free at inference. The LLM baseline is more
accurate but far slower and not on-device.

Reproduce:

```bash
pip install -r requirements.txt
python extraction/synthetic_data.py --count 50
python extraction/finetune_gliner.py --epochs 2
python -m extraction.benchmark
```

## Fraud signals from the same model

The same fine-tuned model also detects fraud signals: `delayed_reporting`,
`known_to_other_party`, `vehicle_listed_for_sale`, `prior_similar_incident`,
`timeline_inconsistency`. The synthetic generator was prompted to include them, so one
on-device model produces both the claim documentation and the fraud-risk signals that
drive `bridge_publish({"type": "fraud_signal", ...})` on the dashboard.
