"""Scoring model runtime: encoder, calibrated LightGBM booster, exact SHAP.

Artifacts are plain text (LightGBM model file + JSON metadata), so loading
does not depend on pickle or on matching library versions.

Probability of default:
    raw   = booster raw score (log-odds)
    logit = a * raw + b            (Platt calibration fitted on out-of-fold scores)
    p     = sigmoid(logit)

Because the calibration is affine in log-odds, TreeSHAP contributions
multiplied by `a` add up exactly to the calibrated log-odds.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

import lightgbm as lgb
import numpy as np
import pandas as pd

from app.domain.features import BY_NAME, MONOTONE_INCREASING, VARIANT_FEATURES

ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT / "ml" / "models"


class Encoder:
    """One-hot encoding with a fixed, documented column order."""

    def __init__(self, variant: str = "full"):
        self.variant = variant
        self.features = VARIANT_FEATURES[variant]
        self.columns: list[str] = []
        self.owner: list[str] = []  # original attribute behind each column
        for name in self.features:
            f = BY_NAME[name]
            if f.kind == "categorical":
                for v in f.values:
                    self.columns.append(f"{name}={v}")
                    self.owner.append(name)
            else:
                self.columns.append(name)
                self.owner.append(name)
        self._index = {c: i for i, c in enumerate(self.columns)}

    def transform(self, rows: pd.DataFrame | Iterable[Mapping]) -> np.ndarray:
        df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
        X = np.zeros((len(df), len(self.columns)), dtype=np.float64)
        for name in self.features:
            f = BY_NAME[name]
            col = df[name].to_numpy()
            if f.kind == "categorical":
                for v in f.values:
                    X[:, self._index[f"{name}={v}"]] = col == v
            else:
                X[:, self._index[name]] = col.astype(np.float64)
        return X

    def monotone_constraints(self) -> list[int]:
        return [1 if c in MONOTONE_INCREASING else 0 for c in self.columns]


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


class ScoringModel:
    def __init__(self, booster: lgb.Booster, meta: dict):
        self.booster = booster
        self.meta = meta
        self.variant: str = meta["variant"]
        self.encoder = Encoder(self.variant)
        assert self.encoder.columns == meta["columns"], "feature definition changed since training"
        self.a: float = meta["calibration"]["a"]
        self.b: float = meta["calibration"]["b"]
        self.threshold: float = meta["threshold"]
        self.version: str = meta["version"]

    @classmethod
    def load(cls, variant: str = "full", directory: Path = MODEL_DIR) -> "ScoringModel":
        model_file = directory / f"model_{variant}.txt"
        if not model_file.exists():
            raise FileNotFoundError(f"{model_file} is missing. Run: python ml/train.py")
        meta = json.loads((directory / f"model_{variant}.json").read_text(encoding="utf-8"))
        return cls(lgb.Booster(model_file=str(model_file)), meta)

    def raw(self, rows) -> np.ndarray:
        return self.booster.predict(self.encoder.transform(rows), raw_score=True)

    def predict_default(self, rows) -> np.ndarray:
        """Calibrated probability of default for each row."""
        return _sigmoid(self.a * self.raw(rows) + self.b)

    def predict_proba(self, rows) -> np.ndarray:
        """scikit-learn style output: column 0 = repays, column 1 = defaults."""
        p = self.predict_default(rows)
        return np.column_stack([1 - p, p])

    def contributions(self, row: Mapping) -> tuple[dict[str, float], float]:
        """Exact TreeSHAP per original attribute, in calibrated log-odds.

        Returns (contributions, base_value) with
        sum(contributions) + base_value == calibrated log-odds of the row.
        """
        contrib = self.booster.predict(self.encoder.transform([row]), pred_contrib=True)[0]
        per_feature: dict[str, float] = {}
        for value, owner in zip(contrib[:-1], self.encoder.owner):
            per_feature[owner] = per_feature.get(owner, 0.0) + self.a * float(value)
        return per_feature, self.a * float(contrib[-1]) + self.b


@lru_cache(maxsize=4)
def get_model(variant: str = "full") -> ScoringModel:
    return ScoringModel.load(variant)
