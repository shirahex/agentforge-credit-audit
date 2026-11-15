"""Figures of the evaluation (shared task S3), drawn from the tables of eval/results/.

    python eval/run_eval.py      # writes the tables
    python eval/figures.py       # writes eval/results/figures/*.png

Same style as the model figures of ml/report.py. Green, red and amber keep
the meaning they have in the interface.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
OUT = RESULTS / "figures"
INK, SOFT, ACCENT, MUTED, FAINT = "#1d1d1f", "#424245", "#0071e3", "#8e8e93", "#c7c7cc"
POSITIVE, NEGATIVE = "#1f8a4c", "#c9342b"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": FAINT, "figure.dpi": 150, "savefig.bbox": "tight"})
NAMES = {"full": "Five agents\nwith the loop", "no_loop": "Without the\nrejection loop",
         "no_verifier": "Without the\nauditor agent", "single_pass": "Model + DiCE,\nno agents",
         "single_prompt": "One prompt,\nno tools"}


def read(name: str) -> list[dict]:
    with (RESULTS / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def systems() -> None:
    rows = read("systems.csv")
    labels = [NAMES[r["system"]] for r in rows]
    sound = [float(r["refusals_with_sound_way"]) * 100 for r in rows]
    unsound = [float(r["refusals_given_unsound_proposal"]) * 100 for r in rows]
    x = range(len(rows))
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    a = ax.bar([i - 0.2 for i in x], sound, width=0.38, color=POSITIVE, label="leave with a way to approval that passes every check")
    b = ax.bar([i + 0.2 for i in x], unsound, width=0.38, color=NEGATIVE, label="are handed a proposal that fails a check")
    for bars in (a, b):
        ax.bar_label(bars, fmt="%.0f%%", padding=2, fontsize=9, color=INK)
    ax.set(ylabel="Share of the refused files", ylim=(0, 112), title="What a refused applicant receives")
    ax.set_xticks(list(x), labels)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=1)
    fig.savefig(OUT / "systems.png")
    plt.close(fig)


def attempts() -> None:
    rows = read("attempts.csv")
    parts = [("solved_at_attempt_1", "Solved at attempt 1", INK), ("solved_at_attempt_2", "Attempt 2", SOFT),
             ("solved_at_attempt_3", "Attempt 3", MUTED), ("no_way_to_approval", "No way to approval", NEGATIVE)]
    fig, ax = plt.subplots(figsize=(7.2, 2.4))
    labels = [NAMES[r["system"]].replace("\n", " ") for r in rows]
    left = [0] * len(rows)
    for key, label, colour in parts:
        values = [int(r[key]) for r in rows]
        bars = ax.barh(labels, values, left=left, color=colour, label=label, height=0.55)
        ax.bar_label(bars, labels=[str(v) if v else "" for v in values], label_type="center", color="white", fontsize=9)
        left = [a + b for a, b in zip(left, values)]
    ax.invert_yaxis()
    ax.set(xlabel="Refused files", title="Where the rejection loop pays")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.35), ncol=4)
    fig.savefig(OUT / "attempts.png")
    plt.close(fig)


def fairness() -> None:
    rows = [r for r in read("fairness.csv") if r["row"] == "group" and r["attribute"] in ("sex", "age_group")]
    groups = list(dict.fromkeys((r["attribute"], r["group"]) for r in rows))
    rate = {(r["model"], r["attribute"], r["group"]): float(r["selection_rate"]) * 100 for r in rows}
    labels = [g for _, g in groups]
    x = range(len(groups))
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    a = ax.bar([i - 0.2 for i in x], [rate[("full", *g)] for g in groups], width=0.38, color=INK, label="Audited model")
    b = ax.bar([i + 0.2 for i in x], [rate[("unaware", *g)] for g in groups], width=0.38, color=ACCENT,
               label="Model without protected attributes")
    for bars in (a, b):
        ax.bar_label(bars, fmt="%.0f%%", padding=2, fontsize=9)
    ax.axvline(1.5, color=FAINT, lw=1)
    ax.set_xticks(list(x), labels)
    ax.set(ylabel="Files approved", ylim=(0, 70), title="Approval rate by group, 200 test files")
    ax.text(0.5, 66, "Sex", ha="center", color=MUTED)
    ax.text(3, 66, "Age band", ha="center", color=MUTED)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    fig.savefig(OUT / "fairness.png")
    plt.close(fig)


def generators() -> None:
    rows = {r["generator"]: r for r in read("counterfactuals.csv")}
    metrics = [("validity", "Valid"), ("actionability_rate", "Actionable"), ("robust", "Robust"),
               ("plausible", "Plausible"), ("sound", "Sound"), ("coverage_sound", "Refusals\ncovered")]
    x = range(len(metrics))
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    a = ax.bar([i - 0.2 for i in x], [float(rows["exhaustive"][k]) * 100 for k, _ in metrics], width=0.38, color=INK,
               label="Exhaustive search")
    b = ax.bar([i + 0.2 for i in x], [float(rows["dice"][k]) * 100 for k, _ in metrics], width=0.38, color=ACCENT, label="DiCE")
    for bars in (a, b):
        ax.bar_label(bars, fmt="%.0f%%", padding=2, fontsize=9)
    ax.set_xticks(list(x), [label for _, label in metrics])
    ax.set(ylabel="Share of candidates (last column: of refusals)", ylim=(0, 115),
           title="Counterfactual generators, judged by the same tools")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
    fig.savefig(OUT / "generators.png")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for draw in (systems, attempts, fairness, generators):
        draw()
        print("written", (OUT / f"{draw.__name__}.png").relative_to(RESULTS.parent.parent))


if __name__ == "__main__":
    main()
