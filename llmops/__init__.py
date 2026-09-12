"""LLMOps subsystem for EchoClaim.

Versioned prompts, LLM-as-judge groundedness, CI eval gating, PII-redacted trace
logging, and drift monitoring.

The gate is the entry point: ``python -m llmops.eval_gate``. Everything else exists to
give the gate something real to measure.
"""
