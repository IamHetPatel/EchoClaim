"""Coverage lookups, exposed as a Gemini function-call — same shape as tavily_lookup.

Thin demo/agent-facing wrapper over ``retrieval.tool.coverage_lookup`` so it slots into
the demo's DISPATCH and GeminiBrain's tool list exactly like the Tavily tools. Falls back
to a stub (telling Jamie not to assert coverage) if the retrieval package can't import,
so the demo never breaks.
"""
from __future__ import annotations

from typing import Any

try:
    from retrieval.tool import COVERAGE_LOOKUP_SCHEMA as _SCHEMA
    from retrieval.tool import coverage_lookup as _coverage_lookup
    _HAVE_RETRIEVAL = True
except ImportError:  # pragma: no cover - graceful degradation (missing deps only)
    _HAVE_RETRIEVAL = False
    _SCHEMA = {
        "name": "coverage_lookup",
        "description": "Look up policy coverage with cited clauses.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }


def lookup_coverage(query: str, product_code: str | None = None, lang: str = "de") -> dict[str, Any]:
    """Return cited policy clauses for a coverage question (or a safe stub)."""
    if not _HAVE_RETRIEVAL:
        return {
            "stub": True,
            "summary": "Coverage lookup unavailable — do not assert coverage; note it for a "
                       "specialist to confirm.",
            "low_confidence": True,
            "citations": [],
        }
    return _coverage_lookup(query, product_code=product_code, lang=lang)


GEMINI_TOOL_DECLS = [_SCHEMA]

DISPATCH = {
    "coverage_lookup": lookup_coverage,
}


# --- self-test -------------------------------------------------------------
if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    # Running this file directly puts tools/ on sys.path, not the repo root —
    # add the root so `import retrieval` resolves (the demo already does this).
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tools.coverage_lookup import lookup_coverage  # re-import with repo root on path

    print(json.dumps(
        lookup_coverage("Ist ein Parkschaden an der Stoßstange in der Vollkasko gedeckt?"),
        indent=2, ensure_ascii=False,
    ))
