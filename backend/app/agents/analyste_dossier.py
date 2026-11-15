"""Analyste-Dossier (task M4).

Checks the applicant file before any scoring: consistency rules, position
against past files, and the outcome actually observed for the most similar
past applicants. The LLM writes the analyst note from these tool outputs;
the note is rejected if it quotes a number the tools did not produce.

Memory (task I3): the agent also asks the case store for similar files that
this system already audited, and cites the closest one in its note.
"""
from pydantic import BaseModel, Field

from app.agents.base import Recorder, guarded_answer, plural, similarity_percent
from app.graph.state import AuditState
from app.memory import case_store
from app.schemas import AnalystReport, PastAudit
from app.tools.analysis import similar_cases, validate_application

SYSTEM = """You are the file analyst of a credit audit team. You receive facts produced by tools about one
loan application: consistency warnings, the outcome of the most similar past applicants and, when there is
one, the closest file already audited by this team ("previous_audit").
Write a short analyst note (at most 55 words, plain English, no bullet points) that states whether the
file is consistent and what the similar past files suggest; mention the previous audit when one is given.
Use only the facts given. Never give a
credit decision or a probability of your own. Never mention sex, age or nationality.
Answer with a JSON object: {"note": "..."}"""


class Note(BaseModel):
    note: str = Field(min_length=20, max_length=600)


def cite(p: PastAudit) -> str:
    """One sentence on the closest file already audited."""
    outcome = f"{p.final_outcome} after human review" if p.reviewed else p.final_outcome
    if p.final_outcome == "refused" and p.paths and not p.reviewed:
        outcome += f", with {plural(p.paths, 'verified way')} to approval"
    return f"A similar file was audited before ({p.applicant_id}, {similarity_percent(p.similarity)}% similar): {outcome}."


def run(state: AuditState) -> AuditState:
    app = state["application"]
    rec = Recorder()
    warnings = rec.call("validate_application", validate_application, app,
                        show={"applicant": app.applicant_id},
                        summary=lambda w: plural(len(w), "warning"))
    rate, peers = rec.call("similar_cases", similar_cases, app, 15, show={"k": 15},
                           summary=lambda r: f"{round(r[0] * 15)} of 15 similar past applicants defaulted")
    precedents = rec.call("past_audits", case_store.search, app, 3, exclude_run=state.get("run_id"),
                          show={"k": 3, "min_similarity": case_store.MIN_SIMILARITY},
                          summary=lambda r: ("no similar file audited before" if not r else "; ".join(
                              f"{p.applicant_id} {p.final_outcome} ({similarity_percent(p.similarity)}% similar)" for p in r)))
    defaults = round(rate * 15)
    facts = {"warnings": warnings, "similar_past_applicants": 15, "of_which_defaulted": defaults,
             "credit_amount": app.credit_amount, "duration_months": app.duration_months}
    if precedents:
        first = precedents[0]
        facts["previous_audit"] = {"applicant": first.applicant_id, "similarity_percent": similarity_percent(first.similarity),
                                   "outcome": first.final_outcome, "decided_by_a_person": first.reviewed,
                                   "verified_ways_to_approval": first.paths}
    answer = guarded_answer(SYSTEM, facts, Note, text_fields=("note",))
    if answer:
        note, mode = answer.note, "llm"
    else:
        state_of_file = ("File complete and consistent." if not warnings
                         else "Attention: " + " ".join(warnings))
        note = f"{state_of_file} Among the 15 most similar past applicants, {defaults} defaulted."
        if precedents:
            note += " " + cite(precedents[0])
        mode = "rules"
    report = AnalystReport(warnings=warnings, peer_default_rate=rate, peer_count=15, peers=peers, note=note,
                           precedents=precedents)
    headline = "file consistent" if not warnings else plural(len(warnings), "warning")
    memory = f"; {plural(len(precedents), 'similar file')} already audited" if precedents else ""
    return {"analysis": report, "warnings": warnings,
            "log": f"File {app.applicant_id} checked: {headline}; {defaults} of 15 similar past applicants defaulted{memory}.",
            "reasoning": note, "mode": mode, "tool_calls": rec.calls, "status": "completed"}
