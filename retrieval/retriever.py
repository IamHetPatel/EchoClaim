"""Query-time retrieval: recall -> rerank -> cited chunks.

This is what the ``coverage_lookup`` tool calls. It always returns citations so the
agent answer can be checked for groundedness, and a ``low_confidence`` flag so the agent
falls back to "a specialist will confirm" instead of inventing coverage.

See echoclaim-spine/BUILD_PLAN.md sections 3.5 and 3.9.
"""
from __future__ import annotations

from dataclasses import dataclass

from .backends import default_backend
from .config import settings
from .rerank import get_reranker


@dataclass
class RetrievedChunk:
    text: str
    clause_id: str       # citation, e.g. "KK-300:§ 4"
    section_path: str
    score: float

    def cite(self) -> str:
        return f"[{self.clause_id}] {self.text}"


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    version: str          # which embedding version / backend served this read
    low_confidence: bool  # true -> caller should trigger the fallback ladder

    @property
    def top(self) -> RetrievedChunk | None:
        return self.chunks[0] if self.chunks else None


class Retriever:
    def __init__(self, backend=None, reranker=None):
        self.backend = backend or default_backend()
        self.reranker = reranker or get_reranker()

    def retrieve(
        self,
        query: str,
        *,
        product_code: str | None = None,
        lang: str = "de",
        min_score: float = 0.2,
    ) -> RetrievalResult:
        hits = self.backend.query(
            query, product_code=product_code, lang=lang, limit=settings.top_k_recall
        )
        ranked = self.reranker.rerank(query, hits, top_k=settings.top_k_final)
        chunks = [
            RetrievedChunk(
                text=h.text,
                clause_id=h.clause_id,
                section_path=h.payload.get("section_path", ""),
                score=h.score,
            )
            for h in ranked
        ]
        low_conf = (not chunks) or (chunks[0].score < min_score)
        return RetrievalResult(
            chunks=chunks, version=self.backend.active_version(), low_confidence=low_conf
        )
