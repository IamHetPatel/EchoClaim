"""Structure-aware chunking for policy / regulatory documents.

Policies are hierarchical (Teil -> § -> Absatz -> Satz). Fixed-length windows shred
a clause across chunk boundaries and wreck retrievability, so we split on structure
first and only fall back to token windows when a single clause is too large.

See BUILD_PLAN.md section 3.1.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field


@dataclass
class Chunk:
    text: str
    doc_id: str
    section_path: str           # e.g. "Teil B / §4 / Abs. 2"
    clause_id: str              # stable id for citation, e.g. "KK-300:§4(2)"
    doc_type: str               # "policy" | "regulation" | "claim" | "faq"
    product_code: str | None    # tariff/product filter key, e.g. "KK-300"
    lang: str = "de"
    token_count: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def payload(self) -> dict:
        """Qdrant payload — also the citation source and the filter keys."""
        return {
            "doc_id": self.doc_id,
            "section_path": self.section_path,
            "clause_id": self.clause_id,
            "doc_type": self.doc_type,
            "product_code": self.product_code,
            "lang": self.lang,
            "text": self.text,
        }


# Matches German clause markers like "§ 4", "Abs. 2", numbered headings, etc.
_SECTION_RE = re.compile(r"(?m)^(?:\s*)(§\s*\d+[a-z]?|Teil\s+[A-Z0-9]+|\d+(?:\.\d+)*\s+\S)")


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token). Swap for a real tokenizer if needed."""
    return max(1, len(text) // 4)


def split_on_structure(raw: str) -> list[tuple[str, str]]:
    """Return [(section_marker, body)] by splitting on structural markers.

    TODO: replace the regex with a real layout/heading parser for PDFs
    (the corpus loader in ingest can hand us already-segmented sections).
    """
    matches = list(_SECTION_RE.finditer(raw))
    if not matches:
        return [("", raw.strip())]
    spans: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        marker = m.group(1).strip()
        spans.append((marker, raw[start:end].strip()))
    return spans


def _window(text: str, max_tokens: int, overlap: int) -> list[str]:
    """Secondary split: sliding token windows with overlap, for oversized clauses."""
    words = text.split()
    if estimate_tokens(text) <= max_tokens:
        return [text]
    approx_words = max_tokens * 4 // 1  # rough words-per-window from char/token ratio
    step = max(1, approx_words - overlap)
    out = []
    for i in range(0, len(words), step):
        out.append(" ".join(words[i:i + approx_words]))
        if i + approx_words >= len(words):
            break
    return out


def chunk_document(
    raw: str,
    *,
    doc_id: str,
    doc_type: str,
    product_code: str | None,
    lang: str = "de",
    max_tokens: int = 400,
    overlap: int = 64,
) -> list[Chunk]:
    """Structure-first, token-window-second chunking."""
    chunks: list[Chunk] = []
    for marker, body in split_on_structure(raw):
        section_path = marker or "root"
        for j, piece in enumerate(_window(body, max_tokens, overlap)):
            clause_id = f"{product_code or doc_id}:{marker or 'root'}"
            if j > 0:
                clause_id += f"#{j}"
            chunks.append(
                Chunk(
                    text=piece,
                    doc_id=doc_id,
                    section_path=section_path,
                    clause_id=clause_id,
                    doc_type=doc_type,
                    product_code=product_code,
                    lang=lang,
                    token_count=estimate_tokens(piece),
                )
            )
    return chunks
