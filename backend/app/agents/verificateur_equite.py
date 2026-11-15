"""Vérificateur-Équité (task I2).

The auditor of the team. It trusts nothing it receives:

1. Individual fairness: the decision is re-scored with each sensitive
   attribute flipped (`sensitive_flip_test`).
2. Group fairness: Fairlearn metrics of the model on the held-out files
   (`group_fairness_metrics`) and the position of the applicant's own
   groups in them (`group_context`). These are recorded as notes. They
   describe the model, not this file, so they never reject a proposal.
3. Every counterfactual proposed by the Générateur-Contrefactuels is
   verified again, independently of the flags it arrived with: recourse
   rules (`check_actionability`), a fresh model call (`rescore_candidates`)
   and realism against past applicants (`plausibility_score`).

A proposal survives only when it is actionable, really flips the decision,
keeps a safety margin and stays a plausible file. When nothing survives,
the step is `rejected` and the objections go back to the generator, which
must then follow a different plan (see graph/build.py). Objections are
short and name what to change, because the next plan is built from them.

The verdict is decided by these rules. The LLM only words it, through
`guarded_answer`: its text is refused when it contradicts the outcome,
names a protected attribute that was not tested, or quotes a number absent
from the tool outputs. Without a usable answer the rule-based wording is used.
"""
from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from app import config
from app.agents.base import Recorder, guarded_answer, plural
from app.domain.features import BY_NAME
from app.graph.state import AuditState
from app.schemas import Counterfactual, FairnessVerdict, LoanApplication
from app.tools import scoring
from app.tools.counterfactuals import REQUEST_SCOPE, check_actionability
from app.tools.fairness import group_context, group_fairness_metrics, plausibility_score, sensitive_flip_test

SYSTEM = """You are the fairness auditor of a credit audit team. Other agents scored a loan application and,
for a refusal, proposed changes that would lead to an approval. Tools have already tested everything; you
receive their results as facts: the flip test on sensitive attributes, the number of proposals checked, kept
and rejected with the reason of each rejection, and the outcome of the audit.
Write the audit verdict in at most 70 words of plain English for a credit officer: state whether the decision
depends on a sensitive attribute, how many proposals survive and why the others were rejected. Use only the
facts given and only numbers present in them. Do not propose new changes and do not give a credit decision.
Set "outcome" to the value of "outcome" in the facts.
Answer with a JSON object: {"verdict": "...", "outcome": "accepted" or "rejected"}"""

SENSITIVE_LABELS = {"sex": "sex", "foreign_worker": "foreign-worker status"}
_FORBIDDEN = ("age", "religion", "marital", "ethnic", "race")


class Verdict(BaseModel):
    verdict: str = Field(min_length=30, max_length=700)
    outcome: Literal["accepted", "rejected"]


def _changes(cf: Counterfactual) -> dict:
    return {c.feature: c.to_value for c in cf.changes}


def _rescore(app: LoanApplication, cfs: list[Counterfactual]) -> list[float]:
    """Fresh model call on every proposal: the auditor does not reuse the generator's probabilities."""
    base = app.features()
    return [float(p) for p in scoring.probabilities({**base, **_changes(cf)} for cf in cfs)]


