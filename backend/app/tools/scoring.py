"""Scoring tools. Owner: Marouane (tasks M2, M3).

PLACEHOLDER: a hand-written formula stands in for the trained model so the
graph, the API and the interface can run from day one. Replace the body of
`score_applicant` with a call to the saved model and `top_factors` with
real SHAP values. The signature must not change.
"""
from __future__ import annotations

import math

from app import config
from app.schemas import Factor, LoanApplication, ScoreResult

_SAVINGS = {"none": 0.45, "low": 0.2, "medium": -0.2, "high": -0.6}
_CHECKING = {"negative": 0.7, "none": 0.1, "low": 0.0, "high": -0.6}
_HOUSING = {"own": -0.3, "rent": 0.15, "free": 0.1}


def _contributions(app: LoanApplication) -> dict[str, float]:
    return {
        "duration_months": 0.04 * (app.duration_months - 20),
        "credit_amount": 0.00016 * (app.credit_amount - 3000),
        "age": -0.02 * (app.age - 35),
        "employment_years": -0.07 * (app.employment_years - 4),
        "savings": _SAVINGS[app.savings],
        "checking_status": _CHECKING[app.checking_status],
        "housing": _HOUSING[app.housing],
    }


def score_applicant(app: LoanApplication) -> ScoreResult:
    contrib = _contributions(app)
    p = 1 / (1 + math.exp(-(-0.9 + sum(contrib.values()))))
    decision = "refused" if p >= config.REFUSAL_THRESHOLD else "approved"
    band = "high" if p >= 0.6 else "medium" if p >= 0.35 else "low"
    top = sorted(contrib.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]
    return ScoreResult(
        default_probability=round(p, 4),
        decision=decision,
        risk_band=band,
        top_factors=[
            Factor(feature=f, value=getattr(app, f), contribution=round(c, 4)) for f, c in top
        ],
    )
