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
    """Applicant file. Attributes of the Statlog German Credit dataset,
    decoded into readable values (see app/domain/features.py)."""

    applicant_id: str = "NEW"
    # loan request
    credit_amount: int = Field(ge=250, le=20000)
    duration_months: int = Field(ge=4, le=72)
    purpose: Literal["car_new", "car_used", "furniture", "radio_tv", "appliances", "repairs",
                     "education", "retraining", "business", "other"]
    installment_rate: int = Field(ge=1, le=4)
    other_debtors: Literal["none", "co_applicant", "guarantor"] = "none"
    # financial situation
    checking_status: Literal["negative", "low", "high", "no_account"]
    savings: Literal["lt_100", "100_to_500", "500_to_1000", "ge_1000", "unknown"]
    credit_history: Literal["no_credits", "all_paid_here", "existing_paid", "past_delays", "critical"]
    existing_credits: int = Field(ge=1, le=4)
    other_installment_plans: Literal["bank", "stores", "none"] = "none"
    property: Literal["real_estate", "savings_insurance", "car_other", "none"]
    # employment and housing
    employment: Literal["unemployed", "lt_1y", "1_to_4y", "4_to_7y", "ge_7y"]
    job: Literal["unskilled_non_resident", "unskilled_resident", "skilled", "highly_skilled"]
    housing: Literal["rent", "own", "free"]
    residence_since: int = Field(ge=1, le=4)
    telephone: bool = False
    # personal
    age: int = Field(ge=18, le=80)
    sex: Literal["male", "female"]
    dependents: int = Field(ge=1, le=2)
    foreign_worker: bool = True

    def features(self) -> dict[str, Any]:
        return self.model_dump(exclude={"applicant_id"})


class Factor(BaseModel):
    feature: str
    label: str
    value: Any
    value_label: str
    contribution: float  # exact SHAP value in log-odds, positive raises the default risk


class ScoreResult(BaseModel):
    default_probability: float = Field(ge=0, le=1)
    threshold: float
    decision: Decision
    risk_band: Literal["low", "medium", "high"]
    base_probability: float = 0.0  # model output for an average applicant
    top_factors: list[Factor] = []
    model_version: str = ""


class FeatureChange(BaseModel):
    feature: str
    label: str = ""
    from_value: Any
    to_value: Any
    from_label: str = ""
    to_label: str = ""


class Counterfactual(BaseModel):
    changes: list[FeatureChange]
    new_probability: float
    valid: bool  # the model decision really flips after re-scoring
    actionable: bool  # no fixed or protected attribute touched, direction rules respected
    rejection_reason: str | None = None
    robust: bool = False  # new probability clears the threshold with a safety margin
    effort: Literal["immediate", "medium_term"] = "immediate"
    cost: float = 0.0  # weighted size of the change, lower is easier
    source: Literal["exhaustive", "dice"] = "exhaustive"
    statement: str = ""  # plain-language wording built from the labels


class SimilarCase(BaseModel):
    applicant_id: str
    distance: float
    defaulted: bool
    credit_amount: int
    duration_months: int


class AnalystReport(BaseModel):
    warnings: list[str] = []
    peer_default_rate: float | None = None  # observed default rate among similar past applicants
    peer_count: int = 0
    peers: list[SimilarCase] = []
    note: str = ""


class ToolCall(BaseModel):
    """One tool invocation made by an agent, kept for the audit trail."""

    name: str
    arguments: dict[str, Any] = {}
    result: str = ""
    duration_ms: float = 0.0


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
    node: str = ""
    status: Literal["completed", "rejected", "escalated", "finished", "error"]
    message: str
    reasoning: str = ""  # agent's own account of its step (LLM text or deterministic fallback)
    mode: Literal["llm", "rules"] = "rules"
    tool_calls: list[ToolCall] = []
    payload: dict[str, Any] = {}
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
