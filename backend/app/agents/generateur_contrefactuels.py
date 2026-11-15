"""Générateur-Contrefactuels (task M4).

Plans a search strategy, runs the counterfactual tools and returns
candidates that were all re-scored by the model.

The strategy (which attributes to act on, how many at once, how far) is
chosen by the LLM from the SHAP factors, the moves permitted for this
applicant and the objections raised by the Vérificateur-Équité at the
previous attempt. The plan is validated: only actionable attributes, and
never the same plan as a failed attempt. Without a usable plan, the agent
follows a fixed escalation ladder:
    attempt 1  loan terms only (amount, duration, guarantor), two changes at most
    attempt 2  loan terms and financial situation, three changes at most
    attempt 3  same attributes, wider ranges
"""
import re
from typing import Literal

from pydantic import BaseModel, Field

from app import config
from app.agents.base import Recorder, guarded_answer, plural
from app.domain import features
from app.domain.features import ACTIONABLE, BY_NAME
from app.graph.state import AuditState
from app.tools.counterfactuals import REQUEST_SCOPE, closest_miss, generate_counterfactuals, permitted_moves

SYSTEM = """You are the recourse planner of a credit audit team. A loan was refused. You choose where a
search tool will look for the smallest realistic changes that turn the refusal into an approval. You do not
compute anything: you only choose the attributes the tool may change.
You receive: the main risk factors, the list "actionable" (attributes the applicant can act on, what acting
on each one means, its scope and its permitted values), the attempt number, "untried" (actionable attributes
no earlier plan used) and the auditor's objections to the previous attempt.
Rules:
1. Choose features only from "actionable".
2. Attempt 1: choose every attribute of scope "request" (the applicant can change them today).
3. Later attempts: the previous plan failed, so the new plan must add attributes from "untried", normally
   all of them. Read the objections: if the best reachable risk stayed above the threshold, loan terms are
   not enough and the financial situation (scope "situation") must join the search.
4. Give priority to attributes that appear in the risk factors as raising the risk.
5. max_changes is 1, 2 or 3: use 2 on attempt 1 and 3 afterwards. Set widen to true only on attempt 3.
6. Attempt 3 is the last one: choose every attribute of "actionable", with max_changes 3 and widen true.
Answer with a JSON object:
{"features": ["..."], "max_changes": 2, "widen": false, "rationale": "one or two sentences naming the attributes and why"}"""

MEANING = {
    "credit_amount": "request a smaller amount",
    "duration_months": "repay over fewer months",
    "other_debtors": "add a guarantor",
    "checking_status": "improve the checking account balance",
    "savings": "build up savings",
    "existing_credits": "close a running credit at this bank",
    "other_installment_plans": "settle instalment plans held elsewhere",
}


class Plan(BaseModel):
    features: list[str] = Field(min_length=1)
    max_changes: Literal[1, 2, 3] = 2
    widen: bool = False
    rationale: str = Field(min_length=10, max_length=500)

    def key(self) -> tuple:
        return (tuple(sorted(self.features)), self.max_changes, self.widen)



def plain_names(text: str) -> str:
    """Raw attribute names a model may quote ("duration_months") become their labels ("duration")."""
    for f in sorted(features.FEATURES, key=lambda f: -len(f.name)):
        if "_" in f.name:
            text = re.sub(rf"\b{f.name}\b", f.label.lower(), text)
    return text

def ladder(attempt: int, available: list[str]) -> Plan:
    request = [f for f in available if f in REQUEST_SCOPE]
    if attempt == 1 and request:
        return Plan(features=request, max_changes=2,
                    rationale="Loan terms first: amount, duration and guarantor can change immediately.")
    if attempt <= 2:
        return Plan(features=available, max_changes=3,
                    rationale="Loan terms alone were not enough: the financial situation is added to the search.")
    return Plan(features=available, max_changes=3, widen=True,
                rationale="Last attempt: larger reductions of amount and duration are allowed.")


