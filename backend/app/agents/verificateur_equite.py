"""Vérificateur-Équité. Owner: Imane (task I2).

Audits the decision and the counterfactuals. A rejection sends the file
back to the Générateur-Contrefactuels with the reasons (see graph/build.py).

PLACEHOLDER logic: flip test on sensitive attributes, and a filter keeping
the counterfactuals that are valid, actionable and robust.
TODO: group metrics from Fairlearn, plausibility score, LLM-written verdict.
"""
from collections import Counter

from app.agents.base import Recorder, plural
from app.graph.state import AuditState
from app.schemas import FairnessVerdict
from app.tools.fairness import group_fairness_metrics, sensitive_flip_test


def run(state: AuditState) -> AuditState:
    rec = Recorder()
    flip_ok, metrics = rec.call(
        "sensitive_flip_test", sensitive_flip_test, state["application"], show={"attributes": ["sex", "foreign_worker"]},
        summary=lambda r: "decision unchanged" if r[0] else "decision changes with a sensitive attribute")
    metrics.update(group_fairness_metrics())
    reasons: list[str] = []
    if not flip_ok:
        reasons.append("the decision changes when only a sensitive attribute changes")

    cfs = state.get("counterfactuals", [])
    kept = [c for c in cfs if c.valid and c.actionable and c.robust]
    objections: Counter[str] = Counter()
    for c in cfs:
        if not c.actionable:
            objections[c.rejection_reason or "not actionable"] += 1
        elif not c.valid:
            objections[f"every permitted change together only reaches {c.new_probability:.0%}, above the threshold"] += 1
        elif not c.robust:
            objections["flips the decision without a safety margin"] += 1
    reasons += [why if why.startswith("every permitted") else f"{plural(n, 'candidate')} rejected ({why})"
                for why, n in objections.items()]

    refused = state["score"].decision == "refused"
    passed = flip_ok and (not refused or len(kept) > 0)
    verdict = FairnessVerdict(passed=passed, reasons=reasons, metrics=metrics, flip_test_passed=flip_ok)
    if not refused:
        log = "Approval audited: sensitive attributes do not change the decision." if flip_ok else \
            "Approval audited: " + reasons[0] + "."
    elif kept:
        dropped = len(cfs) - len(kept)
        log = f"{plural(len(kept), 'way')} to approval verified" + (f", {plural(dropped, 'candidate')} rejected." if dropped else ".")
    else:
        log = "Nothing survives the audit: " + "; ".join(reasons[:3]) + "."
    return {"fairness": verdict, "counterfactuals": kept, "log": log,
            "reasoning": " ".join(r[:1].upper() + r[1:] + "." for r in reasons) or "No objection.",
            "mode": "rules", "tool_calls": rec.calls, "status": "completed" if passed else "rejected"}