def _verify(app: LoanApplication, cfs: list[Counterfactual], rec: Recorder) -> list[tuple[Counterfactual, str | None]]:
    """Each proposal with its objection, or None when it survives."""
    if not cfs:
        return []
    thr = scoring.threshold()
    rules = rec.call(
        "check_actionability", lambda: [check_actionability(app, _changes(cf)) for cf in cfs],
        show={"candidates": len(cfs)},
        summary=lambda r: f"{sum(1 for ok, _ in r if ok)} of {len(r)} respect the recourse rules")
    probs = rec.call(
        "rescore_candidates", _rescore, app, cfs, show={"candidates": len(cfs), "threshold": thr},
        summary=lambda r: f"{sum(1 for p in r if p < thr)} of {len(r)} flip the decision after re-scoring")
    realism = rec.call(
        "plausibility_score", lambda: [plausibility_score(app, _changes(cf)) for cf in cfs],
        show={"candidates": len(cfs), "k": config.PLAUSIBILITY_K},
        summary=lambda r: (f"{sum(1 for x in r if x.plausible)} of {len(r)} stay close to real past applicants "
                           f"(distance limit {r[0].limit:.2f})"))

    out = []
    for cf, (actionable, why), p, plaus in zip(cfs, rules, probs, realism):
        valid = p < thr
        robust = valid and p <= thr - config.ROBUST_MARGIN
        checked = cf.model_copy(update={
            "new_probability": round(p, 4), "valid": valid, "actionable": actionable, "robust": robust,
            "plausibility": plaus, "rejection_reason": why if not actionable else cf.rejection_reason})
        if not actionable:
            objection = why or "not actionable"
        elif not valid:
            objection = f"every permitted change together only reaches {p:.0%}, above the threshold"
        elif not robust:
            objection = "flips the decision without a safety margin"
        elif not plaus.plausible:
            objection = "unrealistic file, too far from past applicants"
        else:
            objection = None
        if objection and actionable:
            checked = checked.model_copy(update={"rejection_reason": objection})
        out.append((checked, objection))
    return out


def _hint(app: LoanApplication, checked: list[tuple[Counterfactual, str | None]]) -> str | None:
    """What the next plan should do differently, deduced from the rejections."""
    if not checked:
        return None
    touched = {c.feature for cf, _ in checked for c in cf.changes}
    reasons = [why or "" for _, why in checked]
    if touched and touched <= set(REQUEST_SCOPE) and any("above the threshold" in r or "safety margin" in r for r in reasons):
        return "loan terms alone are not enough: add the financial situation"
    if any("unrealistic" in r for r in reasons):
        return "prefer fewer or smaller changes: large combined changes leave the range of real files"
    if any("above the threshold" in r for r in reasons):
        return "allow wider ranges on amount and duration"
    return None


def _rule_based(flip_ok: bool, refused: bool, checked: int, kept: int, reasons: list[str]) -> str:
    first = ("The decision is unchanged when a sensitive attribute is flipped." if flip_ok
             else "The decision changes when only a sensitive attribute is flipped, so it cannot be closed without a person.")
    if not refused:
        return first + " The file is approved, so no way to approval had to be verified."
    if kept:
        second = f" {plural(kept, 'proposal')} out of {checked} passed every check: recourse rules, re-scoring with a safety margin and realism."
    elif checked:
        second = f" None of the {plural(checked, 'proposal')} survives."
    else:
        second = " No proposal was submitted."
    objections = [r.replace(" rejected (", " (") for r in reasons
                  if "sensitive attribute" not in r and not r.startswith("next plan")]
    if objections and kept < checked:
        second += " Rejected: " + "; ".join(objections) + "."
    return first + second


