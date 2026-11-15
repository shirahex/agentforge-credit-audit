"""Chooses the demo applicant files (task M1).

Runs the agent graph on every test-set applicant and keeps one real file
for each path of the graph, so the demonstration never relies on invented
data.

    python ml/select_samples.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.graph.build import graph  # noqa: E402
from app.schemas import LoanApplication  # noqa: E402

OUT = ROOT / "backend" / "app" / "samples.json"

WANTED = [
    ("terms", "Refused, solved by loan terms",
     "A refusal that a smaller amount or a shorter duration turns into an approval on the first attempt.",
     lambda r: r["dec"] == "refused" and r["att"] == 1 and not r["esc"] and r["n"] >= 2 and r["warn"] == 0),
    ("second_attempt", "Refused, needs a second attempt",
     "Loan terms alone are not enough: the first attempt is rejected and the search widens to the financial situation.",
     lambda r: r["dec"] == "refused" and r["att"] == 2 and not r["esc"] and r["n"] >= 2),
    ("approved", "Approved",
     "A solid file: approved, then audited for fairness.",
     lambda r: r["dec"] == "approved" and not r["esc"] and r["p"] < 0.12 and r["warn"] == 0),
    ("borderline", "Borderline score",
     "The score falls within the band around the threshold: the file goes to a human reviewer.",
     lambda r: bool(r["esc"]) and "borderline" in r["esc"]),
    ("sensitive", "Decision depends on a sensitive attribute",
     "Changing only a protected attribute changes the decision: the fairness audit fails and a human decides.",
     lambda r: bool(r["esc"]) and "sensitive" in r["esc"] and r["dec"] == "refused"),
    ("no_path", "Refused, no way to approval",
     "Three attempts, no realistic change flips the decision: escalated with the closest result reached.",
     lambda r: bool(r["esc"]) and "no verified way" in r["esc"]),
]


def main() -> None:
    test = pd.read_csv(ROOT / "ml" / "data" / "processed" / "test.csv")
    rows = []
    for rec in test.to_dict("records"):
        rec.pop("default")
        app = LoanApplication(**rec)
        out = graph.invoke({"application": app})
        d = out["decision"]
        rows.append({"app": app, "dec": d.decision, "att": d.attempts, "esc": d.escalation_reason or "",
                     "n": len(d.counterfactuals), "warn": len(out["warnings"]), "p": d.default_probability})
    samples = []
    for tag, title, description, rule in WANTED:
        matches = [r for r in rows if rule(r)]
        if not matches:
            print("no match for", tag)
            continue
        # A mid-sized request reads better in a demonstration than an extreme one.
        pick = sorted(matches, key=lambda r: abs(r["app"].credit_amount - 3500))[0]
        samples.append({"tag": tag, "title": title, "description": description,
                        "application": pick["app"].model_dump(mode="json")})
        print(f"{tag:15s} {pick['app'].applicant_id}  p={pick['p']:.3f}  attempts={pick['att']}  paths={pick['n']}  ({len(matches)} candidates)")
    OUT.write_text(json.dumps(samples, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
