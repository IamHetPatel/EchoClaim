"""Reranking: reorder recall candidates by true query-passage relevance.

Bi-encoder / BM25 recall is cheap but blurry; a reranker reorders the top candidates.
Two backends share one interface (``rerank``):

* ``CrossEncoderReranker``: bge-reranker-v2-m3, the real model (lazy-loaded).
* ``LexicalReranker``: dependency-free query/passage term-overlap scorer for
  offline use and CI. Its score is a bounded [0, 1] coverage fraction, which doubles
  as the low-confidence signal the retriever thresholds on.

``get_reranker`` picks the cross-encoder when sentence-transformers is importable and
falls back to lexical otherwise, so retrieval works with zero heavy deps installed.

See echoclaim-spine/BUILD_PLAN.md section 3.5.
"""
from __future__ import annotations

import os
import re

from .config import settings
from .index import Hit

_TOKEN = re.compile(r"[a-zA-ZäöüÄÖÜß0-9§]+")

# Function words carry no retrieval signal but, left in, they let an off-domain query
# ("Wie spät ist es in Tokio?") match common words in every clause and look confident.
# Dropping them is what keeps the lexical low-confidence signal honest.
_STOPWORDS = frozenset("""
der die das den dem des ein eine einen einem einer eines und oder aber ist sind war waren
sein bei in im an auf für fur mit von vom zu zur zum aus nach über uber unter vor wie was
wer wo wann warum welche welcher welches wird werden kann können konnen muss müssen mussen
soll sollen ich du er sie es wir ihr man nicht kein keine als auch noch nur schon dass ob
am ist sich so wenn dann hier da
the a an is are was were be of to in on at for with and or how what when where why which who
this that it i you we they not no do does
""".split())


_UMLAUT = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})
# Conservative inflectional suffixes, longest first. Light stemming so German
# singular/plural and case variants match (Parkschaden~Parkschäden,
# Stoßstange~Stoßstangen). The dense BGE-M3 path handles this semantically; this
# is the cheap approximation for the offline lexical backend.
_SUFFIXES = ("ern", "en", "er", "es", "e", "n", "s")


def _normalize(token: str) -> str:
    token = token.translate(_UMLAUT)
    for suf in _SUFFIXES:
        if token.endswith(suf) and len(token) - len(suf) >= 4:
            return token[: -len(suf)]
    return token


def tokenize(text: str) -> list[str]:
    """Lowercase, stopword-filtered, lightly-stemmed content tokens."""
    out = []
    for m in _TOKEN.findall(text):
        low = m.lower()
        if low in _STOPWORDS or (len(low) <= 1 and low != "§"):
            continue
        out.append(_normalize(low))
    return out


class CrossEncoderReranker:
    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or settings.rerank_model_id
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_id, device=settings.torch_device)
        return self._model

    def rerank(self, query: str, hits: list[Hit], top_k: int | None = None) -> list[Hit]:
        if not hits:
            return []
        scores = self._load().predict([(query, h.text) for h in hits])
        ranked = sorted(zip(scores, hits), key=lambda x: float(x[0]), reverse=True)
        out = []
        for s, h in ranked[: top_k or settings.top_k_final]:
            h.score = float(s)
            out.append(h)
        return out


class LexicalReranker:
    """Score = fraction of distinct query terms present in the passage, in [0, 1]."""

    def rerank(self, query: str, hits: list[Hit], top_k: int | None = None) -> list[Hit]:
        if not hits:
            return []
        q_terms = set(tokenize(query))
        if not q_terms:
            return hits[: top_k or settings.top_k_final]
        scored = []
        for h in hits:
            passage = set(tokenize(h.text))
            overlap = len(q_terms & passage) / len(q_terms)
            scored.append((overlap, h))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for s, h in scored[: top_k or settings.top_k_final]:
            h.score = float(s)
            out.append(h)
        return out


class NoOpReranker:
    """Keep the recall backend's ordering; just truncate to top_k.

    Not a placeholder -- measured to be the best fast option here. Dense recall with
    BGE-M3 already orders well, and the lexical reranker *discards* that ordering in
    favour of keyword overlap, which is precisely what fails on the paraphrased queries
    the golden set is built from.
    """

    def rerank(self, query: str, hits: list[Hit], top_k: int | None = None) -> list[Hit]:
        return hits[: top_k or settings.top_k_final]


def get_reranker(backend: str | None = None):
    """Return a reranker. ``RERANK_BACKEND``: auto | none | cross-encoder | lexical.

    ``auto`` resolves to ``NoOpReranker``, on measurement rather than taste. Over the
    32-query golden set with dense recall, on CPU:

    ========================  ======  =======  ==========
    rerank                      MRR   nDCG@5    ms/query
    ========================  ======  =======  ==========
    none (recall order)       0.6953   0.7145         0.2
    lexical                   0.6120   0.6426         0.5
    TinyBERT-L-2 (4M, EN)     0.3031   0.3167        22.7
    MiniLM-L-6 (22M, EN)      0.3328   0.3436       221.1
    bge-reranker-v2-m3        0.8047   0.7984      2776.4
    ========================  ======  =======  ==========

    Three things follow.

    **Lexical reranking is worse than none.** It replaces the dense model's ordering with
    keyword overlap, which is exactly what loses on paraphrased queries. ``auto`` used to
    return it; that cost quality for no benefit.

    **English-only cross-encoders are not a shortcut.** The small ms-marco models are
    fast and roughly halve MRR on this German corpus, landing below no reranking at all.
    Reranker size was never the constraint; language coverage is.

    **The multilingual cross-encoder is worth a lot and costs too much.** +0.11 MRR over
    recall order, at ~2.8 s per query steady-state against ~16 ms for recall, so over 99%
    of query latency -- and ~5.2 s on the first call, before torch warms up. Fine
    offline, impossible inside a phone call. It is therefore opt-in: an earlier version
    returned it whenever ``sentence_transformers`` merely happened to be importable, so
    installing the embedding dependency silently put a multi-second rerank into the live
    voice path. Eval and CI set ``cross-encoder`` explicitly; the agent leaves it on
    ``auto``.
    """
    backend = backend or os.getenv("RERANK_BACKEND", "auto")
    if backend == "cross-encoder":
        return CrossEncoderReranker()
    if backend == "lexical":
        return LexicalReranker()
    return NoOpReranker()