def run(state: AuditState) -> AuditState:
    app, score = state["application"], state["score"]
    refused = score.decision == "refused"
    rec = Recorder()

    # 1. individual fairness
    flip_ok, metrics = rec.call(
        "sensitive_flip_test", sensitive_flip_test, app, show={"attributes": list(config.SENSITIVE_FEATURES)},
        summary=lambda r: "decision unchanged" if r[0] else "decision changes with a sensitive attribute")
    # 2. group fairness of the model in use
    group = rec.call(
        "group_fairness_metrics", group_fairness_metrics, show={"variant": scoring.model().variant},
        summary=lambda m: (f"approval gap {m['dp_diff_sex']:.0%} by sex, {m['dp_diff_age_group']:.0%} by age band; "
                           f"equalized odds gap {m['eo_diff_sex']:.0%} and {m['eo_diff_age_group']:.0%}"))
    metrics.update(group)
    context = rec.call(
        "group_context", group_context, app, show={"applicant": app.applicant_id},
        summary=lambda c: "; ".join(f"{x['label'].lower()} {x['group'].replace('_', ' ')}: approved {x['approval_rate']:.0%}"
                                    for x in c))
    notes = [
        f"The applicant belongs to the group \"{c['group'].replace('_', ' ')}\" ({c['label'].lower()}), approved "
        f"{c['gap'] * 100:.0f} points less often than the group \"{c['best_group'].replace('_', ' ')}\" on the test set."
        for c in context if c["disadvantaged"]]

    # 3. independent verification of every proposal
    cfs = state.get("counterfactuals", [])
    checked = _verify(app, cfs, rec)
    kept = [cf for cf, objection in checked if objection is None]

    reasons: list[str] = []
    if not flip_ok:
        changed = [SENSITIVE_LABELS.get(f, f) for f in config.SENSITIVE_FEATURES
                   if _decision_changes(app, f, score.decision)]
        reasons.append("the decision changes when only a sensitive attribute changes"
                       + (f" ({', '.join(changed)})" if changed else ""))
    counts: Counter[str] = Counter(objection for _, objection in checked if objection)
    reasons += [why if why.startswith("every permitted") else f"{plural(n, 'candidate')} rejected ({why})"
                for why, n in counts.items()]
    another_attempt = state.get("attempts", 0) < config.MAX_CF_ATTEMPTS
    hint = _hint(app, checked) if refused and not kept and another_attempt else None
    if hint:
        reasons.append(f"next plan: {hint}")

    passed = flip_ok and (not refused or len(kept) > 0)
    outcome = "accepted" if passed else "rejected"

    facts = {
        "decision": score.decision, "outcome": outcome,
        "flip_test": {"decision_unchanged": flip_ok,
                      "risk_change_in_points": {SENSITIVE_LABELS.get(k.replace("flip_delta_", ""), k): round(v * 100, 1)
                                                for k, v in metrics.items() if k.startswith("flip_delta_")}},
        "proposals_checked": len(checked), "proposals_kept": len(kept),
        "rejections": [{"count": n, "reason": why} for why, n in counts.items()],
        "kept": [{"changes": cf.statement, "risk_after_percent": round(cf.new_probability * 100),
                  "plausibility_percent": round(cf.plausibility.score * 100)} for cf in kept],
        "threshold_percent": round(score.threshold * 100),
    }

    def check(a: Verdict) -> str | None:
        if a.outcome != outcome:
            return f"the outcome of the audit is \"{outcome}\", it is decided by the tools"
        low = f" {a.verdict.lower()} "
        named = [w for w in _FORBIDDEN if f" {w} " in low or f" {w}," in low or f" {w}." in low]
        if named:
            return f"mentions an attribute that was not part of the flip test: {', '.join(named)}"
        return None

    answer = guarded_answer(SYSTEM, facts, Verdict, check=check, text_fields=("verdict",))
    wording = answer.verdict if answer else _rule_based(flip_ok, refused, len(checked), len(kept), reasons)

    verdict = FairnessVerdict(
        passed=passed, reasons=reasons, metrics=metrics, flip_test_passed=flip_ok, verdict=wording, notes=notes,
        group_context=context, candidates_checked=len(checked), candidates_kept=len(kept))

    if not refused:
        log = ("Approval audited: sensitive attributes do not change the decision." if flip_ok
               else "Approval audited: " + reasons[0] + ".")
    elif kept:
        dropped = len(checked) - len(kept)
        log = f"{plural(len(kept), 'way')} to approval verified" + (
            f", {plural(dropped, 'candidate')} rejected." if dropped else ".")
        if not flip_ok:
            log += " The decision itself depends on a sensitive attribute."
    else:
        shown = [r for r in reasons if not r.startswith("next plan")]
        log = "Nothing survives the audit: " + "; ".join(shown[:3] or ["no proposal was submitted"]) + "."
    return {"fairness": verdict, "counterfactuals": kept, "log": log, "reasoning": wording,
            "mode": "llm" if answer else "rules", "tool_calls": rec.calls,
            "status": "completed" if passed else "rejected"}


def _decision_changes(app: LoanApplication, feature: str, decision: str) -> bool:
    from app.tools.fairness import _flipped  # same flip as the tool, to name the attribute

    return scoring.score_applicant(_flipped(app, feature), explain=False).decision != decision
