"""Counterfactual tools. Owner: Marouane (task M3).

PLACEHOLDER: fixed candidate changes stand in for DiCE. The first attempt
deliberately proposes a change on an immutable feature so the verifier loop
can be observed end to end. Replace `generate_counterfactuals` with dice-ml
and keep the re-scoring step: a counterfactual is only `valid` if the model
decision really flips.
"""
from __future__ import annotations

from app import config
from app.schemas import Counterfactual, FeatureChange, LoanApplication
from app.tools.scoring import score_applicant


def check_actionability(changes: list[FeatureChange]) -> tuple[bool, str | None]:
    touched = [c.feature for c in changes if c.feature in config.IMMUTABLE_FEATURES]
    if touched:
        return False, f"changes immutable feature(s): {', '.join(touched)}"
    return True, None


def _candidates(app: LoanApplication, attempt: int) -> list[dict]:
    if attempt == 1:
        return [{"age": min(app.age + 15, 75)}]
    shorter = max(6, int(app.duration_months * 0.5))
    smaller = round(app.credit_amount * 0.6, -2)
    return [
        {"duration_months": shorter},
        {"duration_months": shorter, "credit_amount": smaller},
        {"credit_amount": smaller, "savings": "medium"},
    ]


def generate_counterfactuals(app: LoanApplication, attempt: int) -> list[Counterfactual]:
    out: list[Counterfactual] = []
    for cand in _candidates(app, attempt):
        changes = [
            FeatureChange(feature=k, from_value=getattr(app, k), to_value=v) for k, v in cand.items()
        ]
        rescored = score_applicant(app.model_copy(update=cand))
        actionable, reason = check_actionability(changes)
        out.append(
            Counterfactual(
                changes=changes,
                new_probability=rescored.default_probability,
                valid=rescored.decision == "approved",
                actionable=actionable,
                rejection_reason=reason,
            )
        )
    return out
