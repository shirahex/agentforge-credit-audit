"""Modèle-Scoring. Owner: Marouane (task M4).

Calls the scoring and explanation tools. Numbers always come from tools.
TODO: LLM explanation of the top factors in plain language, checked against SHAP.
"""
from app.graph.state import AuditState
from app.tools.scoring import score_applicant


def run(state: AuditState) -> AuditState:
    score = score_applicant(state["application"])
    main = score.top_factors[0].feature if score.top_factors else "n/a"
    return {
        "score": score,
        "log": f"Default probability {score.default_probability:.2f}, decision {score.decision}. Main factor: {main}.",
        "status": "completed",
    }
