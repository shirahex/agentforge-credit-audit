"""Analyste-Dossier (task M4).

Checks the applicant file before any scoring: consistency rules, position
against past files, and the outcome actually observed for the most similar
past applicants. The LLM writes the analyst note from these tool outputs;
the note is rejected if it quotes a number the tools did not produce.
"""
from pydantic import BaseModel, Field

from app.agents.base import Recorder, guarded_answer, plural
from app.graph.state import AuditState
from app.schemas import AnalystReport
from app.tools.analysis import similar_cases, validate_application

SYSTEM = """You are the file analyst of a credit audit team. You receive facts produced by tools about one
loan application: the list of consistency warnings (it may be empty) and how many of the most similar past
applicants defaulted.
Write an analyst note of two sentences, at most 40 words, in plain English.
Sentence 1: say whether the file is consistent; if there are warnings, say what they are about.
Sentence 2: report how many of the similar past applicants defaulted, as a plain count.
Report facts only. Do not judge the count as high or low. Do not give advice, a recommendation, a decision
or a probability. Do not mention sex, age or nationality. Use only numbers present in the facts.
Answer with a JSON object: {"note": "..."}"""


class Note(BaseModel):
    note: str = Field(min_length=20, max_length=600)


def run(state: AuditState) -> AuditState:
    app = state["application"]
    rec = Recorder()
    warnings = rec.call("validate_application", validate_application, app,
                        show={"applicant": app.applicant_id},
                        summary=lambda w: plural(len(w), "warning"))
    rate, peers = rec.call("similar_cases", similar_cases, app, 15, show={"k": 15},
                           summary=lambda r: f"{round(r[0] * 15)} of 15 similar past applicants defaulted")
    defaults = round(rate * 15)
    facts = {"number_of_warnings": len(warnings), "warnings": warnings,
             "similar_past_applicants": 15, "of_which_defaulted": defaults}
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
        mode = "rules"
    report = AnalystReport(warnings=warnings, peer_default_rate=rate, peer_count=15, peers=peers, note=note)
    headline = "file consistent" if not warnings else plural(len(warnings), "warning")
    return {"analysis": report, "warnings": warnings,
            "log": f"File {app.applicant_id} checked: {headline}; {defaults} of 15 similar past applicants defaulted.",
            "reasoning": note, "mode": mode, "tool_calls": rec.calls, "status": "completed"}
