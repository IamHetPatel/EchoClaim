"""Retrieval subsystem for EchoClaim.

Grounds Jamie's coverage answers in the policy / tariff / regulation corpus instead
of generating them. Structure-aware chunking -> versioned embeddings -> Qdrant
named-vector index -> rerank -> cited clauses.

PR1 (this package so far): config, chunker, embedder, corpus loader, ingest, and the
Qdrant index wrapper. Retriever, reranker, eval, the coverage_lookup tool, and the
zero-downtime migration land in later PRs (see echoclaim-spine/BUILD_PLAN.md).
"""
