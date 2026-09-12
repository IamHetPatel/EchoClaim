"""Structure-aware chunking for policy / regulatory documents.

German insurance policies are hierarchical (Teil -> § -> Absatz -> Satz). Fixed-length
windows shred a clause across chunk boundaries and wreck retrievability, so we split on
structure first and only fall back to token windows when a single clause exceeds the
token budget. Each chunk keeps the metadata that doubles as the citation source and the
Qdrant filter keys (product_code, lang, ...).

See echoclaim-spine/BUILD_PLAN.md section 3.1.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass


# Fixed namespace so ids are reproducible across machines and CI runs.
_POINT_NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def stable_point_id(doc_id: str, clause_id: str) -> str:
    """Deterministic Qdrant point id for a clause. Same clause -> same id, always."""
    return str(uuid.uuid5(_POINT_NS, f"{doc_id}\x00{clause_id}"))


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
    id: str = ""

    def __post_init__(self) -> None:
        # Qdrant point ids must be stable across ingests, or re-ingesting the same
        # corpus inserts duplicate points instead of updating them (and the migration
        # backfill silently doubles the collection). Derive the id from the citation
        # key so the same clause always lands on the same point.
        if not self.id:
            self.id = stable_point_id(self.doc_id, self.clause_id)

    def payload(self) -> dict:
        """Qdrant payload. Also the citation source and the filter keys."""
        return {
            "doc_id": self.doc_id,
            "section_path": self.section_path,
            "clause_id": self.clause_id,
            "doc_type": self.doc_type,
            "product_code": self.product_code,
            "lang": self.lang,
            "text": self.text,
        }


# Matches German clause markers like "§ 4", "Teil B", numbered headings "4.2 ...".
_SECTION_RE = re.compile(r"(?m)^(?:\s*)(§\s*\d+[a-z]?|Teil\s+[A-Z0-9]+|\d+(?:\.\d+)*\s+\S)")


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token). Swap for a real tokenizer if needed."""
    return max(1, len(text) // 4)


def split_on_structure(raw: str) -> list[tuple[str, str]]:
    """Return [(section_marker, body)] by splitting on structural markers.

    The corpus loader hands us plain text; for PDFs a layout parser would feed
    already-segmented sections here instead of the regex.
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
    """Secondary split: token-budgeted word windows with overlap, for oversized clauses.

    Word count per window is derived from *this* text's actual char/token density
    rather than a fixed guess, so a budget expressed in tokens maps to a sensible
    number of words regardless of how long the words are.
    """
    words = text.split()
    if estimate_tokens(text) <= max_tokens or not words:
        return [text]
    tok_per_word = max(1.0, estimate_tokens(text) / len(words))
    words_per_window = max(1, int(max_tokens / tok_per_word))
    overlap_words = min(words_per_window - 1, max(0, int(overlap / tok_per_word)))
    step = max(1, words_per_window - overlap_words)
    out: list[str] = []
    for i in range(0, len(words), step):
        out.append(" ".join(words[i:i + words_per_window]))
        if i + words_per_window >= len(words):
            break
    return out


def _is_container_heading(marker: str, body: str) -> bool:
    """A 'Teil X ...' line with no clause text of its own is a structural container,
    not a citable clause. Its child paragraphs carry the content, so we don't index the
    bare heading (it otherwise wins short-document matches and pollutes citations)."""
    if not marker.startswith("Teil"):
        return False
    return not any(p in body for p in ".!?") and len(body) < 80


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
        if not body or _is_container_heading(marker, body):
            continue
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
