"""Model report (task M2): figures, model card and the summary read by the interface.

    python ml/report.py

Runs after ml/train.py. Besides the usual model metrics, it replays the whole
agent graph on the test set to measure what the audit delivers: how many
refusals get a verified path to approval, at which attempt, and how often
the decision depends on a sensitive attribute, for both model variants.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_curve  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.domain.features import BY_NAME  # noqa: E402
from app.domain.model import MODEL_DIR, get_model  # noqa: E402
from app.graph.build import graph  # noqa: E402
from app.schemas import LoanApplication  # noqa: E402
from app.tools.fairness import group_fairness_comparison  # noqa: E402

REPORTS = ROOT / "ml" / "reports"
INK, ACCENT, MUTED = "#1d1d1f", "#0071e3", "#8e8e93"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c7c7cc", "figure.dpi": 150, "savefig.bbox": "tight"})


def downsample(x, y, n=60):
    idx = np.unique(np.linspace(0, len(x) - 1, n).astype(int))
    return [[round(float(x[i]), 4), round(float(y[i]), 4)] for i in idx]


def audit_test_set(variant: str, test: pd.DataFrame) -> dict:
    config.MODEL_VARIANT = variant
    stats: Counter = Counter()
    paths, immediate = [], 0
    started = time.perf_counter()
    for rec in test.drop(columns=["default"]).to_dict("records"):
        out = graph.invoke({"application": LoanApplication(**rec)})
        d = out["decision"]
        stats["files"] += 1
        stats[d.decision] += 1
        if not out["fairness"].flip_test_passed:
            stats["flip_test_failed"] += 1
        if d.escalated:
            stats["escalated"] += 1
        if d.decision == "refused":
            if d.counterfactuals:
                stats[f"solved_attempt_{d.attempts}"] += 1
                paths.append(len(d.counterfactuals))
                immediate += any(c.effort == "immediate" for c in d.counterfactuals)
            else:
                stats["no_path"] += 1
    refused = max(stats["refused"], 1)
    return {
        **{k: int(v) for k, v in stats.items()},
        "recourse_rate": round(1 - stats["no_path"] / refused, 4),
        "immediate_recourse_rate": round(immediate / refused, 4),
        "mean_paths": round(float(np.mean(paths)), 2) if paths else 0.0,
        "flip_test_failure_rate": round(stats["flip_test_failed"] / stats["files"], 4),
        "ms_per_audit": round((time.perf_counter() - started) / stats["files"] * 1000, 1),
    }


def main() -> None:
    curves = json.loads((REPORTS / "curves.json").read_text(encoding="utf-8"))
    metas = {v: json.loads((MODEL_DIR / f"model_{v}.json").read_text(encoding="utf-8")) for v in ("full", "unaware")}
    test = pd.read_csv(ROOT / "ml" / "data" / "processed" / "test.csv")
    c = curves["full"]
    y, p, base = np.array(c["y_test"]), np.array(c["test_p"]), np.array(c["base_test_p"])
    meta = metas["full"]
    thr = meta["threshold"]

    # --- curves
    fpr, tpr, _ = roc_curve(y, p)
    bfpr, btpr, _ = roc_curve(y, base)
    bins = np.linspace(0, 1, 9)
    which = np.clip(np.digitize(p, bins) - 1, 0, len(bins) - 2)
    calibration = [{"predicted": round(float(p[which == b].mean()), 4), "observed": round(float(y[which == b].mean()), 4),
                    "count": int((which == b).sum())} for b in range(len(bins) - 1) if (which == b).sum() >= 5]
    edges = np.linspace(0, 1, 21)
    hist = {"edges": [round(float(e), 2) for e in edges],
            "repaid": np.histogram(p[y == 0], edges)[0].tolist(), "defaulted": np.histogram(p[y == 1], edges)[0].tolist()}

    # --- global SHAP importance on the test set
    model = get_model("full")
    rows = test.drop(columns=["default", "applicant_id"]).to_dict("records")
    totals: dict[str, float] = {}
    for row in rows:
        contrib, _ = model.contributions(row)
        for k, v in contrib.items():
            totals[k] = totals.get(k, 0.0) + abs(v)
    shap_importance = [{"feature": k, "label": BY_NAME[k].label, "value": round(v / len(rows), 4)}
                       for k, v in sorted(totals.items(), key=lambda kv: -kv[1])]

    # --- what the audit delivers, for both variants
    audit = {v: audit_test_set(v, test) for v in ("full", "unaware")}
    config.MODEL_VARIANT = "full"
    fairness = group_fairness_comparison()  # Fairlearn group metrics of both variants (task I1)

    summary = {
        "roc": downsample(fpr, tpr), "roc_baseline": downsample(bfpr, btpr),
        "calibration": calibration, "histogram": hist,
        "cost_curve": [[g, round(v, 4)] for g, v in zip(c["grid"], c["cost"])],
        "ks_curve": [[g, round(v, 4)] for g, v in zip(c["grid"], c["youden"])],
        "shap_importance": shap_importance, "audit": audit, "fairness": fairness,
    }
    (REPORTS / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")

    # --- figures for the written report
    fig, ax = plt.subplots(figsize=(4.6, 4))
    ax.plot(fpr, tpr, color=ACCENT, lw=2, label=f"LightGBM (AUC {meta['test']['auc']:.3f})")
    ax.plot(bfpr, btpr, color=MUTED, lw=1.5, label=f"Logistic regression (AUC {meta['test_baseline_logreg']['auc']:.3f})")
    ax.plot([0, 1], [0, 1], color="#c7c7cc", lw=1, ls="--")
    ax.set(xlabel="False positive rate", ylabel="True positive rate", title="ROC curve, test set")
    ax.legend(frameon=False, loc="lower right")
    fig.savefig(REPORTS / "roc.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(4.6, 4))
    ax.plot([0, 1], [0, 1], color="#c7c7cc", lw=1, ls="--")
    ax.plot([b["predicted"] for b in calibration], [b["observed"] for b in calibration], "o-", color=ACCENT, lw=2)
    ax.set(xlabel="Predicted default probability", ylabel="Observed default rate", title="Calibration, test set",
           xlim=(0, 1), ylim=(0, 1))
    fig.savefig(REPORTS / "calibration.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    ax.plot(c["grid"], c["cost"], color=INK, lw=2)
    for name, pol in meta["policies"].items():
        ax.axvline(pol["threshold"], color=ACCENT if name == "balanced" else MUTED, ls="--", lw=1.2,
                   label=f"{name.replace('_', ' ')} ({pol['threshold']:.2f})")
    ax.set(xlabel="Refusal threshold", ylabel="Expected cost per applicant (5:1 matrix)",
           title="Cost of the decision policy, out-of-fold")
    ax.legend(frameon=False)
    fig.savefig(REPORTS / "cost_curve.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    top = shap_importance[:12][::-1]
    ax.barh([t["label"] if len(t["label"]) < 34 else t["label"][:32] + "..." for t in top], [t["value"] for t in top], color=ACCENT)
    ax.set(xlabel="Mean absolute SHAP value (log-odds)", title="Global attribute importance, test set")
    fig.savefig(REPORTS / "shap_importance.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    w = edges[1] - edges[0]
    ax.bar(edges[:-1] + w / 2, hist["repaid"], width=w * 0.9, color="#c7c7cc", label="Repaid")
    ax.bar(edges[:-1] + w / 2, hist["defaulted"], width=w * 0.9, bottom=hist["repaid"], color=INK, label="Defaulted")
    ax.axvline(thr, color=ACCENT, ls="--", lw=1.5, label=f"Threshold {thr:.2f}")
    ax.set(xlabel="Predicted default probability", ylabel="Applicants", title="Score distribution, test set")
    ax.legend(frameon=False)
    fig.savefig(REPORTS / "score_distribution.png"); plt.close(fig)

    # --- model card
    t, cv, a = meta["test"], meta["cv"], audit
    lines = [
        "# Model card: German Credit default model", "",
        f"Version `{meta['version']}`. Generated by `ml/train.py` and `ml/report.py`.", "",
        "## Purpose", "",
        "Probability that a loan applicant defaults. The model is the object of the audit: the agents score a file",
        "with it, explain the score with exact SHAP values, search for counterfactuals against it and test whether",
        "its decision depends on protected attributes.", "",
        "## Data", "",
        "Statlog German Credit (UCI Machine Learning Repository, CC BY 4.0): 1,000 applicants, 20 attributes,",
        f"30% defaults. Stratified split: {meta['data']['train_rows']} training files, {meta['data']['test_rows']} test files (seed 42).",
        "The personal status code is reduced to `sex`, because marital status and sex are confounded in the original coding.", "",
        "## Model", "",
        "LightGBM on one-hot encoded attributes, with monotone constraints: predicted risk never decreases when the",
        "duration, the amount or the instalment rate increases. Hyperparameters chosen by random search",
        f"({cv['configs_tried']} configurations) on {cv['scheme']}. Probabilities calibrated by Platt scaling on out-of-fold scores.", "",
        "| | Cross-validation AUC | Test AUC | Test KS | Test Brier |", "|---|---|---|---|---|",
        f"| LightGBM (retained) | {cv['lightgbm_auc']:.3f} | {t['auc']:.3f} (95% CI {t['auc_ci95'][0]:.3f} to {t['auc_ci95'][1]:.3f}) | {t['ks']:.3f} | {t['brier']:.3f} |",
        f"| Logistic regression | {cv['baseline_logreg_auc']:.3f} | {meta['test_baseline_logreg']['auc']:.3f} | {meta['test_baseline_logreg']['ks']:.3f} | {meta['test_baseline_logreg']['brier']:.3f} |", "",
        "The test set holds 200 files, so the confidence interval is wide. Figures: `roc.png`, `calibration.png`,",
        "`score_distribution.png`, `shap_importance.png`.", "",
        "## Decision policy", "",
        "| Policy | Rule | Threshold | Refusal rate | Bad payers approved | Good payers refused | Expected cost (5:1) |", "|---|---|---|---|---|---|---|",
    ]
    for name, pol in meta["policies"].items():
        cf = pol["confusion"]
        lines.append(f"| {name.replace('_', ' ')}{' (default)' if pol['threshold'] == thr else ''} | {pol['rule']} | {pol['threshold']:.2f} | "
                     f"{pol['refusal_rate']:.0%} | {cf['bad_approved']} of {cf['bad_approved'] + cf['bad_refused']} | "
                     f"{cf['good_refused']} of {cf['good_refused'] + cf['good_approved']} | {pol['expected_cost']:.3f} |")
    lines += [
        "", f"Approving everyone costs {t['cost_approve_all']:.2f} per applicant and refusing everyone {t['cost_refuse_all']:.2f}.",
        "The balanced threshold is the default operating point: it refuses about half of the files instead of",
        "about seven in ten, and on the test set its expected cost is not higher than the cost-optimal threshold's.",
        "The other policy is available with `REFUSAL_THRESHOLD`.", "",
        "## What the audit delivers (test set, 200 files, agents on rules)", "",
        "| | Full model (audited) | Unaware model |", "|---|---|---|",
        f"| Refusals | {a['full']['refused']} | {a['unaware']['refused']} |",
        f"| Refusals with a verified path to approval | {a['full']['recourse_rate']:.0%} | {a['unaware']['recourse_rate']:.0%} |",
        f"| of which solved at attempt 1 / 2 / 3 | {a['full'].get('solved_attempt_1', 0)} / {a['full'].get('solved_attempt_2', 0)} / {a['full'].get('solved_attempt_3', 0)} | {a['unaware'].get('solved_attempt_1', 0)} / {a['unaware'].get('solved_attempt_2', 0)} / {a['unaware'].get('solved_attempt_3', 0)} |",
        f"| Refusals with an immediate path (loan terms only) | {a['full']['immediate_recourse_rate']:.0%} | {a['unaware']['immediate_recourse_rate']:.0%} |",
        f"| Files whose decision changes with a protected attribute | {a['full']['flip_test_failure_rate']:.1%} | {a['unaware']['flip_test_failure_rate']:.1%} |",
        f"| Files sent to human review | {a['full'].get('escalated', 0)} | {a['unaware'].get('escalated', 0)} |",
        f"| Time per audit | {a['full']['ms_per_audit']:.0f} ms | {a['unaware']['ms_per_audit']:.0f} ms |", "",
        "A way to approval is counted only when it passes every check of the Vérificateur-Équité: recourse rules,",
        "re-scoring with a safety margin, and realism against past applicants (plausibility).", "",
        "The full model uses sex, age and foreign-worker status, as a legacy scorecard would. The audit detects the",
        "files where one of these attributes decides the outcome. The unaware variant removes them at a negligible",
        f"cost in accuracy (test AUC {metas['unaware']['test']['auc']:.3f}).", "",
        "## Fairness across groups (test set, Fairlearn)", "",
        "Approval rate of each group, demographic parity difference (largest gap in approval rate between two groups),",
        "demographic parity ratio (lowest rate divided by the highest; the four-fifths rule asks for at least 0.80) and",
        "equalized odds difference (largest gap between groups in the approval rate of good payers or of bad payers).",
        "Intervals are 95% bootstrap intervals on the 200 test files.", "",
        "| Attribute | Model | Approval rate by group | DP difference | DP ratio | EO difference |", "|---|---|---|---|---|---|",
    ]
    for attribute in fairness["full"]["attributes"]:
        for variant, name in (("full", "Full (audited)"), ("unaware", "Unaware")):
            r = fairness[variant]["attributes"][attribute]
            groups = ", ".join(f"{g.replace('_', ' ')} {v['selection_rate']:.0%} (n={v['n']})" for g, v in r["groups"].items())
            dp, eo = r["ci95"]["demographic_parity_difference"], r["ci95"]["equalized_odds_difference"]
            lines.append(f"| {r['label']} | {name} | {groups} | {r['demographic_parity_difference']:.3f} ({dp[0]:.2f} to {dp[1]:.2f}) | "
                         f"{r['demographic_parity_ratio']:.2f} | {r['equalized_odds_difference']:.3f} ({eo[0]:.2f} to {eo[1]:.2f}) |")
    lines += [
        "", *[f"- {line}" for line in fairness["reading"]], "",
        f"A gap above {fairness['tolerance']:.0%} between groups of at least {fairness['min_group']} files is reported as a disparity.",
        "The unaware model never sees the protected attributes: what it still shows reaches the decision through",
        "correlated attributes. These metrics describe the model on a small test set; the audit of one file relies on",
        "the individual flip test, and records the group metrics for the reviewer.", "",
        "## Limits", "",
        "- 1,000 files from one German bank in the 1990s, amounts in Deutsche Mark: a benchmark, not a production portfolio.",
        "- Only accepted applicants are in the data (no reject inference).",
        "- Counterfactuals describe what the model would decide, not a causal guarantee of repayment.",
    ]
    (REPORTS / "MODEL_CARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=1))


if __name__ == "__main__":
    main()
