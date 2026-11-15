"""Scoring model training (task M2).

    python ml/train.py            # trains both variants, writes models and reports
    python ml/train.py --fast     # smaller hyperparameter search

For each variant ("full" = model under audit, "unaware" = protected
attributes removed):
  1. logistic regression baseline and LightGBM, compared by repeated
     stratified cross-validation on the training set;
  2. LightGBM hyperparameters chosen by random search on the same folds;
  3. Platt calibration fitted on out-of-fold scores;
  4. two refusal thresholds: "balanced" (maximum KS, the operating point
     used by default) and "cost_optimal" (minimum expected cost under the
     dataset's cost matrix: accepting a bad payer costs 5, refusing a good
     payer costs 1);
  5. evaluation on the untouched test set with bootstrap confidence intervals.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, roc_curve
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.model import Encoder, MODEL_DIR  # noqa: E402

DATA = ROOT / "ml" / "data" / "processed"
REPORTS = ROOT / "ml" / "reports"
SEED = 42
COST_FALSE_APPROVAL = 5.0  # bad payer accepted
COST_FALSE_REFUSAL = 1.0  # good payer refused


def ks_statistic(y, p) -> float:
    fpr, tpr, _ = roc_curve(y, p)
    return float(np.max(tpr - fpr))


def expected_cost(y, p, threshold) -> float:
    refuse = p >= threshold
    fa = np.sum((~refuse) & (y == 1)) * COST_FALSE_APPROVAL
    fr = np.sum(refuse & (y == 0)) * COST_FALSE_REFUSAL
    return float((fa + fr) / len(y))


def lgbm_params(overrides: dict, encoder: Encoder) -> dict:
    base = dict(objective="binary", learning_rate=0.03, n_estimators=300, num_leaves=8, max_depth=4,
                min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.6,
                reg_lambda=5.0, reg_alpha=0.0, min_split_gain=0.0, random_state=SEED, n_jobs=1, verbose=-1,
                monotone_constraints=encoder.monotone_constraints(), monotone_constraints_method="advanced")
    base.update(overrides)
    return base


def oof_raw_scores(X, y, params, splitter) -> np.ndarray:
    """Out-of-fold raw scores averaged over the repeats."""
    total = np.zeros(len(y))
    count = np.zeros(len(y))
    for tr, va in splitter.split(X, y):
        m = lgb.LGBMClassifier(**params).fit(X[tr], y[tr])
        total[va] += m.predict(X[va], raw_score=True)
        count[va] += 1
    return total / count


def oof_baseline(X, y, splitter) -> np.ndarray:
    total = np.zeros(len(y))
    count = np.zeros(len(y))
    for tr, va in splitter.split(X, y):
        m = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000)).fit(X[tr], y[tr])
        total[va] += m.predict_proba(X[va])[:, 1]
        count[va] += 1
    return total / count


def sample_configs(n: int, rng: np.random.Generator) -> list[dict]:
    configs = [{}]
    for _ in range(n - 1):
        configs.append(dict(
            learning_rate=float(rng.choice([0.02, 0.03, 0.05])),
            n_estimators=int(rng.choice([150, 250, 400, 600])),
            num_leaves=int(rng.choice([4, 6, 8, 12])),
            max_depth=int(rng.choice([2, 3, 4, 5])),
            min_child_samples=int(rng.choice([10, 20, 30, 40])),
            colsample_bytree=float(rng.choice([0.4, 0.6, 0.8])),
            subsample=float(rng.choice([0.7, 0.85, 1.0])),
            reg_lambda=float(rng.choice([1.0, 5.0, 10.0, 20.0])),
        ))
    return configs


def bootstrap_ci(y, p, fn, n=2000, seed=SEED) -> list[float]:
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        vals.append(fn(y[idx], p[idx]))
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def metrics(y, p, threshold) -> dict:
    refuse = p >= threshold
    return {
        "auc": round(float(roc_auc_score(y, p)), 4),
        "auc_ci95": bootstrap_ci(y, p, roc_auc_score),
        "ks": round(ks_statistic(y, p), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "log_loss": round(float(log_loss(y, p)), 4),
        "expected_cost": round(expected_cost(y, p, threshold), 4),
        "cost_approve_all": round(expected_cost(y, p, 1.01), 4),
        "cost_refuse_all": round(expected_cost(y, p, -0.01), 4),
        "refusal_rate": round(float(refuse.mean()), 4),
        "confusion": {
            "bad_refused": int(np.sum(refuse & (y == 1))), "bad_approved": int(np.sum(~refuse & (y == 1))),
            "good_refused": int(np.sum(refuse & (y == 0))), "good_approved": int(np.sum(~refuse & (y == 0))),
        },
    }


def train_variant(variant: str, train: pd.DataFrame, test: pd.DataFrame, n_configs: int) -> dict:
    enc = Encoder(variant)
    Xtr, ytr = enc.transform(train), train["default"].to_numpy()
    Xte, yte = enc.transform(test), test["default"].to_numpy()
    splitter = RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=SEED)

    base_oof = oof_baseline(Xtr, ytr, splitter)
    baseline_cv_auc = roc_auc_score(ytr, base_oof)

    rng = np.random.default_rng(SEED)
    best = None
    for overrides in sample_configs(n_configs, rng):
        params = lgbm_params(overrides, enc)
        raw = oof_raw_scores(Xtr, ytr, params, splitter)
        auc = roc_auc_score(ytr, raw)
        if best is None or auc > best["auc"]:
            best = {"auc": auc, "overrides": overrides, "raw": raw}
    params = lgbm_params(best["overrides"], enc)

    # Platt calibration on out-of-fold raw scores.
    cal = LogisticRegression(C=1e6, max_iter=1000).fit(best["raw"].reshape(-1, 1), ytr)
    a, b = float(cal.coef_[0, 0]), float(cal.intercept_[0])
    oof_p = 1 / (1 + np.exp(-(a * best["raw"] + b)))

    # Two operating points, both chosen on out-of-fold calibrated probabilities and
    # smoothed over +/- 0.03 so the choice does not hang on one fold artefact.
    #   balanced      maximises the KS statistic (TPR - FPR), the usual scorecard cut-off
    #   cost_optimal  minimises the expected cost of the dataset's 5:1 cost matrix
    grid = np.round(np.arange(0.05, 0.95, 0.01), 2)
    costs = np.array([expected_cost(ytr, oof_p, t) for t in grid])
    youden = np.array([np.mean(oof_p[ytr == 1] >= t) - np.mean(oof_p[ytr == 0] >= t) for t in grid])
    kernel = np.ones(7) / 7
    thr_cost = float(grid[5:-5][np.argmin(np.convolve(costs, kernel, mode="same")[5:-5])])
    thr_balanced = float(grid[5:-5][np.argmax(np.convolve(youden, kernel, mode="same")[5:-5])])
    threshold = thr_balanced

    final = lgb.LGBMClassifier(**params).fit(Xtr, ytr)
    booster = final.booster_
    test_p = 1 / (1 + np.exp(-(a * booster.predict(Xte, raw_score=True) + b)))
    base_final = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000)).fit(Xtr, ytr)
    base_test_p = base_final.predict_proba(Xte)[:, 1]

    gain = booster.feature_importance(importance_type="gain")
    by_attr: dict[str, float] = {}
    for g, owner in zip(gain, enc.owner):
        by_attr[owner] = by_attr.get(owner, 0.0) + float(g)
    total_gain = sum(by_attr.values()) or 1.0

    version = f"german-credit-{variant}-{date.today().isoformat()}"
    meta = {
        "version": version, "variant": variant, "columns": enc.columns, "features": list(enc.features),
        "calibration": {"method": "platt", "a": round(a, 6), "b": round(b, 6)},
        "threshold": threshold,
        "cost_matrix": {"false_approval": COST_FALSE_APPROVAL, "false_refusal": COST_FALSE_REFUSAL},
        "params": {k: v for k, v in params.items() if k not in ("monotone_constraints", "n_jobs", "verbose")},
        "monotone_increasing": [c for c, m in zip(enc.columns, enc.monotone_constraints()) if m == 1],
        "data": {"train_rows": int(len(train)), "test_rows": int(len(test)), "default_rate": round(float(ytr.mean()), 4)},
        "cv": {
            "scheme": "5-fold stratified, 3 repeats",
            "lightgbm_auc": round(float(best["auc"]), 4),
            "baseline_logreg_auc": round(float(baseline_cv_auc), 4),
            "calibrated_brier": round(float(brier_score_loss(ytr, oof_p)), 4),
            "configs_tried": n_configs,
        },
        "policies": {
            "balanced": {"threshold": thr_balanced, "rule": "maximum KS on out-of-fold predictions",
                         **metrics(yte, test_p, thr_balanced)},
            "cost_optimal": {"threshold": thr_cost, "rule": "minimum expected cost, 5:1 cost matrix",
                             **metrics(yte, test_p, thr_cost)},
        },
        "test": metrics(yte, test_p, threshold),
        "test_baseline_logreg": {"auc": round(float(roc_auc_score(yte, base_test_p)), 4),
                                 "ks": round(ks_statistic(yte, base_test_p), 4),
                                 "brier": round(float(brier_score_loss(yte, base_test_p)), 4)},
        "importance_gain": {k: round(v / total_gain, 4) for k, v in sorted(by_attr.items(), key=lambda kv: -kv[1])},
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(MODEL_DIR / f"model_{variant}.txt"))
    (MODEL_DIR / f"model_{variant}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    curves = {"grid": grid.tolist(), "cost": costs.tolist(), "youden": youden.tolist(), "oof_p": oof_p.tolist(), "y_train": ytr.tolist(),
              "test_p": test_p.tolist(), "y_test": yte.tolist(), "base_test_p": base_test_p.tolist()}
    return {"meta": meta, "curves": curves}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    args = ap.parse_args()
    train = pd.read_csv(DATA / "train.csv")
    test = pd.read_csv(DATA / "test.csv")
    results = {}
    for variant in ("full", "unaware"):
        results[variant] = train_variant(variant, train, test, n_configs=8 if args.fast else 40)
        m = results[variant]["meta"]
        print(f"[{variant}] cv auc lgbm {m['cv']['lightgbm_auc']} / logreg {m['cv']['baseline_logreg_auc']} | "
              f"test auc {m['test']['auc']} {m['test']['auc_ci95']} ks {m['test']['ks']} brier {m['test']['brier']} | "
              f"threshold {m['threshold']} refusal {m['test']['refusal_rate']} cost {m['test']['expected_cost']}")
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "curves.json").write_text(json.dumps({k: v["curves"] for k, v in results.items()}), encoding="utf-8")
    print("models written to", MODEL_DIR)


if __name__ == "__main__":
    main()
