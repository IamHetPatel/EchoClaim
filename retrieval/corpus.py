"""Corpus loader.

Reads the policy / tariff / regulation corpus from ``data/policies/*.md``. Each file
carries optional YAML front matter (delimited by ``---``) with the metadata that becomes
the chunk's citation + filter keys; the body is the clause text the chunker splits on.

    ---
    doc_id: kk-300
    doc_type: policy        # policy | regulation | claim | faq
    product_code: KK-300
    lang: de
    ---
    Teil A — ...
    § 1 ...
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class CorpusDoc:
    doc_id: str
    doc_type: str
    product_code: str | None
    lang: str
    text: str
    source_path: str


def _parse_front_matter(raw: str) -> tuple[dict, str]:
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            header = raw[3:end].strip()
            body = raw[end + 4:].lstrip("\n")
            return (yaml.safe_load(header) or {}), body
    return {}, raw


def load_doc(path: Path) -> CorpusDoc:
    meta, body = _parse_front_matter(path.read_text(encoding="utf-8"))
    return CorpusDoc(
        doc_id=str(meta.get("doc_id") or path.stem),
        doc_type=str(meta.get("doc_type") or "policy"),
        product_code=(str(meta["product_code"]) if meta.get("product_code") else None),
        lang=str(meta.get("lang") or "de"),
        text=body.strip(),
        source_path=str(path),
    )


def load_corpus(corpus_dir: str | Path) -> list[CorpusDoc]:
    root = Path(corpus_dir)
    if not root.exists():
        raise FileNotFoundError(f"corpus dir not found: {root}")
    docs = [load_doc(p) for p in sorted(root.glob("*.md"))]
    if not docs:
        raise FileNotFoundError(f"no .md corpus files in {root}")
    return docs
