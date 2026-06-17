"""Recall backends behind the retriever.

The retriever asks a backend for top-N candidates by ``query(text, ...)``; the backend
owns *how* it recalls them. Three implementations share the interface:

* ``QdrantBackend``        — dense ANN over BGE-M3 vectors in Qdrant (production path).
* ``InMemoryDenseBackend`` — dense cosine in numpy, real embeddings but no Qdrant server
  (handy for small corpora, the PR3 eval, and CI when the model *is* installed).
* ``LexicalBackend``       — BM25 over the corpus text, zero heavy deps. The offline /
  CI / "the demo never breaks" path: genuinely relevant for keyworded German policy
  queries without a model download.

``default_backend`` selects via ``RETRIEVAL_BACKEND`` (auto|qdrant|memory-dense|lexical);
``auto`` uses Qdrant when reachable and falls back to lexical otherwise.
"""
from __future__ import annotations

import math
import os
from collections import Counter

import numpy as np

from .chunker import Chunk
from .config import settings
from .corpus import load_corpus
from .index import Hit
from .ingest import load_and_chunk
from .rerank import tokenize


class QdrantBackend:
    """Dense ANN recall from Qdrant. Probes connectivity on construction so an
    unreachable server raises here and the caller can fall back."""

    def __init__(self, embedder=None):
        from .embedder import get_embedder
        from .index import QdrantIndex

        self.index = QdrantIndex()
        self.index.client.get_collections()  # raises if server is unreachable
        self._version = self.index.get_active_version()
        self.embedder = embedder or get_embedder(settings.version(self._version))

    def active_version(self) -> str:
        return self._version

    def query(self, text: str, *, product_code=None, lang="de", limit=None) -> list[Hit]:
        qvec = self.embedder.encode_one(text)
        return self.index.search(
            qvec, version=self._version, limit=limit or settings.top_k_recall,
            product_code=product_code, lang=lang,
        )


class InMemoryDenseBackend:
    """Dense cosine recall held in numpy — real embeddings, no Qdrant server."""

    def __init__(self, chunks: list[Chunk], matrix: np.ndarray, version: str):
        self._chunks = chunks
        self._matrix = matrix  # (n, dim), normalized
        self._version = version

    @classmethod
    def from_corpus(cls, corpus_dir: str | None = None, *, backend: str | None = None):
        from .embedder import get_embedder

        chunks = load_and_chunk(corpus_dir)
        version = settings.active_version
        emb = get_embedder(settings.version(version), backend=backend)
        matrix = emb.encode([c.text for c in chunks])
        return cls(chunks, matrix, version)

    def active_version(self) -> str:
        return self._version

    def query(self, text: str, *, product_code=None, lang="de", limit=None) -> list[Hit]:
        from .embedder import get_embedder

        emb = get_embedder(settings.version(self._version))
        qvec = emb.encode_one(text)
        sims = self._matrix @ qvec  # cosine (vectors are normalized)
        order = np.argsort(-sims)
        out: list[Hit] = []
        for i in order:
            ch = self._chunks[i]
            if product_code and ch.product_code != product_code:
                continue
            if lang and ch.lang != lang:
                continue
            out.append(Hit(score=float(sims[i]), payload=ch.payload()))
            if len(out) >= (limit or settings.top_k_recall):
                break
        return out


class LexicalBackend:
    """BM25 recall over the corpus text. Dependency-free; carries no semantics, but for
    keyworded German policy questions it reliably surfaces the right clause."""

    K1 = 1.5
    B = 0.75

    def __init__(self, chunks: list[Chunk]):
        self._chunks = chunks
        self._docs = [tokenize(c.text + " " + c.section_path) for c in chunks]
        self._tf = [Counter(d) for d in self._docs]
        self._len = [len(d) for d in self._docs]
        self._avgdl = (sum(self._len) / len(self._len)) if self._len else 0.0
        df: Counter = Counter()
        for d in self._docs:
            df.update(set(d))
        n = len(self._docs)
        self._idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }

    @classmethod
    def from_corpus(cls, corpus_dir: str | None = None):
        # Build directly from chunks so it shares PR1's chunking exactly.
        load_corpus(corpus_dir or settings.corpus_dir)  # validates the corpus dir early
        return cls(load_and_chunk(corpus_dir))

    def active_version(self) -> str:
        return "lexical-bm25"

    def _score(self, q_terms: list[str], i: int) -> float:
        tf, dl = self._tf[i], self._len[i]
        s = 0.0
        for t in q_terms:
            if t not in tf:
                continue
            idf = self._idf.get(t, 0.0)
            num = tf[t] * (self.K1 + 1)
            den = tf[t] + self.K1 * (1 - self.B + self.B * dl / (self._avgdl or 1))
            s += idf * num / den
        return s

    def query(self, text: str, *, product_code=None, lang="de", limit=None) -> list[Hit]:
        q_terms = tokenize(text)
        scored: list[tuple[float, int]] = []
        for i, ch in enumerate(self._chunks):
            if product_code and ch.product_code != product_code:
                continue
            if lang and ch.lang != lang:
                continue
            s = self._score(q_terms, i)
            if s > 0:
                scored.append((s, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            Hit(score=s, payload=self._chunks[i].payload())
            for s, i in scored[: limit or settings.top_k_recall]
        ]


def default_backend():
    """Pick a recall backend from RETRIEVAL_BACKEND (auto|qdrant|memory-dense|lexical)."""
    choice = os.getenv("RETRIEVAL_BACKEND", "auto")
    if choice == "lexical":
        return LexicalBackend.from_corpus()
    if choice == "memory-dense":
        return InMemoryDenseBackend.from_corpus()
    if choice == "qdrant":
        return QdrantBackend()
    # auto: Qdrant if reachable, else the offline lexical path.
    try:
        return QdrantBackend()
    except Exception:
        return LexicalBackend.from_corpus()
