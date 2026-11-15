"""Arbitre et Rédacteur. Owner: Imane (task I2).

Finalises the audit or escalates it to a human reviewer, then writes the
applicant summary and the audit report.

PLACEHOLDER logic: three escalation rules and a template summary.
TODO: LangGraph interrupt for the human review step, LLM-written letter,
PDF report through tools/report.py.
"""
from app import config
from app.agents.base import plural
from app.graph.state import AuditState
from app.memory import case_store
from app.schemas import AuditDecision


def run(state: AuditState) -> AuditState:
    app, score, fairness = state["application"], state["score"], state["fairness"]
    cfs = state.get("counterfactuals", [])
    p = score.default_probability

    reason = None
    if not fairness.flip_test_passed:
        reason = "the decision depends on a sensitive attribute"
    elif abs(p - score.threshold) <= config.BORDERLINE_MARGIN:
        reason = "the score falls within the borderline band around the threshold"
    elif score.decision == "refused" and not cfs:
        reason = f"no verified way to approval was found after {plural(state.get('attempts', 0), 'attempt')}"

    if score.decision == "approved":
        summary = f"Application approved: default risk {p:.0%}, below the {score.threshold:.0%} threshold."
    elif cfs:
        best = min(cfs, key=lambda c: c.cost)
        summary = (f"Application refused: default risk {p:.0%}, threshold {score.threshold:.0%}. "
                   f"Easiest verified way to approval: {best.statement[:1].lower() + best.statement[1:]}")
    else:
        summary = f"Application refused: default risk {p:.0%}, threshold {score.threshold:.0%}. No verified way to approval."

    decision = AuditDecision(
        applicant_id=app.applicant_id, decision=score.decision, default_probability=p,
        escalated=reason is not None, escalation_reason=reason, summary=summary,
        counterfactuals=cfs, fairness=fairness, attempts=state.get("attempts", 0),
    )
    case_store.add(app, decision)
    log = f"Sent to human review: {reason}." if reason else "Audit closed without escalation."
    return {"decision": decision, "log": log, "reasoning": summary, "mode": "rules", "tool_calls": [],
            "status": "escalated" if reason else "finished"}
