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
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.base import Recorder, guarded_answer, plural
from app.domain.features import ACTIONABLE, BY_NAME
from app.graph.state import AuditState
from app.tools.counterfactuals import REQUEST_SCOPE, closest_miss, generate_counterfactuals, permitted_moves

SYSTEM = """You are the recourse planner of a credit audit team. A loan was refused. Your job is to choose
where to search for the smallest realistic changes that would turn the refusal into an approval.
You receive: the main risk factors (SHAP), the attributes the applicant can act on with their permitted
values, the attempt number, the plans already tried and the objections of the fairness auditor.
Rules: choose only attributes from "actionable". Prefer loan terms (scope "request") on the first attempt
because the applicant can change them immediately; add the financial situation (scope "situation") when
loan terms were not enough. Never repeat a plan that already failed. max_changes is 1, 2 or 3. Set widen
to true only from the second attempt, to allow larger reductions.
Answer with a JSON object:
{"features": ["..."], "max_changes": 2, "widen": false, "rationale": "one or two sentences"}"""


class Plan(BaseModel):
    features: list[str] = Field(min_length=1)
    max_changes: Literal[1, 2, 3] = 2
    widen: bool = False
    rationale: str = Field(min_length=10, max_length=500)

    def key(self) -> tuple:
        return (tuple(sorted(self.features)), self.max_changes, self.widen)


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

    facts = {
        "attempt": attempt,
        "risk_factors": [{"feature": f.feature, "effect": "raises risk" if f.contribution > 0 else "lowers risk",
                          "contribution": round(f.contribution, 2)} for f in score.top_factors],
        "actionable": [{"feature": n, "scope": BY_NAME[n].recourse, "current": getattr(app, n),
                        "permitted_values": v} for n, v in moves.items()],
        "plans_already_tried": [{"features": list(k[0]), "max_changes": k[1], "widen": k[2]} for k in tried],
        "auditor_objections": feedback,
    }

    def check(p: Plan) -> str | None:
        unknown = [f for f in p.features if f not in available]
        if unknown:
            return f"not actionable for this applicant: {', '.join(unknown)}"
        if p.key() in tried:
            return "this plan was already tried and failed"
        if p.widen and attempt == 1:
            return "widen is not allowed on the first attempt"
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
            "log": log, "reasoning": plan.rationale, "mode": mode, "tool_calls": rec.calls, "status": "completed"}
