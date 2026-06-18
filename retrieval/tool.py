"""``coverage_lookup``: retrieval exposed as a Gemini function-call tool.

The agent calls this to ground coverage answers in cited policy clauses; on low
confidence it returns a signal so the agent uses the fallback ladder instead of
inventing coverage. The returned dict carries a ``summary`` field (the top cited
clause) so it renders straight into the agent's existing tool-results prompt block,
and ``stub=True`` whenever the agent must NOT assert coverage (no confident match, or
retrieval unavailable), matching how the prompt treats stubbed tool output.

See echoclaim-spine/BUILD_PLAN.md sections 3.5 and 3.9.
"""
from __future__ import annotations

from .retriever import Retriever

_retriever: Retriever | None = None


def _get() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


# Gemini function-declaration schema (register alongside the Tavily tools).
COVERAGE_LOOKUP_SCHEMA = {
    "name": "coverage_lookup",
    "description": (
        "Look up whether something is covered under the caller's motor-insurance policy. "
        "Returns verbatim policy clauses with citations. Use this before stating any "
        "coverage fact; never assert coverage without a citation from this tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Coverage question in natural language."},
            "product_code": {"type": "string", "description": "Caller's tariff/product code, e.g. KK-300."},
            "lang": {"type": "string", "enum": ["de", "en"], "default": "de"},
        },
        "required": ["query"],
    },
}


def _summary(res) -> str:
    top = res.top
    text = top.text.strip().replace("\n", " ")
    if len(text) > 240:
        text = text[:240].rsplit(" ", 1)[0] + "…"
    return f"Laut {top.clause_id} ({top.section_path}): {text}"


def coverage_lookup(query: str, product_code: str | None = None, lang: str = "de") -> dict:
    """Handler invoked when Gemini calls the tool. Returns a JSON-serializable result."""
    try:
        res = _get().retrieve(query, product_code=product_code, lang=lang)
    except Exception as exc:  # retrieval down -> never assert coverage
        return {
            "stub": True,
            "summary": "Deckungsdatenbank momentan nicht erreichbar. Keine Deckungszusage "
                       "geben; den Fall notieren und einem Spezialisten zur Prüfung übergeben.",
            "low_confidence": True,
            "citations": [],
            "error": str(exc),
        }

    citations = [
        {"clause_id": c.clause_id, "section": c.section_path,
         "text": c.text, "score": round(c.score, 4)}
        for c in res.chunks
    ]
    if res.low_confidence:
        return {
            "stub": True,  # prompt: "say something general, don't quote"
            "summary": "Kein eindeutiger Treffer in den Versicherungsbedingungen. Keine "
                       "Deckungszusage geben; einem Spezialisten zur Bestätigung übergeben.",
            "low_confidence": True,
            "embedding_version": res.version,
            "citations": citations,
        }
    return {
        "stub": False,
        "summary": _summary(res),
        "low_confidence": False,
        "embedding_version": res.version,
        "citations": citations,
    }
