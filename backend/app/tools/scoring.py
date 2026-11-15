"""Scoring and explanation tools (task M3).

`score_applicant` returns the calibrated default probability, the decision
and the main factors. Factors are exact TreeSHAP values computed by
LightGBM, summed per attribute and expressed in calibrated log-odds.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from app import config
from app.domain.features import BY_NAME
from app.domain.model import ScoringModel, get_model
from app.schemas import Factor, LoanApplication, ScoreResult


def model() -> ScoringModel:
    return get_model(config.MODEL_VARIANT)


def threshold() -> float:
    return config.REFUSAL_THRESHOLD if config.REFUSAL_THRESHOLD is not None else model().threshold


def probabilities(rows: Iterable[dict]) -> np.ndarray:
    """Default probability for many attribute dictionaries in one model call."""
    return model().predict_default(list(rows))


def risk_band(p: float) -> str:
    t = threshold()
    return "low" if p < t else "medium" if p < max(0.5, 2 * t) else "high"


def explain_applicant(app: LoanApplication, top_k: int = 6) -> tuple[list[Factor], float]:
    """Exact SHAP factors of one applicant and the model's base probability."""
    row = app.features()
    contrib, base = model().contributions(row)
    top = sorted(contrib.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_k]
    factors = [
        Factor(feature=name, label=BY_NAME[name].label, value=row[name],
               value_label=BY_NAME[name].label_of(row[name]), contribution=round(c, 4))
        for name, c in top
    ]
    return factors, round(1 / (1 + math.exp(-base)), 4)


def score_applicant(app: LoanApplication, explain: bool = True) -> ScoreResult:
    m = model()
    p = float(m.predict_default([app.features()])[0])
    factors, base = explain_applicant(app) if explain else ([], 0.0)
    return ScoreResult(
        default_probability=round(p, 4), threshold=threshold(),
        decision="refused" if p >= threshold() else "approved", risk_band=risk_band(p),
        base_probability=base, top_factors=factors, model_version=m.version,
    )
