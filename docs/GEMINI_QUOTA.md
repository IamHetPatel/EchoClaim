# Handling Gemini rate limits

The Gemini Developer free tier has per-model and per-day quota buckets. When the
configured model returns 429 / `RESOURCE_EXHAUSTED`, work through the following.

## 1. Check what's reachable

```bash
python scripts/diagnose_gemini.py
```

It calls `client.models.list()` to enumerate what the key can see, then probes each
candidate with a tiny `generateContent`. The output shows which models are reachable and
which are rate-limited per bucket. Lite models often survive when Flash and Pro are
exhausted.

## 2. If at least one Gemini model works

Pin it in `.env`:

```
GEMINI_MODEL=gemini-2.5-flash-lite
```

Both the chat brain (`agent/gemini_client.py`) and the eval judge (`scripts/eval_jamie.py`)
auto-rotate to fallback models when the configured one 429s mid-call, so pinning is an
optimisation that avoids wasted retries rather than a requirement.

## 3. If all Gemini models are rate-limited — use Ollama (local, no quota)

```bash
brew install ollama
ollama serve &

ollama pull llama3.2      # 3B, fast, fine for prompt iteration
# or: ollama pull qwen2.5:7b   # better empathy / German, slower

echo "BRAIN_PROVIDER=ollama" >> .env
echo "OLLAMA_MODEL=llama3.2" >> .env

python scripts/run_demo_auto.py --scenario max_rear_end_a4 --pace normal
```

Trade-offs vs. Gemini Flash: higher latency (~1–3s/turn on an M-series laptop vs <500ms);
lower conversational quality on the 3B model (7B is closer); no quota, rate limits, or API
key. Use it for prompt iteration and offline runs; Gemini Flash still sounds more natural
for a final recording.

## 4. Other providers

The brain factory in `agent/brain.py` also supports OpenAI-compatible providers:

```
BRAIN_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
```

(`pip install openai`.) The `stream_reply` interface is identical; the runner is
provider-agnostic.

## 5. Notes

- Each `eval_jamie.py --all` is `N transcripts × 1 judge call` — check quota before
  running it in a loop.
- The free tier resets at midnight Pacific.
- The eval judge tries models in order
  `gemini-2.5-flash-lite → gemini-flash-latest → gemini-2.5-flash → gemini-2.5-pro`;
  the first that answers wins, and it reports the last exception clearly if all fail.
