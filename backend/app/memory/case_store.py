"""Persistent store of past audits, with a similarity search (task I3).

Every closed audit is kept in SQLite with its file and its outcome. Before a
new file is scored, the Analyste-Dossier asks the store for the most similar
files already audited; the Arbitre et Rédacteur uses the same search to
check that a near-identical file did not receive the opposite outcome.

Similarity is 1 minus the Gower distance on the non-protected attributes:
two files are never matched because of sex, age or nationality.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.memory.db import connect
from app.schemas import AuditDecision, LoanApplication, PastAudit
from app.tools.fairness import gower_distance

# Below this similarity a past audit is not a precedent worth citing.
MIN_SIMILARITY = 0.85
# At or above this similarity two files are the same case for the consistency check.
SAME_CASE_SIMILARITY = 0.97


def add(app: LoanApplication, decision: AuditDecision, run_id: str, model_version: str = "") -> None:
    """Stores a closed audit. Storing the same run again replaces it (a review closes it a second time)."""
    cfs = decision.counterfactuals
    best = min(cfs, key=lambda c: c.cost).statement if cfs else ""
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, app.applicant_id, datetime.now(timezone.utc).isoformat(), decision.decision,
             decision.final_outcome or decision.decision, decision.default_probability, int(decision.escalated),
             int(decision.review is not None), decision.attempts, len(cfs), best, model_version,
             json.dumps(app.features())))


def search(app: LoanApplication, k: int = 3, min_similarity: float = MIN_SIMILARITY,
           exclude_run: str | None = None) -> list[PastAudit]:
    """The k most similar files already audited, most similar first.

    Several audits of the same applicant are reduced to the most recent one.
    """
    with connect() as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY closed_at DESC").fetchall()
    target = app.features()
    found: list[PastAudit] = []
    seen: set[str] = set()
    for row in rows:
        if row["run_id"] == exclude_run:
            continue
        past = json.loads(row["application"])
        key = json.dumps(past, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        similarity = 1 - gower_distance(target, past)
        if similarity < min_similarity:
            continue
        found.append(PastAudit(
            run_id=row["run_id"], applicant_id=row["applicant_id"], similarity=round(similarity, 4),
            decision=row["decision"], final_outcome=row["final_outcome"],
            default_probability=row["default_probability"], escalated=bool(row["escalated"]),
            reviewed=bool(row["reviewed"]), attempts=row["attempts"], paths=row["paths"],
            best_path=row["best_path"], closed_at=row["closed_at"]))
    found.sort(key=lambda p: (-p.similarity, p.closed_at))
    return found[:k]


def count() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]


def clear() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM cases")
