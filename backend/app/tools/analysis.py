"""File analysis tools (task M3), used by the Analyste-Dossier.

* `validate_application`: consistency rules and comparison with the value
  ranges seen in the training data.
* `similar_cases`: nearest past applicants (Gower distance on non-protected
  attributes) and the default rate actually observed among them.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from app.domain.features import BY_NAME, FEATURES
from app.domain.model import ROOT
from app.schemas import LoanApplication, SimilarCase

_PEER_FEATURES = [f for f in FEATURES if not f.protected]


@lru_cache(maxsize=1)
def _history() -> pd.DataFrame:
    return pd.read_csv(ROOT / "ml" / "data" / "processed" / "train.csv")


@lru_cache(maxsize=1)
def _reference() -> dict:
    df = _history()
    monthly = df["credit_amount"] / df["duration_months"]
    return {
        "monthly_p975": float(monthly.quantile(0.975)),
        "amount_p99": float(df["credit_amount"].quantile(0.99)),
        "duration_p99": float(df["duration_months"].quantile(0.99)),
        "amount_by_purpose_p95": df.groupby("purpose")["credit_amount"].quantile(0.95).to_dict(),
    }


def validate_application(app: LoanApplication) -> list[str]:
    ref, out = _reference(), []
    monthly = app.credit_amount / app.duration_months
    if monthly > ref["monthly_p975"]:
        out.append(f"Monthly instalment of about {monthly:,.0f} DM is higher than 97.5% of past files.")
    if app.credit_amount > ref["amount_p99"]:
        out.append(f"Credit amount of {app.credit_amount:,} DM is above 99% of past files.")
    p95 = ref["amount_by_purpose_p95"].get(app.purpose)
    if p95 and app.credit_amount > p95 and app.credit_amount <= ref["amount_p99"]:
        out.append(f"Amount is unusually high for the purpose '{BY_NAME['purpose'].label_of(app.purpose).lower()}'.")
    if app.duration_months > ref["duration_p99"]:
        out.append(f"Duration of {app.duration_months} months is above 99% of past files.")
    years = {"ge_7y": 7, "4_to_7y": 4}.get(app.employment, 0)
    if years and app.age - years < 16:
        out.append("Time in employment is inconsistent with the applicant's age.")
    if app.employment == "unemployed" and app.job == "highly_skilled":
        out.append("Declared unemployed with a management or highly qualified job level.")
    if app.credit_history == "no_credits" and app.existing_credits > 1:
        out.append("Credit history states no credit taken, yet several credits are running at this bank.")
    if app.other_debtors == "none" and app.checking_status == "negative" and app.savings == "lt_100":
        out.append("No guarantor, overdrawn account and almost no savings: weak repayment buffer.")
    return out


@lru_cache(maxsize=1)
def _peer_matrix():
    df = _history()
    nums = [f.name for f in _PEER_FEATURES if f.kind == "numeric"]
    cats = [f.name for f in _PEER_FEATURES if f.kind != "numeric"]
    ranges = {n: float(df[n].max() - df[n].min()) or 1.0 for n in nums}
    return df, nums, cats, ranges


def similar_cases(app: LoanApplication, k: int = 15) -> tuple[float, list[SimilarCase]]:
    """Observed default rate among the k most similar past applicants, and the closest five."""
    df, nums, cats, ranges = _peer_matrix()
    dist = np.zeros(len(df))
    for n in nums:
        dist += np.abs(df[n].to_numpy(dtype=float) - float(getattr(app, n))) / ranges[n]
    for c in cats:
        dist += (df[c].to_numpy() != getattr(app, c)).astype(float)
    dist /= len(nums) + len(cats)
    order = np.argsort(dist, kind="stable")[:k]
    rate = float(df["default"].to_numpy()[order].mean())
    peers = [
        SimilarCase(applicant_id=str(df["applicant_id"].iloc[i]), distance=round(float(dist[i]), 3),
                    defaulted=bool(df["default"].iloc[i]), credit_amount=int(df["credit_amount"].iloc[i]),
                    duration_months=int(df["duration_months"].iloc[i]))
        for i in order[:5]
    ]
    return round(rate, 3), peers
