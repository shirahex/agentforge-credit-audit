from __future__ import annotations

from typing import TypedDict

from app.schemas import (AnalystReport, AuditDecision, Counterfactual, FairnessVerdict, LoanApplication,
                         ScoreResult, ToolCall)


class AuditState(TypedDict, total=False):
    application: LoanApplication
    # Analyste-Dossier
    warnings: list[str]
    analysis: AnalystReport
    # Modèle-Scoring
    score: ScoreResult
    explanation: str
    # Générateur-Contrefactuels
    counterfactuals: list[Counterfactual]
    attempts: int
    cf_plans: list[tuple]  # plans already tried, so a failed plan is never replayed
    # Vérificateur-Équité
    fairness: FairnessVerdict
    # Arbitre et Rédacteur
    decision: AuditDecision
    # Written by every agent for the audit trail
    log: str  # one-line outcome of the step
    reasoning: str  # the agent's own account of the step
    mode: str  # "llm" or "rules"
    tool_calls: list[ToolCall]
    status: str
