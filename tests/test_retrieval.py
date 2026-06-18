"""Retrieval PR1 tests: fast, offline, no Qdrant, no model download.

Proves the ingest data path: structure-aware chunking, corpus loading, the deterministic
hash embedder, and a dry-run ingest that records the embedding version. Run with:
    EMBED_BACKEND=hash pytest -q tests/test_retrieval.py
(the ingest test forces the hash backend explicitly, so the env var is optional).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from retrieval.chunker import chunk_document, estimate_tokens, split_on_structure
from retrieval.config import settings
from retrieval.corpus import load_corpus
from retrieval.embedder import get_embedder

REPO = Path(__file__).resolve().parent.parent


# ---- chunker -------------------------------------------------------------------

def test_split_on_structure_keeps_paragraph_markers():
    raw = "§ 1 Erstes\nText eins.\n§ 2 Zweites\nText zwei."
    spans = split_on_structure(raw)
    markers = [m for m, _ in spans]
    assert "§ 1" in markers and "§ 2" in markers


def test_chunk_metadata_is_citation_ready():
    raw = "§ 4 Entwendung\n(1) Bei Entwendung ersetzt der Versicherer den Wert.\n"
    chunks = chunk_document(raw, doc_id="kk-300", doc_type="policy", product_code="KK-300")
    assert chunks
    c = chunks[0]
    assert c.clause_id.startswith("KK-300:§ 4")
    assert c.section_path == "§ 4"
    assert c.product_code == "KK-300"
    assert c.lang == "de"
    # payload carries exactly the keys the index filters + cites on
    assert {"clause_id", "section_path", "product_code", "lang", "text"} <= set(c.payload())


def test_oversized_clause_is_window_split_with_overlap():
    # One clause well over the budget must split into multiple chunks (no marker loss).
    body = "§ 9 Lang\n" + " ".join(f"wort{i}" for i in range(400))
    chunks = chunk_document(body, doc_id="d", doc_type="policy",
                            product_code=None, max_tokens=50, overlap=10)
    assert len(chunks) > 1, "oversized clause should split into multiple windows"
    assert all(c.token_count <= 80 for c in chunks), "windows should respect the token budget"
    # secondary splits get a #n suffix so each chunk has a distinct clause id
    assert any("#" in c.clause_id for c in chunks)


# ---- corpus --------------------------------------------------------------------

def test_corpus_loads_with_front_matter():
    docs = load_corpus(REPO / "data" / "policies")
    by_id = {d.doc_id: d for d in docs}
    assert "kk-300" in by_id and "vvg-auszug" in by_id
    assert by_id["kk-300"].product_code == "KK-300"
    assert by_id["kk-300"].doc_type == "policy"
    assert by_id["vvg-auszug"].doc_type == "regulation"
    assert by_id["vvg-auszug"].product_code is None
    assert "Entwendung" in by_id["kk-300"].text  # front matter stripped, body intact


# ---- embedder (hash backend) ---------------------------------------------------

def test_hash_embedder_is_deterministic_and_normalized():
    v1 = settings.version("emb_v1")
    emb = get_embedder(v1, backend="hash")
    a = emb.encode(["Stoßstangenschaden durch Parkrempler", "etwas anderes"])
    b = emb.encode(["Stoßstangenschaden durch Parkrempler", "etwas anderes"])
    assert a.shape == (2, v1.dim)
    assert np.allclose(a, b), "hash embedder must be reproducible"
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0, atol=1e-5), "vectors must be L2-normalized"
    assert not np.allclose(a[0], a[1]), "distinct text -> distinct vector"


def test_embedder_empty_input():
    emb = get_embedder(settings.version("emb_v1"), backend="hash")
    assert emb.encode([]).shape == (0, settings.version("emb_v1").dim)


# ---- ingest (dry run) ----------------------------------------------------------

def test_ingest_dry_run_records_embedding_version():
    from retrieval.ingest import ingest

    manifest = ingest(str(REPO / "data" / "policies"), dry_run=True, backend="hash")
    assert manifest["n_chunks"] > 0
    assert manifest["n_docs"] == 2
    assert settings.active_version in manifest["embedding_versions"]
    ev = manifest["embedding_versions"][settings.active_version]
    assert ev["model_id"] and ev["dim"] == settings.version(settings.active_version).dim

    # manifest is the offline index_meta: it must be persisted and re-readable
    written = json.loads(Path(settings.ingest_manifest_path).read_text(encoding="utf-8"))
    assert written["active"] == settings.active_version
    assert written["dry_run"] is True


def test_estimate_tokens_monotonic():
    assert estimate_tokens("abcd") <= estimate_tokens("abcd" * 10)
