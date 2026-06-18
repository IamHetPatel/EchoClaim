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

            self._model = CrossEncoder(self.model_id)
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


def get_reranker(backend: str | None = None):
    """Return a reranker. ``RERANK_BACKEND`` env: auto | cross-encoder | lexical."""
    backend = backend or os.getenv("RERANK_BACKEND", "auto")
    if backend == "lexical":
        return LexicalReranker()
    if backend == "cross-encoder":
        return CrossEncoderReranker()
    # auto: prefer the real model, fall back to lexical when the dep is absent.
    import importlib.util

    if importlib.util.find_spec("sentence_transformers") is not None:
        return CrossEncoderReranker()
    return LexicalReranker()
