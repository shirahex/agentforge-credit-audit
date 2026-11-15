"""Modèle-Scoring (task M4).

Calls the scoring model and its exact SHAP explanation, then words the
result. The LLM may only cite factors returned by SHAP and numbers returned
by the tools: an explanation that cites anything else is rejected, retried
once, then replaced by the rule-based wording.
"""
import re

from pydantic import BaseModel, Field

from app.agents.base import Recorder, guarded_answer
from app.graph.state import AuditState
from app.schemas import ScoreResult
from app.tools.scoring import explain_applicant, score_applicant

SYSTEM = """You are the scoring analyst of a credit audit team. You receive the output of a credit scoring
model for one applicant: the default probability, the refusal threshold, the decision, and two lists of
factors computed by SHAP: "raises_risk" (factors that push the default risk up) and "lowers_risk" (factors
that pull it down), each ordered from strongest to weakest.
Explain the decision to a credit officer in two or three sentences, at most 60 words, plain English.
Name the two or three strongest factors of "raises_risk" as raising the risk, and one or two of
"lowers_risk" as lowering it. Never swap the two lists: a factor's direction is given, do not reason about
it. In the explanation, refer to each factor by its label and value in plain words (for example
"an overdrawn checking account"), never by its feature name. Use only numbers present in the facts. Do not
suggest changes.
Answer with a JSON object:
{"explanation": "...", "raises_risk": ["feature_name", ...], "lowers_risk": ["feature_name", ...]}
where the two lists hold the feature names you mentioned, each on the side given in the facts."""


class Explanation(BaseModel):
    explanation: str = Field(min_length=30, max_length=600)
    raises_risk: list[str] = []
    lowers_risk: list[str] = []


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

    up = {f.feature for f in score.top_factors if f.contribution > 0}
    down = {f.feature for f in score.top_factors if f.contribution < 0}

    def side(positive: bool) -> list[dict]:
        return [{"feature": f.feature, "label": f.label, "value": f.value_label}
                for f in score.top_factors if (f.contribution > 0) == positive]

    facts = {
        "default_probability_percent": round(score.default_probability * 100),
        "refusal_threshold_percent": round(score.threshold * 100),
        "decision": score.decision,
        "raises_risk": side(True),
        "lowers_risk": side(False),
    }

    def check(a: Explanation) -> str | None:
        if not a.raises_risk and not a.lowers_risk:
            return "no factor is cited"
        wrong_up = [c for c in a.raises_risk if c not in up]
        wrong_down = [c for c in a.lowers_risk if c not in down]
        if wrong_up:
            return f"these are not in the raises_risk facts: {', '.join(wrong_up)}"
        if wrong_down:
            return f"these are not in the lowers_risk facts: {', '.join(wrong_down)}"
        text = a.explanation.lower()
        said = set(re.findall(r"[a-z0-9]+", text))  # whole words: "used" must not match "refused"
        named = 0
        for f in score.top_factors:
            if f.feature in a.raises_risk + a.lowers_risk:
                words = [w for w in f"{f.label} {f.value_label}".lower().replace("(", " ").replace(")", " ").split()
                         if len(w) >= 3 and w not in ("than", "more", "less", "with", "this", "bank", "years", "the",
                                                      "and", "for", "not", "per", "from", "level", "other")]
                named += any(w.strip(",.;:") in said for w in words)
        if named < min(2, len(score.top_factors)):
            return "the explanation does not name its factors; name at least two of them by label and value"
        if any(f.feature in text for f in score.top_factors if "_" in f.feature):
            return "the explanation uses feature names with underscores; use the labels in plain words"
        if len(a.explanation.split()) > 80:
            return "the explanation is longer than 60 words"
        return None

    answer = guarded_answer(SYSTEM, facts, Explanation, check=check, text_fields=("explanation",))
    explanation, mode = (answer.explanation, "llm") if answer else (rule_based(score), "rules")
    main = score.top_factors[0]
    return {"score": score, "explanation": explanation,
            "log": (f"Default risk {score.default_probability:.0%}, threshold {score.threshold:.0%}: "
                    f"{score.decision}. Main factor: {main.label.lower()}."),
            "reasoning": explanation, "mode": mode, "tool_calls": rec.calls, "status": "completed"}
