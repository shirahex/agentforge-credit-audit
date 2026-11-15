"""Persistent store of past audits. Owner: Imane (task I3).

TODO: SQLite table of finished audits and a similarity search so that the
Analyste-Dossier can cite comparable past files.
"""
from __future__ import annotations

from app.schemas import AuditDecision, LoanApplication

_CASES: list[tuple[LoanApplication, AuditDecision]] = []


def add(app: LoanApplication, decision: AuditDecision) -> None:
    _CASES.append((app, decision))


def search(app: LoanApplication, k: int = 3) -> list[AuditDecision]:
    return [d for _, d in _CASES[-k:]]
