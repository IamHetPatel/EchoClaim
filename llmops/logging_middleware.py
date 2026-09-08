"""PII-redacted trace logging around the agent's model call.

One row per turn is what turns telemetry into a learning signal: llmops.drift_monitor
reads these rows back to compare a recent window against a reference window.

Persists one row per turn: prompt version, retrieved clause ids, response, judge
scores, latency, token counts. Reuses the repo's existing `agent/pii_redact.py` as the
redactor. In a regulated insurance context this audit trail is a feature.

"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:  # reuse the real redactor when running inside the repo
    from agent.pii_redact import redact  # type: ignore
except Exception:  # scaffold fallback
    def redact(text: str) -> str:  # noqa: D401
        return text


@dataclass
class TraceRecord:
    trace_id: str
    ts: float
    prompt_ref: str                 # e.g. "jamie_system@1.0.0+abcd1234"
    retrieved_ids: list[str] = field(default_factory=list)
    response: str = ""
    embedding_version: str | None = None
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    groundedness: float | None = None
    top_score: float | None = None   # top rerank score; feeds the drift monitor's PSI


class TraceLogger:
    def __init__(self, path: str = "logs/traces.sqlite"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.execute("CREATE TABLE IF NOT EXISTS traces (trace_id TEXT PRIMARY KEY, ts REAL, data TEXT)")

    def write(self, rec: TraceRecord) -> None:
        d = asdict(rec)
        d["response"] = redact(d["response"])  # never store raw PII
        self.con.execute("INSERT OR REPLACE INTO traces VALUES (?,?,?)",
                         (rec.trace_id, rec.ts, json.dumps(d, ensure_ascii=False)))
        self.con.commit()


_logger = TraceLogger()


@contextmanager
def trace(prompt_ref: str, **fields):
    """Wrap a model call:

        with trace(prompt.ref, embedding_version=ver) as rec:
            rec.retrieved_ids = [c.clause_id for c in chunks]
            resp = gemini(...)
            rec.response = resp.text
    """
    rec = TraceRecord(trace_id=str(uuid.uuid4()), ts=time.time(), prompt_ref=prompt_ref, **fields)
    t0 = time.perf_counter()
    try:
        yield rec
    finally:
        rec.latency_ms = (time.perf_counter() - t0) * 1000
        _logger.write(rec)
