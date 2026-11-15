"""Analyste-Dossier. Owner: Marouane (task M4).

Validates the applicant file and flags missing or implausible values.
TODO: LLM-written remarks, retrieval of similar past files from the case store.
"""
from app.graph.state import AuditState


def run(state: AuditState) -> AuditState:
    app = state["application"]
    warnings: list[str] = []
    if app.credit_amount / app.duration_months > 2000:
        warnings.append("monthly instalment unusually high for the stated duration")
    if app.employment_years > app.age - 16:
        warnings.append("employment length inconsistent with age")
    note = f"{len(warnings)} warning(s)" if warnings else "file consistent"
    return {"warnings": warnings, "log": f"File {app.applicant_id} checked: {note}.", "status": "completed"}
