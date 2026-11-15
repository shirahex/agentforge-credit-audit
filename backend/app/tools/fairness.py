"""Fairness tools. Owner: Imane (task I1).

PLACEHOLDER: only the individual flip test is implemented. Group metrics
(demographic parity difference, equalized odds difference) must be computed
with Fairlearn on the test set and returned by `group_fairness_metrics`,
and a plausibility score must be added for counterfactuals.
"""
from __future__ import annotations

from app import config
from app.domain.features import BY_NAME
from app.schemas import LoanApplication
from app.tools.scoring import score_applicant


def _flipped(app: LoanApplication, feature: str) -> LoanApplication:
    current = getattr(app, feature)
    if isinstance(current, bool):
        new = not current
    else:
        values = BY_NAME[feature].values
        new = values[(values.index(current) + 1) % len(values)]
    return app.model_copy(update={feature: new})


def sensitive_flip_test(app: LoanApplication) -> tuple[bool, dict[str, float]]:
    """True when the decision is unchanged after flipping each sensitive attribute."""
    base = score_applicant(app, explain=False)
    passed = True
    metrics: dict[str, float] = {}
    for feat in config.SENSITIVE_FEATURES:
        other = score_applicant(_flipped(app, feat), explain=False)
        metrics[f"flip_delta_{feat}"] = round(other.default_probability - base.default_probability, 4)
        if other.decision != base.decision:
            passed = False
    return passed, metrics


def group_fairness_metrics() -> dict[str, float]:
    """TODO(I1): Fairlearn MetricFrame on the held-out test set."""
    return {}