def run(state: AuditState) -> AuditState:
    app, score = state["application"], state["score"]
    attempt = state.get("attempts", 0) + 1
    tried: list[tuple] = list(state.get("cf_plans", []))
    feedback = state["fairness"].reasons if attempt > 1 and state.get("fairness") else []
    rec = Recorder()

    moves = rec.call("permitted_moves", permitted_moves, app, None, attempt > 1,
                     show={"widen": attempt > 1},
                     summary=lambda m: f"{plural(len(m), 'actionable attribute')}: {', '.join(m) or 'none'}")
    available = list(moves)
    if not available:
        return {"counterfactuals": [], "attempts": attempt, "cf_plans": tried,
                "log": f"Attempt {attempt}: no attribute of this file can be acted on.",
                "reasoning": "Every actionable attribute is already at its best permitted value.",
                "mode": "rules", "tool_calls": rec.calls, "status": "completed"}

    used = {f for k in tried for f in k[0]}
    untried = [f for f in available if f not in used]
    facts = {
        "attempt": attempt,
        "risk_factors": [{"feature": f.feature, "effect": "raises risk" if f.contribution > 0 else "lowers risk"}
                         for f in score.top_factors],
        "actionable": [{"feature": n, "meaning": MEANING.get(n, ""), "scope": BY_NAME[n].recourse,
                        "current": getattr(app, n), "permitted_values": v} for n, v in moves.items()],
        "untried": untried,
        "plans_already_tried": [{"features": list(k[0]), "max_changes": k[1], "widen": k[2]} for k in tried],
        "auditor_objections": feedback,
    }

    def check(p: Plan) -> str | None:
        unknown = [f for f in p.features if f not in available]
        if unknown:
            return f"not actionable for this applicant: {', '.join(unknown)}"
        if p.widen and attempt < 3:
            return "widen is only allowed on attempt 3"
        if attempt >= config.MAX_CF_ATTEMPTS:
            missing = [f for f in available if f not in p.features]
            if missing or not p.widen or p.max_changes != 3:
                return ("the last attempt must search everything: every actionable attribute, max_changes 3, "
                        f"widen true{'; missing: ' + ', '.join(missing) if missing else ''}")
        elif attempt == 1:
            missing = [f for f in available if f in REQUEST_SCOPE and f not in p.features]
            if missing:
                return f"attempt 1 must include every request attribute; missing: {', '.join(missing)}"
        elif untried and not any(f in untried for f in p.features):
            return f"the plan repeats attributes that already failed; add untried attributes: {', '.join(untried)}"
        elif not untried and not p.widen and p.key() in tried:
            return "this plan was already tried and failed"
        return None

    plan = guarded_answer(SYSTEM, facts, Plan, check=check)
    mode = "llm" if plan else "rules"
    if plan is None:
        for step in range(attempt, 4):  # never replay a plan that already failed
            plan = ladder(step, available)
            if plan.key() not in tried:
                break

    cfs = rec.call(
        "generate_counterfactuals", generate_counterfactuals, app, plan.features, plan.max_changes, plan.widen,
        show={"features": plan.features, "max_changes": plan.max_changes, "widen": plan.widen},
        summary=lambda r: (f"{plural(len(r), 'candidate')} re-scored, "
                           f"{sum(1 for c in r if c.valid and c.actionable)} flip the decision"))
    usable = [c for c in cfs if c.valid and c.actionable]
    if not usable:
        miss = rec.call("closest_miss", closest_miss, app, plan.features, plan.widen,
                        show={"features": plan.features},
                        summary=lambda c: f"best reachable risk {c.new_probability:.0%}" if c else "none")
        if miss and not any(miss.changes == c.changes for c in cfs):
            cfs = [miss] + cfs

    scope = ("loan terms" if set(plan.features) <= set(REQUEST_SCOPE) else "loan terms and financial situation")
    found = f"{plural(len(usable), 'way')} to approval found" if usable else "nothing flips the decision"
    log = (f"Attempt {attempt} ({scope}, up to {plural(plan.max_changes, 'change')}"
           f"{', wider ranges' if plan.widen else ''}): {found}.")
    return {"counterfactuals": cfs, "attempts": attempt, "cf_plans": tried + [plan.key()],
            "log": log, "reasoning": plain_names(plan.rationale), "mode": mode, "tool_calls": rec.calls, "status": "completed"}
