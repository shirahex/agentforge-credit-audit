"""Shared data contracts.

Every agent, tool, API route and frontend type is built on these models.
A change here must be agreed by both team members and mirrored in
frontend/src/types.ts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Decision = Literal["approved", "refused"]


class LoanApplication(BaseModel):
    """Simplified applicant file. Field list to be finalised in task M1
    once the German Credit attributes are mapped."""

    applicant_id: str
    duration_months: int = Field(gt=0, le=120)
    credit_amount: float = Field(gt=0)
    age: int = Field(ge=18, le=100)
    sex: Literal["male", "female"]
    purpose: str
    housing: Literal["own", "rent", "free"]
    employment_years: float = Field(ge=0)
    savings: Literal["none", "low", "medium", "high"]
    checking_status: Literal["none", "negative", "low", "high"]
    foreign_worker: bool = False


class Factor(BaseModel):
    feature: str
    value: Any
    contribution: float  # signed SHAP value, positive pushes towards default


class ScoreResult(BaseModel):
    default_probability: float = Field(ge=0, le=1)
    decision: Decision
    risk_band: Literal["low", "medium", "high"]
    top_factors: list[Factor] = []


class FeatureChange(BaseModel):
    feature: str
    from_value: Any
    to_value: Any


class Counterfactual(BaseModel):
    changes: list[FeatureChange]
    new_probability: float
    valid: bool  # the model decision really flips after re-scoring
    actionable: bool  # no immutable or protected feature is touched
    rejection_reason: str | None = None


class FairnessVerdict(BaseModel):
    passed: bool
    reasons: list[str] = []
    metrics: dict[str, float] = {}
    flip_test_passed: bool = True


class AuditDecision(BaseModel):
    applicant_id: str
    decision: Decision
    default_probability: float
    escalated: bool = False
    escalation_reason: str | None = None
    summary: str = ""
    counterfactuals: list[Counterfactual] = []
    fairness: FairnessVerdict | None = None
    attempts: int = 0
    report_path: str | None = None


class AgentEvent(BaseModel):
    """One line of the audit trail, streamed to the interface over SSE."""

    run_id: str
    seq: int
    agent: str
    status: Literal["completed", "rejected", "escalated", "finished", "error"]
    message: str
    payload: dict[str, Any] = {}
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
