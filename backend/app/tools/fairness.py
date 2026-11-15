"""Fairness tools. Owner: Imane (task I1).

PLACEHOLDER: only the individual flip test is implemented. Group metrics
(demographic parity difference, equalized odds difference) must be computed
with Fairlearn on the test set and returned in `metrics`.
"""
from __future__ import annotations

from app import config
from app.schemas import LoanApplication
from app.tools.scoring import score_applicant

_FLIP = {"sex": {"male": "female", "female": "male"}}


def sensitive_flip_test(app: LoanApplication) -> tuple[bool, dict[str, float]]:
    """True when the decision is unchanged after flipping each sensitive attribute."""
    base = score_applicant(app)
    passed = True
    metrics: dict[str, float] = {}
    for feat in config.SENSITIVE_FEATURES:
        flipped = app.model_copy(update={feat: _FLIP[feat][getattr(app, feat)]})
        other = score_applicant(flipped)
        metrics[f"flip_delta_{feat}"] = round(abs(other.default_probability - base.default_probability), 4)
        if other.decision != base.decision:
            passed = False
    return passed, metrics


def group_fairness_metrics() -> dict[str, float]:
    """TODO(I1): Fairlearn MetricFrame on the held-out test set."""
    return {}
