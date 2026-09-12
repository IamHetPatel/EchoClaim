# EchoClaim Handbook

The one document to read first. It explains what the system is, every concept it uses in
plain language, where each piece lives, and how to run or test it yourself.

If you only remember one thing: **the system has two halves.** A *live* half that talks
to a caller in real time, and an *offline* half that measures whether the live half is
any good. Most of the interesting engineering is in the second half.

---

## Table of contents

1. [What the system does](#1-what-the-system-does)
2. [The 60-second mental model](#2-the-60-second-mental-model)
3. [Concepts, explained from scratch](#3-concepts-explained-from-scratch)
4. [Where everything lives](#4-where-everything-lives)
5. [How to run and test each piece](#5-how-to-run-and-test-each-piece)
6. [Design decisions and why](#6-design-decisions-and-why)
7. [What is not done](#7-what-is-not-done)

---

## 1. What the system does

A customer's car gets hit. They phone their insurer. Normally a human adjuster answers,
calms them down, asks twenty questions, and types the answers into a form.

EchoClaim is that adjuster, as software. It:

- answers a real phone call and holds a natural spoken conversation in German
- already knows who the caller is (it reads their CRM record before speaking)
- fills in a structured claim form *while* talking, without asking form-shaped questions
- answers coverage questions ("is my bumper covered?") by quoting the actual policy
  clause, not by guessing
- flags possible fraud signals as they come up in conversation

The hard part is not any single one of those. It is doing them **at the same time,
fast enough that the caller does not notice**, and being able to **prove** the answers
are grounded in the policy rather than invented.

---

## 2. The 60-second mental model

```
                         ┌──────────────── THE LIVE HALF ────────────────┐

   caller speaks
        │
        ▼
   ┌─────────┐    ┌──────────────┐    ┌─────────┐
   │   STT   │──▶ │  GeminiBrain │──▶ │   TTS   │──▶ caller hears
   └─────────┘    └──────┬───────┘    └─────────┘
    speech→text          │  can call tools mid-sentence
                         │       │
                         │       ├──▶ coverage_lookup ──▶ retrieval ──▶ cited clause
                         │       └──▶ tavily_lookup   ──▶ live web facts
                         │
                    transcript also forks sideways
                         │
                         ▼
                  ┌─────────────┐
                  │  GLiNER2    │──▶ 15 claim pillars + 5 fraud signals ──▶ dashboard
                  └─────────────┘
                                                        └──────────────────────────────┘

                         ┌────────────── THE OFFLINE HALF ───────────────┐

   golden set (32 questions) ──▶ retrieval ──▶ ranking metrics ─┐
                                     │                          │
                                     └──▶ answer ──▶ LLM judge ─┼──▶ eval gate ──▶ CI
                                                                │      pass/fail
   benchmark set ──▶ extractor ──▶ extraction F1 ───────────────┘
                                                        └──────────────────────────────┘
```

**Live half:** speech in, speech out, with two things happening in parallel — the
conversation itself, and a separate extractor quietly filling in the claim form.

**Offline half:** a fixed set of questions with known right answers, run through the same
retrieval code, scored, and compared against a committed baseline. If quality drops, the
build fails.

---

## 3. Concepts, explained from scratch

### 3.1 Why not just ask the LLM?

You could paste the whole policy into the prompt and ask Gemini. Three problems:

1. **Policies are long.** Real ones are hundreds of pages. They do not fit.
2. **Models invent things.** Asked about a deductible not in its context, a model will
   often produce a confident, plausible, wrong number. In insurance that is a
   mis-sold policy.
3. **You cannot audit it.** "The model said so" is not an answer a regulator accepts.

So instead: **find the exact relevant paragraph first, then let the model answer using
only that paragraph, and make it cite the paragraph.** That is RAG.

### 3.2 RAG — Retrieval-Augmented Generation

Three steps:

- **Retrieval** — search a document collection for the passages most relevant to the
  question.
- **Augmentation** — paste those passages into the prompt.
- **Generation** — the model answers using them.

The model stops being a memory and becomes a reader. Its job shifts from *knowing* the
answer to *reading it off the page you handed it* — which is a much easier job to do
reliably, and a much easier job to check.

### 3.3 Chunking — cutting documents into searchable pieces

You cannot search "a document". You search pieces of it. Cutting the document up is
**chunking**.

The naive way is fixed-length: every 500 characters, cut. This is bad for legal text,
because § 4 of a policy might get sliced in half, so neither half makes sense on its own
and neither can be cited cleanly.

**Structure-aware chunking** cuts on the document's own skeleton instead. German policies
are hierarchical — `Teil A` → `§ 4` → `Absatz (2)` → sentence. We split on those markers,
and only fall back to length-based windows if one clause is enormous.

Each chunk keeps metadata that doubles as its citation:

| Field | Example | Purpose |
|---|---|---|
| `clause_id` | `KK-300:§ 4` | the citation the agent quotes |
| `section_path` | `§ 4` | where it sits in the document |
| `product_code` | `KK-300` | filter: only search this caller's product |
| `doc_type` | `policy` | filter: policy vs regulation |
| `lang` | `de` | filter: language |

→ `retrieval/chunker.py`

### 3.4 Embeddings — turning meaning into coordinates

An **embedding** converts a piece of text into a list of numbers (here, 1024 of them)
positioned so that *texts with similar meaning land near each other*.

The magic is that this works across wording. "Ich bin gegen einen Hirsch gefahren" (I hit
a deer) and "Zusammenstoß mit Haarwild" (collision with game animals) share no words at
all, but land close together, because the model learned they mean the same thing.

So searching becomes: embed the question, find the chunks whose coordinates are nearest.
Nearness is **cosine similarity** — the angle between two vectors. Same direction = same
meaning.

We use **BGE-M3**, a 568M-parameter multilingual model. Multilingual matters: the corpus
is German, the callers speak German, and many embedding models are English-first.

Two implementation details that matter more than they sound:

- **Version-stamping.** Every vector records *which model made it*. Vectors from two
  different models are not comparable — mixing them silently produces garbage results.
  Recording the version makes that impossible to do by accident.
- **Content-hash caching.** Embedding is slow. We hash the text, and if we have embedded
  that exact text with that exact model before, we reuse the stored vector. Re-ingesting
  an unchanged corpus costs nothing.

→ `retrieval/embedder.py`, `retrieval/config.py`

### 3.5 The vector database — Qdrant

Once you have thousands of vectors you need something that can find the nearest ones
fast. That is a **vector database**. Scanning all of them one by one is exact but slow;
real ones use **ANN** (approximate nearest neighbour) indexes that are a hair less
precise and enormously faster.

We use **Qdrant**, and specifically its **named vectors** feature: one collection can
store several *different* vectors per document, each under a name.

```
point "KK-300:§ 4"
  ├── emb_v1  → [0.03, -0.41, ...]   (BGE-M3)
  └── emb_v2  → [0.11,  0.22, ...]   (some future model)
  └── payload → {clause_id, text, product_code, lang, ...}
```

This is what makes changing your embedding model survivable: you can write the new
model's vectors alongside the old ones and switch which name you read from. More in
[§6.4](#64-why-named-vectors).

→ `retrieval/index.py`

### 3.6 Two-stage retrieval: recall then rerank

Good search is two passes.

**Stage 1 — recall (bi-encoder).** Embed the question, grab the nearest ~50 chunks. Fast,
because document vectors were computed in advance; at query time it is just arithmetic.
But it is a blunt instrument: question and document were embedded *separately* and never
"looked at" each other.

**Stage 2 — rerank (cross-encoder).** Take those 50 and score each one properly, feeding
the model the question and the document *together* so every word can attend to every
other word. Far more accurate, far more expensive — nothing can be precomputed.

The trade, measured on this project:

| | MRR | nDCG@5 | time per query (CPU) |
|---|---|---|---|
| BM25 keyword only | 0.314 | 0.323 | ~0 ms |
| BGE-M3 recall, no rerank | 0.695 | 0.715 | ~16 ms |
| BGE-M3 recall + cross-encoder rerank | 0.805 | 0.798 | ~2,790 ms |

Reranking adds a further +0.11 MRR on top of dense recall — and costs about 2.8 seconds
per query on CPU, which is over 99% of the total. That is the single most important
measurement in this project, and [§6.2](#62-why-the-cross-encoder-is-not-in-the-live-path)
explains what we did about it.

→ `retrieval/backends.py`, `retrieval/rerank.py`, `retrieval/retriever.py`

### 3.7 Grounding and citations

Every chunk we return carries its `clause_id`. The agent is instructed to quote it. So an
answer looks like "Laut KK-300:§ 4 beträgt die Selbstbeteiligung 150 Euro" — and anyone
can go check § 4.

The retriever also returns a **`low_confidence` flag** when the best match scores poorly.
The agent's instruction in that case is to say a specialist will confirm, rather than
guess. *Refusing is a feature.* A confident wrong answer about coverage is worse than no
answer.

→ `retrieval/retriever.py`, `retrieval/tool.py`

### 3.8 Structured extraction, running alongside

Separately from the conversation, a model called **GLiNER2** reads the running transcript
and pulls out fields. It fills **15 claim pillars** (incident location, time, other
party's plate, police case number, injuries…) and **5 fraud signals** (delayed reporting,
prior similar incident, knows the other party…).

Why a separate model instead of asking Gemini? Because we measured:

| | latency | cost/call | F1 |
|---|---|---|---|
| GLiNER2 fine-tuned | **69 ms** | **$0** | 0.61 |
| Gemini structured output | 2,729 ms | $0.0015 | **0.86** |

Gemini is more accurate. GLiNER2 is 40× faster and free. **We chose GLiNER2** — on a live
phone call, a 2.7-second pause is a dead conversation. This is the kind of trade where
the "best" model on the leaderboard is the wrong answer.

Running it in parallel ("fanning out") means extraction never delays a reply.

→ `extraction/`, `agent/claim_state.py`

### 3.9 Evaluating retrieval: the four metrics

We have a **golden set**: 32 questions, each labelled with the clause ids that *should*
come back. Four numbers score the result.

Say the right answer is at position 2 of 5 returned:

- **precision@k** — of the k returned, what fraction were right? Here 1/5 = 0.2.
  *Careful:* if a question has only one right answer, precision@5 can never exceed 0.2.
  Do not read it as "20% correct".
- **recall@k** — of all the right answers, how many did we return? 1 of 1 = 1.0.
- **MRR** (Mean Reciprocal Rank) — 1 ÷ the rank of the first correct hit. Rank 2 → 0.5.
  Rewards putting the right answer *first*. **The most useful single number here.**
- **nDCG@k** — like MRR but credits *every* correct item, discounted by how far down it
  is. Best for questions with several right answers.

→ `retrieval/eval.py`

### 3.10 Why a bad golden set is worse than none

The original golden set had 11 questions, one per clause, each phrased using that
clause's own vocabulary. Every single one returned at rank 1. MRR 1.0, nDCG 1.0.

That looks like a triumph. It is actually a broken instrument. **A metric pinned at its
ceiling cannot detect a regression** — break the retriever and the score still reads 1.0.
Gating a build on it produces a green check that means nothing.

The replacement is deliberately hard, in two ways:

**Questions use caller language, not clause language.** A caller says "Ich bin gegen einen
Hirsch gefahren"; the clause says "Zusammenstoß mit Haarwild". No shared words, so keyword
search cannot bridge it and the embedding model has to actually earn its place.

**The corpus contains near-misses.** Five documents, 27 clauses, seeded on purpose with:

- three different deductible clauses — 150 €, 250 €, and "none" — plus a fourth clause
  mentioning 150 € for something unrelated
- two territorial-scope clauses that disagree with each other
- three exclusion clauses that all mention motor racing
- five reporting-deadline clauses with different deadlines

So retrieving *a* clause about deductibles is not enough. It has to be the right one.

On the good configuration, four of 32 still fail. **That is the point** — there is room to
move in both directions, so the number can actually detect change.

→ `data/eval/golden_set.jsonl`, `data/policies/`

### 3.11 LLM-as-judge and groundedness

Ranking metrics tell you the right clause was *retrieved*. They say nothing about whether
the answer the caller hears actually follows from it. The model could retrieve § 4
perfectly and then say something § 4 does not support.

**Groundedness** measures that second hop. For each question:

1. retrieve → get clauses
2. generate an answer using *only* those clauses, at temperature 0
3. ask a *second* model: "does every claim in this answer follow from these clauses?"

That second model is the **LLM-as-judge**. Scoring language quality with code is nearly
impossible; another language model can do it approximately, cheaply, at scale.

Measured here: **groundedness 0.703** over 32 questions.

Read that with its caveat, which is instructive. The same run scored *faithfulness* 1.000
on all 32 questions — a suspiciously perfect result. It means the small local judge
(llama3.2, 3B parameters) cannot discriminate on that dimension at all. **A judge is a
measuring instrument, and instruments need checking.** See [§6.5](#65-judge-caveats-that-are-not-yet-handled).

→ `llmops/judge.py`, `llmops/groundedness.py`

### 3.12 The prompt registry

The system prompt is the single biggest lever on behaviour. Change a sentence and quality
moves. The classic failure is: someone edits it, quality shifts weeks later, and nobody
can connect the two.

A **prompt registry** treats prompts as versioned artifacts. Each lives in a YAML file
with a semantic version, and gets a **content hash** — a fingerprint of the exact text.
The reference looks like:

```
jamie_system@1.0.0+212125a0c3e1
            │      └── content hash: changes if one character changes
            └── semver: you bump it deliberately
```

The registry **refuses to load unless exactly one version is marked active**. Two active
versions, or zero, is an error rather than a coin flip. Every logged turn records the
reference, so any behaviour change traces to a specific prompt.

→ `llmops/prompt_registry.py`, `llmops/prompts/`, wired in `agent/prompts.py`

### 3.13 PII redaction

Claims calls contain some of the most sensitive data there is: health details, bank
details, location, vehicle identity. Under GDPR, health data is Article 9 — special
category.

So there is a **redaction boundary**: before any text is written to a log, the bridge, or
disk, it passes through `redact()`, which replaces twelve pattern classes with tokens —
policy number, VIN, licence plate, IBAN, credit card, social security number, health card,
driving licence, phone, email, date of birth.

Pattern order matters: date-of-birth runs before phone, or an ISO date like `1984-03-15`
gets eaten by the looser phone-number pattern first.

→ `agent/pii_redact.py`, live at `voice/livekit_agent.py:159`

### 3.14 Trace logging and drift

Each turn writes one row: prompt reference, retrieved clause ids, the response
(redacted), latency, top retrieval score, judge score.

**Drift** is the slow degradation that nothing alerts on, because nothing broke. The
corpus gets edited; a model version changes; questions shift with the season. Nothing
throws an error. Quality just sags.

The drift monitor compares a **recent window** of traces against a **reference window**
before it, on two signals:

- **groundedness rate** — has the mean judge score fallen?
- **PSI** (Population Stability Index) on retrieval scores — has the *distribution* of
  match scores shifted? PSI above ~0.2 conventionally means a meaningful shift.

PSI usually moves first. The retrieval scores get worse before the answers visibly do, so
it is an early warning rather than a post-mortem.

The monitor returns nothing until there are `2 × window` traces. "Not enough data to
compare" is a different state from "no drift", and it says so rather than implying calm.

→ `llmops/logging_middleware.py`, `llmops/drift_monitor.py`

### 3.15 The eval gate — CI for things that are not deterministic

Normal CI asserts exact equality: `assert add(2,2) == 4`. You cannot do that with a
language model — the same input can produce different words, all correct.

So the gate compares **statistical metrics against a committed baseline**, with
**tolerance bands**:

| Metric | Tolerance |
|---|---|
| `precision@k` | 0.02 |
| `ndcg@k` | 0.02 |
| `groundedness` | 0.05 |
| `extraction_f1` | 0.02 |

Drop more than that and the build fails. Retrieval is deterministic so it gets tight
bands; the judge is a sampled model score so it gets a looser one.

Three things stop it from being theatre:

**Determinism.** Frozen eval set, temperature 0 everywhere, fixed index. Re-running
unchanged inputs reproduces the numbers. Without this, tolerance bands become a
retry-until-green lottery.

**Unmeasurable is not passing.** If the judge has no API key, groundedness is reported
**absent with the reason** — never filled in with a passing 1.0. Under `--strict` (how CI
runs it) that absence *fails the build*. This is the single most important line in the
gate: a gate that quietly substitutes a passing value for a metric it did not compute is
worse than no gate, because it reads as a green check.

**Provenance.** The baseline records which judge, embedder and reranker produced it, plus
a hash of the golden set. Comparing a groundedness score from one judge against a baseline
from another measures the judge, not the system — so the gate refuses.

→ `llmops/eval_gate.py`, `data/eval/baseline.json`

---

## 4. Where everything lives

```
AI-voice-Agent/
│
├── agent/                  the conversation's brain
│   ├── prompts.py          builds the system prompt; loads persona from the registry
│   ├── gemini_client.py    Gemini wrapper + model fallback chain
│   ├── brain.py            provider selection (Gemini / Ollama / OpenAI)
│   ├── claim_state.py      what we know so far about this claim
│   └── pii_redact.py       ★ the redaction boundary (12 pattern classes)
│
├── voice/                  the live call loop
│   └── livekit_agent.py    STT → brain → TTS over LiveKit; forks transcript to extraction
│
├── telephony/              Twilio SIP ↔ LiveKit room glue
│
├── extraction/             the parallel form-filler
│   ├── gliner2_service.py  ★ 15 claim pillars + 5 fraud signals
│   ├── gemini_extractor.py the LLM alternative it was benchmarked against
│   ├── benchmark.py        the latency / cost / F1 comparison
│   └── finetune_gliner.py  training script
│
├── retrieval/              ★ finding the right policy clause
│   ├── config.py           every tunable, all env-overridable
│   ├── corpus.py           reads data/policies/*.md + front matter
│   ├── chunker.py          structure-aware splitting; stable point ids
│   ├── embedder.py         BGE-M3 + hash fallback; content-hash cache
│   ├── index.py            Qdrant named-vector wrapper
│   ├── ingest.py           corpus → chunks → vectors → Qdrant
│   ├── backends.py         qdrant / memory-dense / lexical recall
│   ├── rerank.py           cross-encoder or lexical rerank
│   ├── retriever.py        recall → rerank → cited chunks + low_confidence
│   ├── tool.py             coverage_lookup, the agent-facing function
│   ├── eval.py             precision@k / recall@k / MRR / nDCG
│   └── compare_backends.py side-by-side backend comparison
│
├── llmops/                 ★ measuring whether any of it works
│   ├── prompt_registry.py  content-hashed prompts, exactly one active
│   ├── prompts/            the prompt artifacts themselves
│   ├── judge.py            LLM-as-judge (Gemini or Ollama), temperature 0
│   ├── groundedness.py     retrieve → answer → judge, end to end
│   ├── extraction_eval.py  extraction F1 for the gate
│   ├── eval_gate.py        ★ the thing CI runs; fails on regression
│   ├── logging_middleware.py  per-turn PII-redacted traces
│   └── drift_monitor.py    groundedness delta + PSI over traces
│
├── tools/                  functions the agent can call mid-conversation
│   ├── coverage_lookup.py  → retrieval
│   └── tavily_lookup.py    → live web
│
├── bridge/ + dashboard/    WebSocket bridge and the React view
│
├── data/
│   ├── policies/           the corpus (5 docs, 27 clauses)
│   ├── eval/golden_set.jsonl   ★ 32 questions with known answers
│   ├── eval/baseline.json  ★ the numbers CI compares against
│   ├── crm/                mock caller records
│   └── scenarios/          scripted test conversations
│
├── tests/                  54 tests; run fully offline
│   └── juror_bot.py        adversarial realism harness (written, never run)
│
├── .github/workflows/      ★ tests.yml (offline) + llm-eval.yml (the gate)
└── docs/                   this file, EVAL.md, SECURITY.md, COMPONENTS.md
```

★ = the parts worth reading first.

---

## 5. How to run and test each piece

### 5.0 Setup

```bash
cd ~/Documents/Workspace/BBH/AI-voice-Agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # full stack
pip install -r requirements-eval.txt     # just retrieval + eval + tests
cp .env.example .env                     # then fill in keys
```

### 5.1 Everything offline, no keys, no downloads

The fastest confidence check. Should take well under a minute.

```bash
RETRIEVAL_BACKEND=lexical EMBED_BACKEND=hash python -m pytest tests/ -q
```
Expect: **54 passed.**

```bash
python -m retrieval.eval
```
Expect MRR ≈ 0.31 on the lexical backend. **A low number here is correct** — that is BM25
against deliberately hard paraphrases, and it is the floor the dense stack improves on.

### 5.2 Retrieval quality, for real

Needs the models (~4.3 GB first time) and Docker.

```bash
docker run -d --name echoclaim-qdrant -p 6333:6333 qdrant/qdrant:v1.12.1

TORCH_DEVICE=cpu EMBED_BACKEND=sentence-transformers \
  python -m retrieval.ingest --recreate

TORCH_DEVICE=cpu python -m retrieval.compare_backends
```

Expect roughly:

```
backend                        precision@5   recall@5      mrr    ndcg@5   hit_rate
lexical + lexical                   0.0938     0.3594   0.3135    0.3229     0.3750
memory-dense + cross-encoder        0.2188     0.8385   0.8047    0.7984     0.8750
qdrant + cross-encoder              0.2188     0.8385   0.8047    0.7984     0.8750
```

Qdrant and in-memory agreeing to four decimals is the check that the index is wired
correctly. **Be patient:** the cross-encoder rows take ~30s per query on CPU.

### 5.3 Ask it a question yourself

```bash
python tools/coverage_lookup.py
```

```python
from retrieval.tool import coverage_lookup
coverage_lookup("Ist ein Parkschaden in der Vollkasko gedeckt?", product_code="KK-300")
# {"summary": "Laut KK-300:§ 6 ...", "citations": [...], "low_confidence": False}
```

Try a nonsense question and confirm `low_confidence` comes back `True`. The refusal path
matters as much as the happy path.

### 5.4 The extractor and its benchmark

```bash
python -m llmops.extraction_eval          # F1 of the live extractor
python -m extraction.benchmark            # the full latency/cost/F1 table
```

### 5.5 The LLM judge and groundedness

Either a local model (free) or Gemini (needs a working key):

```bash
ollama serve &
ollama pull llama3.2

JUDGE_BACKEND=ollama JUDGE_MODEL=llama3.2:latest \
TORCH_DEVICE=cpu EMBED_BACKEND=sentence-transformers \
RETRIEVAL_BACKEND=qdrant RERANK_BACKEND=cross-encoder \
  python -m llmops.groundedness --sample 8
```

`--sample 8` keeps it to a few minutes. Read the per-question output, not just the mean —
it shows you what the judge actually objected to.

### 5.6 The eval gate

```bash
# Retrieval metrics only. No key, no model, no server.
python -m llmops.eval_gate --skip-groundedness --skip-extraction

# The full gate.
JUDGE_BACKEND=ollama JUDGE_MODEL=llama3.2:latest \
TORCH_DEVICE=cpu EMBED_BACKEND=sentence-transformers \
RETRIEVAL_BACKEND=qdrant RERANK_BACKEND=cross-encoder \
  python -m llmops.eval_gate --strict
```

**See it refuse to fake a result** — the behaviour the whole design turns on:

```bash
JUDGE_BACKEND=gemini GOOGLE_API_KEY= python -m llmops.eval_gate
#   ! groundedness NOT MEASURED -> JudgeUnavailable: GOOGLE_API_KEY is not set
```

Not a 1.0. Absent, with the reason.

**Prove it catches a regression** without a 15-minute run:

```python
from llmops.eval_gate import compare
import json
base = json.load(open("data/eval/baseline.json"))["metrics"]
print(compare({**base, "ndcg@5": base["ndcg@5"] - 0.05}, base))
# ['ndcg@5: 0.7484 vs baseline 0.7984 (drop 0.0500 > tolerance 0.02)']
```

### 5.7 The prompt registry

```python
from llmops.prompt_registry import registry
p = registry.get("jamie_system")
print(p.ref)        # jamie_system@1.0.0+212125a0c3e1
```

To see the invariant bite: copy the YAML to a second file, set `active: true` on both, and
watch `registry.get` raise `ValueError: expected exactly one active version`.

### 5.8 The drift monitor

```bash
python -m llmops.drift_monitor --window 50
```

On a fresh checkout this prints "not enough traces" — correct, since nothing has run at
volume. `tests/test_llmops.py` exercises the logic with synthetic traces.

### 5.9 The conversation, end to end

```bash
python scripts/run_demo_text.py --crm max_mueller
```

Typed input instead of a phone call, but the real prompt, real extraction, real
`coverage_lookup`. For actual telephony see [telephony/README.md](../telephony/README.md).

---

## 6. Design decisions and why

### 6.1 Why the offline paths exist at all

Every heavy component has a dependency-free twin: `lexical` recall instead of dense,
`hash` embeddings instead of BGE-M3, `LexicalReranker` instead of the cross-encoder.

Two reasons. **CI runs in a minute** without downloading gigabytes. And because the
lexical and hash paths are fully deterministic, the test suite's numbers never move — so
a failure means something actually broke.

### 6.2 Why the cross-encoder is not in the live path

It is over 99% of query latency — 2,776 ms steady state against ~16 ms for recall. (An
earlier draft of these docs said 28 s; that was a cold process, folding model load and
torch warmup into one measured call. Measure warm.) A caller will not wait either way.

So `RERANK_BACKEND=auto` resolves to `NoOpReranker` and the cross-encoder is opt-in. This
was a real bug: an earlier version returned the cross-encoder whenever
`sentence_transformers` happened to be importable, so merely installing the embedding
dependency would have put a multi-second rerank into live phone calls.

Two further findings, both from measuring rather than guessing:

| rerank | MRR | nDCG@5 | ms/query |
|---|---|---|---|
| none (recall order) | 0.6953 | 0.7145 | 0.2 |
| lexical | 0.6120 | 0.6426 | 0.5 |
| TinyBERT-L-2 (4M, EN) | 0.3031 | 0.3167 | 22.7 |
| MiniLM-L-6 (22M, EN) | 0.3328 | 0.3436 | 221.1 |
| bge-reranker-v2-m3 (568M, multilingual) | 0.8047 | 0.7984 | 2776.4 |

**Lexical reranking is worse than doing nothing.** It throws away the dense model's
ordering and substitutes keyword overlap — precisely what fails on paraphrased queries.
`auto` returned it until this was measured.

**A tiny reranker is not the answer.** The small English ms-marco cross-encoders are fast
and roughly *halve* MRR on German, scoring below no reranking at all. Reranker size was
never the constraint; multilingual coverage is.

Serving reranking properly needs a GPU (~90 ms/100 pairs) or late interaction — see
[§7](#7-what-is-not-done).

### 6.3 Why GLiNER2 despite losing on F1

0.61 vs Gemini's 0.86 — but 69 ms vs 2,729 ms, and free vs paid. On a phone call latency
*is* correctness, because a 2.7-second pause ends the illusion of a conversation.
Benchmarks rank models; products rank constraints.

### 6.4 Why named vectors

Changing embedding model is the scary migration: old and new vectors are incomparable, so
a naive swap means re-embedding everything with search broken in between.

Named vectors let both live side by side on the same point. The safe sequence becomes:
introduce `emb_v2` → write both on ingest → backfill the old corpus → evaluate v2 against
v1 on the golden set → flip which name reads serve → keep v1 for instant rollback.

All six phases are implemented in `retrieval/migrate.py` and have been rehearsed end to
end against a live Qdrant. The rehearsal deliberately migrates *to a worse model*
(`bge-base-en-v1.5`, English-only, on a German corpus) because the interesting question is
not whether a good migration succeeds but whether a bad one is stopped:

```
shadow-eval   emb_v1 ndcg@5 0.7145   emb_v2 ndcg@5 0.2322   delta -0.4823  -> FAIL, exit 1
cutover       (blocked: shadow-eval gates it in the pipeline)
cutover       --force            -> reads serve emb_v2, return the WRONG clause
rollback --to emb_v1             -> reads serve emb_v1, correct clause restored
```

One caveat worth knowing, because it constrains the design: **Qdrant cannot add a named
vector to a live collection.** `update_collection` takes a `VectorParamsDiff`, which
changes hnsw or quantization settings but cannot introduce a new vector name. So slots for
every registered version are created up front (an empty slot costs nothing), and
`retrieval/migrate.py` carries an alias-swap path for the case where you did not plan
ahead.

### 6.5 Judge caveats that are not yet handled

Current research on LLM-as-judge names several biases with known mitigations. Two apply
directly here and are **not** yet handled:

- **Family bias.** A judge from the same model family as the generator systematically
  over-rewards it. The CI config uses Gemini to generate the answer *and* Gemini to judge
  it. That should be a different family.
- **No human calibration.** Judge scores are only trustworthy once checked against human
  labels — the usual bar is Cohen's kappa ≥ 0.7 on a few hundred samples. We have none, so
  0.703 is a *number*, not yet a *measurement*. Judges are also reported to drift over
  60–90 days, so calibration wants a cadence.

Written down here rather than quietly ignored, because a miscalibrated judge that reads
green is exactly the failure this whole layer is supposed to prevent.

### 6.6 Why "unmeasurable is not passing"

The original gate hardcoded `groundedness = 1.0` and `extraction_f1 = 1.0` with a `TODO`.
It would have shown a green check while measuring two of its four metrics not at all.

That is worse than having no gate, because a green check is *read as evidence*. The rule
now: a metric you could not compute is absent and named, and under `--strict` it fails.

---

## 7. What is not done

Stated plainly, because knowing the edges is part of understanding the system.

| Gap | State |
|---|---|
| **Drift monitor at volume** | Implemented and unit-tested, never run over production traces. Needs `2 × window` rows. |
| **Trace logging in the live turn** | `trace()` exists and is tested, but is not yet wrapped around the live Gemini call, so no real traces accumulate. |
| **Juror bot** | 259 lines, never executed. One run produces `juror_results.csv` and makes the claim real. |
| **Aikido as a gate** | It genuinely scanned (`docs/aikido-screenshots/`), but `aikido.yml` is a self-described placeholder and is not a required check. |
| **Judge calibration** | No human-labelled gold set, no kappa, no different-family judge. See [§6.5](#65-judge-caveats-that-are-not-yet-handled). |
| **Quantization / context compression** | Build plan PR7. Not started. |

### Worth considering next

- **Late interaction (ColBERT-style) reranking.** Qdrant supports multivectors natively
  with a `MAX_SIM` comparator, and document token embeddings are precomputed — roughly
  5–50 ms per query against the cross-encoder's 50–500 ms, at most of the quality. This is
  the natural fix for §6.2, and it fits the existing named-vector design. It is now the
  *only* promising option left, since the tiny-reranker route was tried and failed.
- **A multilingual small reranker.** The failure above was language coverage, not size, so
  a small *multilingual* cross-encoder is the shape worth looking for.

---

## Further reading in this repo

| Document | Covers |
|---|---|
| [EVAL.md](EVAL.md) | Evaluation methodology and every measured number |
| [COMPONENTS.md](COMPONENTS.md) | Module-by-module contracts |
| [SECURITY.md](SECURITY.md) | GDPR posture, the redaction table |
| [../retrieval/README.md](../retrieval/README.md) | Retrieval internals and configuration |
| [../llmops/README.md](../llmops/README.md) | The gate, the registry, judge backends |
| [../telephony/README.md](../telephony/README.md) | Twilio SIP and LiveKit setup |
