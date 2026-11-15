"""Fairness and plausibility tools (task I1).

Three questions are answered here, each by one tool:

* `sensitive_flip_test`: does the decision on THIS file change when only a
  protected attribute changes? (individual fairness, counterfactual test)
* `group_fairness_metrics`: across the 200 held-out files, are groups
  approved at different rates, and with different error rates? Fairlearn
  computes the selection rate per group, the demographic parity difference
  and ratio, and the equalized odds difference, by sex, by age band and by
  foreign-worker status. The same metrics are computed for the model variant
  trained without protected attributes, which shows what remains through
  correlated attributes (proxies).
* `plausibility_score`: is a proposed counterfactual still a file that looks
  like real past applicants? Mean Gower distance to its k nearest training
  files, read against the same distance measured for every training file.

Conventions for the group metrics: the favourable outcome is the approval,
so y_pred = 1 means approved and y_true = 1 means the applicant repaid.
The true positive rate is the share of good payers approved, the false
positive rate the share of bad payers approved. The differences are the
same whichever outcome is taken as positive.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from fairlearn.metrics import (MetricFrame, count, demographic_parity_difference, demographic_parity_ratio,
                               equalized_odds_difference, false_positive_rate, selection_rate, true_positive_rate)

from app import config
from app.domain.features import BY_NAME, FEATURES
from app.domain.model import ROOT, get_model
from app.schemas import Counterfactual, LoanApplication, Plausibility
from app.tools import scoring
from app.tools.scoring import score_applicant

GROUP_ATTRIBUTES = ("sex", "age_group", "foreign_worker")
GROUP_LABELS = {"sex": "Sex", "age_group": "Age band", "foreign_worker": "Foreign worker"}
_DATA = ROOT / "ml" / "data" / "processed"


# --------------------------------------------------------------------------- individual test
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


# --------------------------------------------------------------------------- group metrics
def age_band(age: int | float) -> str:
    for upper, label in config.AGE_BANDS:
        if age <= upper:
            return label
    return config.AGE_BANDS[-1][1]


def group_of(app: LoanApplication | Mapping[str, Any], attribute: str) -> str:
    """Group of one applicant for a protected attribute, as named in the metrics."""
    get = (lambda k: getattr(app, k)) if isinstance(app, LoanApplication) else (lambda k: app[k])
    if attribute == "age_group":
        return age_band(get("age"))
    if attribute == "foreign_worker":
        return "foreign" if get("foreign_worker") else "non_foreign"
    return str(get(attribute))


def fairness_from_predictions(y_true: Sequence[int], y_pred: Sequence[int], groups: Sequence[str]) -> dict:
    """Fairlearn metrics for one protected attribute.

    y_true: 1 when the applicant repaid. y_pred: 1 when the file is approved.
    """
    y_true, y_pred, groups = np.asarray(y_true, dtype=int), np.asarray(y_pred, dtype=int), np.asarray(groups, dtype=str)
    frame = MetricFrame(
        metrics={"n": count, "selection_rate": selection_rate,
                 "true_positive_rate": true_positive_rate, "false_positive_rate": false_positive_rate},
        y_true=y_true, y_pred=y_pred, sensitive_features=groups)
    per_group = {
        str(name): {"n": int(row["n"]), "selection_rate": round(float(row["selection_rate"]), 4),
                    "true_positive_rate": round(float(row["true_positive_rate"]), 4),
                    "false_positive_rate": round(float(row["false_positive_rate"]), 4),
                    "small_sample": bool(row["n"] < config.FAIRNESS_MIN_GROUP)}
        for name, row in frame.by_group.iterrows()
    }
    rates = {g: v["selection_rate"] for g, v in per_group.items()}
    return {
        "groups": per_group,
        "demographic_parity_difference": round(float(demographic_parity_difference(
            y_true, y_pred, sensitive_features=groups)), 4),
        "demographic_parity_ratio": round(float(demographic_parity_ratio(
            y_true, y_pred, sensitive_features=groups)), 4),
        "equalized_odds_difference": round(float(equalized_odds_difference(
            y_true, y_pred, sensitive_features=groups)), 4),
        "least_approved": min(rates, key=rates.get), "most_approved": max(rates, key=rates.get),
    }


def _gaps(y_true: np.ndarray, y_pred: np.ndarray, codes: np.ndarray, n_groups: int) -> tuple[float, float]:
    """Demographic parity and equalized odds differences, in plain numpy (used by the bootstrap)."""
    sel, tpr, fpr = [], [], []
    for g in range(n_groups):
        mask = codes == g
        if not mask.any():
            continue
        sel.append(y_pred[mask].mean())
        good, bad = mask & (y_true == 1), mask & (y_true == 0)
        if good.any():
            tpr.append(y_pred[good].mean())
        if bad.any():
            fpr.append(y_pred[bad].mean())
    spread = lambda v: float(max(v) - min(v)) if len(v) > 1 else 0.0  # noqa: E731
    return spread(sel), max(spread(tpr), spread(fpr))


def _bootstrap(y_true: np.ndarray, y_pred: np.ndarray, groups: np.ndarray, draws: int, seed: int = 42) -> dict:
    """95% percentile interval of both differences: 200 test files leave wide margins."""
    names, codes = np.unique(groups, return_inverse=True)
    rng = np.random.default_rng(seed)
    dp, eo = [], []
    for _ in range(draws):
        idx = rng.integers(0, len(y_true), len(y_true))
        a, b = _gaps(y_true[idx], y_pred[idx], codes[idx], len(names))
        dp.append(a)
        eo.append(b)
    q = lambda v: [round(float(x), 4) for x in np.percentile(v, [2.5, 97.5])]  # noqa: E731
    return {"demographic_parity_difference": q(dp), "equalized_odds_difference": q(eo)}


@lru_cache(maxsize=1)
def _test_set() -> pd.DataFrame:
    return pd.read_csv(_DATA / "test.csv")


@lru_cache(maxsize=8)
def _group_report(variant: str, threshold: float, draws: int) -> dict:
    test = _test_set()
    probs = get_model(variant).predict_default(test.drop(columns=["default", "applicant_id"]).to_dict("records"))
    y_pred = (probs < threshold).astype(int)
    y_true = (test["default"].to_numpy() == 0).astype(int)
    attributes = {}
    for attribute in GROUP_ATTRIBUTES:
        groups = np.array([group_of(row, attribute) for row in test.to_dict("records")])
        result = fairness_from_predictions(y_true, y_pred, groups)
        result["label"] = GROUP_LABELS[attribute]
        result["ci95"] = _bootstrap(y_true, y_pred, groups, draws) if draws else None
        solid = [g for g, v in result["groups"].items() if not v["small_sample"]]
        rates = [result["groups"][g]["selection_rate"] for g in solid]
        # The alert only looks at groups large enough to be read.
        result["reliable_gap"] = round(max(rates) - min(rates), 4) if len(solid) > 1 else None
        result["alert"] = bool(len(solid) > 1 and max(rates) - min(rates) > config.FAIRNESS_TOLERANCE)
        result["four_fifths_ok"] = bool(len(solid) < 2 or min(rates) / max(rates) >= 0.8) if rates and max(rates) > 0 else True
        attributes[attribute] = result
    return {"variant": variant, "model_version": get_model(variant).version, "threshold": round(float(threshold), 4),
            "files": int(len(test)), "approval_rate": round(float(y_pred.mean()), 4), "attributes": attributes}


def _threshold_of(variant: str) -> float:
    return config.REFUSAL_THRESHOLD if config.REFUSAL_THRESHOLD is not None else get_model(variant).threshold


def group_fairness_report(variant: str | None = None, draws: int = 500) -> dict:
    """Group metrics of one model variant on the held-out test set, with bootstrap intervals."""
    variant = variant or scoring.model().variant
    return _group_report(variant, _threshold_of(variant), draws)


def group_fairness_comparison() -> dict:
    """Audited model against the variant trained without protected attributes.

    What the second column still shows is what reaches the decision through
    correlated attributes, since that model never sees sex, age or nationality.
    """
    full, unaware = group_fairness_report("full"), group_fairness_report("unaware")
    reading = []
    for attribute in GROUP_ATTRIBUTES:
        a, b = full["attributes"][attribute], unaware["attributes"][attribute]
        if a["reliable_gap"] is None:
            reading.append(f"{a['label']}: one group has fewer than {config.FAIRNESS_MIN_GROUP} test files, "
                           "so no conclusion is drawn.")
            continue
        verb = ("disappears" if b["reliable_gap"] <= 0.02 else
                "is reduced but remains through correlated attributes" if b["reliable_gap"] < a["reliable_gap"] - 0.02 else
                "remains through correlated attributes")
        reading.append(
            f"{a['label']}: approval gap of {a['reliable_gap'] * 100:.0f} points in the audited model "
            f"({a['least_approved'].replace('_', ' ')} least approved); without protected attributes it "
            f"{verb} ({b['reliable_gap'] * 100:.0f} {'point' if round(b['reliable_gap'] * 100) == 1 else 'points'}).")
    return {"full": full, "unaware": unaware, "tolerance": config.FAIRNESS_TOLERANCE,
            "min_group": config.FAIRNESS_MIN_GROUP, "reading": reading,
            "definitions": {
                "selection_rate": "share of the group's files that are approved",
                "demographic_parity_difference": "largest gap in approval rate between two groups",
                "demographic_parity_ratio": "lowest approval rate divided by the highest (four-fifths rule: at least 0.8)",
                "equalized_odds_difference": "largest gap between groups in the approval rate of good payers "
                                             "or of bad payers, whichever is larger",
            }}


def group_fairness_metrics() -> dict[str, float]:
    """Flat group metrics of the model in use, as stored in FairnessVerdict.metrics.

    Keys: dp_diff_<attribute>, dp_ratio_<attribute>, eo_diff_<attribute> and
    selection_rate_<attribute>_<group>.
    """
    report = group_fairness_report()
    out: dict[str, float] = {}
    for attribute, r in report["attributes"].items():
        out[f"dp_diff_{attribute}"] = r["demographic_parity_difference"]
        out[f"dp_ratio_{attribute}"] = r["demographic_parity_ratio"]
        out[f"eo_diff_{attribute}"] = r["equalized_odds_difference"]
        for group, v in r["groups"].items():
            out[f"selection_rate_{attribute}_{group}"] = v["selection_rate"]
    return out


def group_context(app: LoanApplication) -> list[dict]:
    """Where this applicant's own groups stand in the group metrics.

    One entry per protected attribute: the applicant's group, its approval
    rate, the best approved group, and whether the gap is a reliable alert.
    """
    report = group_fairness_report()
    out = []
    for attribute, r in report["attributes"].items():
        mine = group_of(app, attribute)
        if mine not in r["groups"]:
            continue
        solid = [g for g in r["groups"] if not r["groups"][g]["small_sample"]]
        best = max(solid, key=lambda g: r["groups"][g]["selection_rate"], default=mine)
        gap = round(r["groups"][best]["selection_rate"] - r["groups"][mine]["selection_rate"], 4)
        out.append({
            "attribute": attribute, "label": r["label"], "group": mine,
            "approval_rate": r["groups"][mine]["selection_rate"], "best_group": best,
            "best_approval_rate": r["groups"][best]["selection_rate"], "gap": gap,
            # False when the other groups hold too few test files for the comparison to mean anything.
            "comparable": len(solid) > 1 and not r["groups"][mine]["small_sample"],
            "disadvantaged": bool(r["alert"] and not r["groups"][mine]["small_sample"]
                                  and gap > config.FAIRNESS_TOLERANCE),
        })
    return out


# --------------------------------------------------------------------------- plausibility
_PLAUSIBILITY_FEATURES = [f for f in FEATURES if not f.protected]


@lru_cache(maxsize=1)
def _reference() -> dict:
    """Training files and, for each of them, the mean distance to its k nearest other files."""
    train = pd.read_csv(_DATA / "train.csv")
    nums = [f.name for f in _PLAUSIBILITY_FEATURES if f.kind == "numeric"]
    cats = [f.name for f in _PLAUSIBILITY_FEATURES if f.kind != "numeric"]
    ranges = np.array([float(train[n].max() - train[n].min()) or 1.0 for n in nums])
    num = train[nums].to_numpy(dtype=float) / ranges
    cat = train[cats].astype(str).to_numpy()
    k = config.PLAUSIBILITY_K
    own = np.empty(len(train))
    for i in range(len(train)):  # leave-one-out: a file is not its own neighbour
        d = (np.abs(num - num[i]).sum(axis=1) + (cat != cat[i]).sum(axis=1)) / (len(nums) + len(cats))
        d[i] = np.inf
        own[i] = np.sort(d)[:k].mean()
    return {"nums": nums, "cats": cats, "ranges": ranges, "num": num, "cat": cat, "own": np.sort(own),
            "limit": float(np.quantile(own, config.PLAUSIBILITY_QUANTILE)),
            "repaid": (train["default"].to_numpy() == 0), "k": k}


def _knn(row: Mapping[str, Any]) -> tuple[float, float]:
    ref = _reference()
    num = np.array([float(row[n]) for n in ref["nums"]]) / ref["ranges"]
    cat = np.array([str(row[c]) for c in ref["cats"]])
    d = (np.abs(ref["num"] - num).sum(axis=1) + (ref["cat"] != cat).sum(axis=1)) / (len(num) + len(cat))
    nearest = np.argsort(d, kind="stable")[:ref["k"]]
    return float(d[nearest].mean()), float(ref["repaid"][nearest].mean())


def gower_distance(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    """Gower distance between two files on the non-protected attributes (proximity of a counterfactual)."""
    ref = _reference()
    total = sum(abs(float(a[n]) - float(b[n])) / r for n, r in zip(ref["nums"], ref["ranges"]))
    total += sum(str(a[c]) != str(b[c]) for c in ref["cats"])
    return float(total / (len(ref["nums"]) + len(ref["cats"])))


def plausibility_score(app: LoanApplication, changes: Mapping[str, Any] | Counterfactual) -> Plausibility:
    """Realism of the file obtained by applying `changes` to `app`.

    The modified file is compared with its k nearest training files. It is
    plausible when it is no more isolated than 95% of real past applicants.
    Beyond that limit it is still accepted when the changes are not what
    isolated it: an applicant who is already unusual is not blamed for it.
    """
    if isinstance(changes, Counterfactual):
        changes = {c.feature: c.to_value for c in changes.changes}
    ref = _reference()
    base = app.features()
    d_app, _ = _knn(base)
    d_cf, repaid = _knn({**base, **changes})
    score = float((ref["own"] >= d_cf).mean())
    return Plausibility(
        score=round(score, 4), knn_distance=round(d_cf, 4), limit=round(ref["limit"], 4),
        applicant_distance=round(d_app, 4), plausible=bool(d_cf <= ref["limit"] or d_cf <= d_app + config.PLAUSIBILITY_SLACK),
        neighbours_repaid=round(repaid, 4), k=ref["k"])
