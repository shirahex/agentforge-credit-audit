from __future__ import annotations

from typing import TypedDict

from app.schemas import AuditDecision, Counterfactual, FairnessVerdict, LoanApplication, ScoreResult


class AuditState(TypedDict, total=False):
    application: LoanApplication
    warnings: list[str]
    score: ScoreResult
    counterfactuals: list[Counterfactual]
    attempts: int
    fairness: FairnessVerdict
    decision: AuditDecision
    # Short human-readable line written by the last agent, used for the event trail.
    log: str
    status: str
