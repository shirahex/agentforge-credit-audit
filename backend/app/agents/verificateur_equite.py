"""Vérificateur-Équité. Owner: Imane (task I2).

Audits the decision and the counterfactuals. A rejection sends the file
back to the Générateur-Contrefactuels (see graph/build.py).
TODO: group metrics from Fairlearn, plausibility score, LLM-written reasons.
"""
from app.graph.state import AuditState
from app.schemas import FairnessVerdict
from app.tools.fairness import group_fairness_metrics, sensitive_flip_test


def run(state: AuditState) -> AuditState:
    flip_ok, metrics = sensitive_flip_test(state["application"])
    metrics.update(group_fairness_metrics())
    reasons: list[str] = []
    if not flip_ok:
        reasons.append("decision changes when only a sensitive attribute changes")

    cfs = state.get("counterfactuals", [])
    kept = [c for c in cfs if c.valid and c.actionable]
    for c in cfs:
        if not c.actionable:
            reasons.append(f"counterfactual rejected: {c.rejection_reason}")
        elif not c.valid:
            reasons.append("counterfactual rejected: decision does not flip after re-scoring")

    refused = state["score"].decision == "refused"
    passed = flip_ok and (not refused or len(kept) > 0)
    verdict = FairnessVerdict(passed=passed, reasons=reasons, metrics=metrics, flip_test_passed=flip_ok)
    if passed:
        log = f"Audit passed. {len(kept)} counterfactual(s) kept."
    else:
        log = "Audit failed: " + "; ".join(reasons)
    return {
        "fairness": verdict,
        "counterfactuals": kept,
        "log": log,
        "status": "completed" if passed else "rejected",
    }
