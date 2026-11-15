"""Arbitre et Rédacteur. Owner: Imane (task I2).

Finalises the audit or escalates it to a human reviewer, then writes the
applicant summary and the audit report.
TODO: LangGraph interrupt for the human review step, LLM-written summary,
PDF report through tools/report.py, storage in the case store.
"""
from app import config
from app.graph.state import AuditState
from app.memory import case_store
from app.schemas import AuditDecision


def run(state: AuditState) -> AuditState:
    app, score, fairness = state["application"], state["score"], state["fairness"]
    cfs = state.get("counterfactuals", [])
    p = score.default_probability

    reason = None
    if abs(p - config.REFUSAL_THRESHOLD) <= config.BORDERLINE_MARGIN:
        reason = "score within the borderline band"
    elif not fairness.flip_test_passed:
        reason = "sensitive attribute flip test failed"
    elif score.decision == "refused" and not cfs:
        reason = "no valid and actionable counterfactual found"

    if score.decision == "approved":
        summary = "Application approved."
    elif cfs:
        best = min(cfs, key=lambda c: len(c.changes))
        steps = ", ".join(f"{c.feature} from {c.from_value} to {c.to_value}" for c in best.changes)
        summary = f"Application refused. Smallest verified path to approval: {steps}."
    else:
        summary = "Application refused. No verified path to approval."

    decision = AuditDecision(
        applicant_id=app.applicant_id,
        decision=score.decision,
        default_probability=p,
        escalated=reason is not None,
        escalation_reason=reason,
        summary=summary,
        counterfactuals=cfs,
        fairness=fairness,
        attempts=state.get("attempts", 0),
    )
    case_store.add(app, decision)
    log = f"Escalated to human review: {reason}." if reason else f"Audit finalised. {summary}"
    return {"decision": decision, "log": log, "status": "escalated" if reason else "finished"}
