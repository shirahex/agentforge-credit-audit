from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.schemas import (AnalystReport, AuditDecision, Counterfactual, FairnessVerdict, LoanApplication,
                         ScoreResult, ToolCall)


class AuditState(TypedDict, total=False):
    application: LoanApplication
    # Set for durable runs. With a run id, the audit leaves a trace, a report and a case in the store;
    # without one (tests, batch statistics) the graph has no side effect.
    run_id: str
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
    review: dict[str, Any]  # reviewer's answer, written when the human interrupt is resumed
    # One record per finished step, appended by the graph (see graph/build.py). The API events,
    # the JSONL trace and the PDF report are all built from this list.
    trail: Annotated[list[dict[str, Any]], operator.add]
    # Written by every agent for the audit trail
    log: str  # one-line outcome of the step
    reasoning: str  # the agent's own account of the step
    mode: str  # "llm" or "rules"
    tool_calls: list[ToolCall]
    status: str
