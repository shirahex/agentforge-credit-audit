"""LangGraph checkpointer on SQLite (task I3).

After every agent step LangGraph writes the whole audit state to
`checkpoints.sqlite`. A run interrupted by a crash, a restart or a human
review is resumed from its last checkpoint: finished steps are not run
again.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from app import schemas
from app.memory.db import data_dir

# The state holds Pydantic objects; the serializer only rebuilds the types listed here.
_STATE_TYPES = [("app.schemas", name) for name in (
    "LoanApplication", "Factor", "ScoreResult", "FeatureChange", "Plausibility", "Counterfactual", "SimilarCase",
    "PastAudit", "AnalystReport", "ToolCall", "FairnessVerdict", "AuditDecision", "AgentEvent")]
assert all(hasattr(schemas, name) for _, name in _STATE_TYPES)


def checkpoint_file() -> Path:
    return data_dir() / "checkpoints.sqlite"


def sqlite_checkpointer(path: Path | str | None = None) -> SqliteSaver:
    conn = sqlite3.connect(str(path or checkpoint_file()), check_same_thread=False, timeout=15)
    saver = SqliteSaver(conn, serde=JsonPlusSerializer(allowed_msgpack_modules=_STATE_TYPES))
    saver.setup()
    return saver
