"""Générateur-Contrefactuels. Owner: Marouane (task M4).

Proposes minimal changes that would flip a refusal and re-scores each one.
TODO: LLM selection among DiCE candidates, using the verifier's rejection
reasons from the previous attempt.
"""
from app.graph.state import AuditState
from app.tools.counterfactuals import generate_counterfactuals


def run(state: AuditState) -> AuditState:
    attempt = state.get("attempts", 0) + 1
    cfs = generate_counterfactuals(state["application"], attempt)
    return {
        "counterfactuals": cfs,
        "attempts": attempt,
        "log": f"Attempt {attempt}: {len(cfs)} counterfactual(s) proposed and re-scored.",
        "status": "completed",
    }
