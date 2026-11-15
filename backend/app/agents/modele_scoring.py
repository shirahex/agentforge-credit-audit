"""Modèle-Scoring (task M4).

Calls the scoring model and its exact SHAP explanation, then words the
result. The LLM may only cite factors returned by SHAP and numbers returned
by the tools: an explanation that cites anything else is rejected, retried
once, then replaced by the rule-based wording.
"""
from pydantic import BaseModel, Field

from app.agents.base import Recorder, guarded_answer
from app.graph.state import AuditState
from app.schemas import ScoreResult
from app.tools.scoring import explain_applicant, score_applicant

SYSTEM = """You are the scoring analyst of a credit audit team. You receive the output of a credit scoring
model for one applicant: the default probability, the refusal threshold, the decision, and the main
factors with their signed contribution (positive raises the default risk, negative lowers it).
Explain the decision in at most 70 words of plain English for a credit officer. Cite only factors from
the list, with their direction. Use only numbers present in the facts. Do not suggest changes and do not
mention sex, age or nationality unless they are in the factor list.
Answer with a JSON object: {"explanation": "...", "cited_features": ["feature_name", ...]}"""


class Explanation(BaseModel):
    explanation: str = Field(min_length=30, max_length=800)
    cited_features: list[str] = Field(min_length=1)


def rule_based(score: ScoreResult) -> str:
    def name(f) -> str:
        label = f.label.lower().replace(" (share of income)", "")
        return f"{label}: {f.value_label[:1].lower() + f.value_label[1:]}"

    up = [name(f) for f in score.top_factors if f.contribution > 0][:3]
    down = [name(f) for f in score.top_factors if f.contribution < 0][:2]
    text = (f"Default risk estimated at {score.default_probability:.0%} against a refusal threshold of "
            f"{score.threshold:.0%}: {score.decision}.")
    if up:
        text += " Raising the risk: " + "; ".join(up) + "."
    if down:
        text += " Lowering it: " + "; ".join(down) + "."
    return text


def run(state: AuditState) -> AuditState:
    app = state["application"]
    rec = Recorder()
    score: ScoreResult = rec.call(
        "score_applicant", score_applicant, app, False, show={"applicant": app.applicant_id},
        summary=lambda s: f"p(default) = {s.default_probability:.3f}, threshold {s.threshold:.2f}, {s.decision}")
    factors, base = rec.call(
        "shap_explain", explain_applicant, app, show={"top_k": 6},
        summary=lambda r: "top factors: " + ", ".join(f"{f.feature} {f.contribution:+.2f}" for f in r[0][:4]))
    score = score.model_copy(update={"top_factors": factors, "base_probability": base})

    allowed = {f.feature for f in score.top_factors}
    facts = {
        "default_probability_percent": round(score.default_probability * 100),
        "refusal_threshold_percent": round(score.threshold * 100),
        "decision": score.decision,
        "factors": [{"feature": f.feature, "label": f.label, "value": f.value_label,
                     "effect": "raises risk" if f.contribution > 0 else "lowers risk",
                     "contribution": round(f.contribution, 2)} for f in score.top_factors],
    }

    def check(a: Explanation) -> str | None:
        unknown = [c for c in a.cited_features if c not in allowed]
        return f"cited features not in the factor list: {', '.join(unknown)}" if unknown else None

    answer = guarded_answer(SYSTEM, facts, Explanation, check=check, text_fields=("explanation",))
    explanation, mode = (answer.explanation, "llm") if answer else (rule_based(score), "rules")
    main = score.top_factors[0]
    return {"score": score, "explanation": explanation,
            "log": (f"Default risk {score.default_probability:.0%}, threshold {score.threshold:.0%}: "
                    f"{score.decision}. Main factor: {main.label.lower()}."),
            "reasoning": explanation, "mode": mode, "tool_calls": rec.calls, "status": "completed"}
