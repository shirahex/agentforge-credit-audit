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
loan application: the list of consistency warnings (it may be empty), how many of the most similar past
applicants defaulted and, when there is one, the closest file already audited by this team ("previous_audit").
Write an analyst note of two sentences, at most 40 words, in plain English.
Sentence 1: say whether the file is consistent; if there are warnings, say what they are about.
Sentence 2: report how many of the similar past applicants defaulted, as a plain count.
When "previous_audit" is given, add a third sentence of at most 20 words stating that applicant and its outcome.
Report facts only. Do not judge the count as high or low. Do not give advice, a recommendation, a decision
or a probability. Do not mention sex, age or nationality. Use only numbers present in the facts.
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
    facts = {"number_of_warnings": len(warnings), "warnings": warnings,
             "similar_past_applicants": 15, "of_which_defaulted": defaults}
    if precedents:
        first = precedents[0]
        facts["previous_audit"] = {"applicant": first.applicant_id, "similarity_percent": similarity_percent(first.similarity),
                                   "outcome": first.final_outcome, "decided_by_a_person": first.reviewed,
                                   "verified_ways_to_approval": first.paths}
    banned = ("caution", "recommend", "should", "high default", "low default", "investigat")

    def check(a: Note) -> str | None:
        used = [w for w in banned if w in a.note.lower()]
        return f"the note gives advice or a judgement ({', '.join(used)}); report facts only" if used else None

    answer = guarded_answer(SYSTEM, facts, Note, check=check, text_fields=("note",))
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
