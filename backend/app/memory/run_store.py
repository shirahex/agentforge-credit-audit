"""Persistent store of runs and of their events (task I4).

Replaces the in-memory dictionary of the first API: the history, the event
stream and the review state survive a restart of the backend.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.memory.db import connect
from app.schemas import LoanApplication

RUNNING, AWAITING_REVIEW, FINISHED, ERROR = "running", "awaiting_review", "finished", "error"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(run_id: str, application: LoanApplication) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO runs (run_id, applicant_id, application, status, started_at) VALUES (?, ?, ?, ?, ?)",
                     (run_id, application.applicant_id, application.model_dump_json(), RUNNING, _now()))


def add_event(run_id: str, seq: int, body: dict[str, Any]) -> None:
    """Idempotent: a step replayed after a restart overwrites its own event."""
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO events (run_id, seq, body) VALUES (?, ?, ?)",
                     (run_id, seq, json.dumps(body, ensure_ascii=False, default=str)))


def events(run_id: str, after: int = -1) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT body FROM events WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, after)).fetchall()
    return [json.loads(r["body"]) for r in rows]


def event_count(run_id: str) -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM events WHERE run_id = ?", (run_id,)).fetchone()[0]


def update(run_id: str, *, status: str | None = None, decision: dict | None = None, review: dict | None = None,
           error: str | None = None, finished: bool = False) -> None:
    fields, values = [], []
    for column, value in (("status", status), ("error", error)):
        if value is not None:
            fields.append(f"{column} = ?")
            values.append(value)
    for column, value in (("decision", decision), ("review", review)):
        if value is not None:
            fields.append(f"{column} = ?")
            values.append(json.dumps(value, ensure_ascii=False, default=str))
    if finished:
        fields.append("finished_at = ?")
        values.append(_now())
    if fields:
        with connect() as conn:
            conn.execute(f"UPDATE runs SET {', '.join(fields)} WHERE run_id = ?", (*values, run_id))


def _row(row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"], "applicant_id": row["applicant_id"], "status": row["status"],
        "application": json.loads(row["application"]), "started_at": row["started_at"],
        "finished_at": row["finished_at"], "error": row["error"],
        "decision": json.loads(row["decision"]) if row["decision"] else None,
        "review": json.loads(row["review"]) if row["review"] else None,
    }


def get(run_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return _row(row) if row else None


def status(run_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT status FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return row["status"] if row else None


def list_runs(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def with_status(wanted: str) -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT run_id FROM runs WHERE status = ? ORDER BY started_at", (wanted,)).fetchall()
    return [r["run_id"] for r in rows]
