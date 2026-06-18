"""Retrieval PR2 tests: query path, offline (BM25 lexical backend, no Qdrant/model).

Proves: the lexical backend recalls the right clause, the retriever returns a citation
with a sane confidence flag, and the coverage_lookup tool returns the agent-facing shape
(summary + citations) and refuses to assert coverage when there's no match.
"""
from __future__ import annotations

from pathlib import Path

from retrieval.backends import LexicalBackend
from retrieval.rerank import LexicalReranker
from retrieval.retriever import Retriever

REPO = Path(__file__).resolve().parent.parent
CORPUS = str(REPO / "data" / "policies")


def _retriever() -> Retriever:
    return Retriever(backend=LexicalBackend.from_corpus(CORPUS), reranker=LexicalReranker())


# ---- backend recall ------------------------------------------------------------

def test_lexical_backend_finds_parkschaden_clause():
    b = LexicalBackend.from_corpus(CORPUS)
    hits = b.query("Sind Parkschäden an der Stoßstange in der Vollkasko gedeckt?")
    assert hits
    assert "§ 6" in hits[0].clause_id, f"expected §6, got {hits[0].clause_id}"


def test_lexical_backend_finds_selbstbeteiligung_clause():
    b = LexicalBackend.from_corpus(CORPUS)
    hits = b.query("Welche Selbstbeteiligung gilt bei der Teilkasko?")
    assert hits and "§ 4" in hits[0].clause_id
    assert "150" in hits[0].text  # the actual answer lives in the cited clause


def test_product_code_filter():
    b = LexicalBackend.from_corpus(CORPUS)
    # VVG (product_code=None) must be excluded when we filter to the tariff.
    hits = b.query("Obliegenheit Anzeige", product_code="KK-300")
    assert all(h.payload.get("product_code") == "KK-300" for h in hits)
    assert b.query("Obliegenheit", product_code="DOES-NOT-EXIST") == []


# ---- retriever -----------------------------------------------------------------

def test_retriever_returns_citation_for_in_domain_query():
    res = _retriever().retrieve("Ist Vandalismus in der Vollkasko versichert?")
    assert res.top is not None
    assert res.top.clause_id and res.top.section_path
    assert not res.low_confidence
    assert res.top.cite().startswith("[")


def test_retriever_low_confidence_for_off_domain_query():
    res = _retriever().retrieve("Wie wird das Wetter morgen in Köln?")
    assert res.low_confidence, "off-domain query must not look confident"


# ---- coverage_lookup tool ------------------------------------------------------

def test_coverage_lookup_tool_returns_agent_shape():
    from tools.coverage_lookup import DISPATCH, lookup_coverage

    assert "coverage_lookup" in DISPATCH
    out = lookup_coverage("Ist ein Parkschaden an der Stoßstange in der Vollkasko gedeckt?")
    assert out["stub"] is False
    assert not out["low_confidence"]
    assert out["summary"].startswith("Laut ")          # renders into the prompt's tool block
    assert out["citations"] and out["citations"][0]["clause_id"]


def test_coverage_lookup_refuses_when_no_match():
    from tools.coverage_lookup import lookup_coverage

    out = lookup_coverage("Wie spät ist es in Tokio?")
    assert out["low_confidence"] is True
    assert out["stub"] is True               # prompt: "say something general, don't quote"
    assert "Spezialist" in out["summary"] or "specialist" in out["summary"].lower()


# ---- agent glue: the citation must reach Jamie's system prompt ------------------

def test_cited_clause_reaches_jamie_system_prompt():
    """The PR2 acceptance criterion: a coverage answer is grounded in a cited clause
    that the agent actually sees. Mirrors how run_demo_text.py feeds tool_results in."""
    import json

    from agent.claim_state import ClaimState
    from agent.prompts import build_jamie_system_prompt
    from tools.coverage_lookup import lookup_coverage

    crm = json.loads((REPO / "data" / "crm" / "max_mueller.json").read_text(encoding="utf-8"))
    result = lookup_coverage("Ist ein Parkschaden an der Stoßstange in der Vollkasko gedeckt?")
    prompt = build_jamie_system_prompt(
        crm, ClaimState(call_id="t"),
        tool_results=[{"name": "coverage_lookup", "result": result}],
    )
    assert "KK-300:§ 6" in prompt           # the exact clause citation is in the prompt
    assert "Vollkasko" in prompt
