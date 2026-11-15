"""Arbitre et Rédacteur (task I2).

Last agent of the audit. It does four things:

1. Memory: asks the case store for similar files already audited and
   checks that a near-identical file did not receive the opposite outcome.
2. Arbitration: closes the audit or hands it to a person. Four rules, in
   order: the decision depends on a sensitive attribute; the score is
   within the borderline band; no verified way to approval was found; a
   near-identical past file ended differently.
3. Writing: the applicant letter, in French. The LLM writes it from tool
   outputs only, through `guarded_answer`: the letter is refused when its
   decision differs from the audit, when it names a protected attribute,
   or when it quotes a number absent from the facts. Without a usable
   answer, a fixed French template built from the same facts is used.
   The letter of an escalated file stays a draft until the reviewer decides.
4. Closing (`close`, called by the graph once the step is recorded): PDF
   report through tools/report.py and storage of the case.

`human_review` is the second half of the same agent: the graph interrupts
on it for an escalated file, and the reviewer's answer resumes it. The
letter is then rewritten for the final outcome and the audit is closed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app import config
from app.agents.base import Recorder, guarded_answer, plural, similarity_percent
from app.domain import fr
from app.domain.features import BY_NAME
from app.graph.state import AuditState
from app.memory import case_store
from app.schemas import AuditDecision, Counterfactual, LoanApplication, PastAudit, ScoreResult
from app.tools.report import render_report

SYSTEM = """Tu es le rédacteur du service crédit d'une banque. Tu écris la lettre adressée au demandeur d'un
crédit, en français, à partir des faits fournis par les outils d'audit (JSON). Règles :
- Commence par "Objet : " suivi de l'objet de la lettre avec le numéro de dossier, puis "Madame, Monsieur,".
- Annonce la décision indiquée dans "decision_finale" ("approved" = demande acceptée, "refused" = demande refusée).
- Pour un refus : cite les éléments de "facteurs_defavorables" puis, si "pistes" n'est pas vide, présente chaque
  piste en reprenant son texte tel qu'il est donné, avec son risque estimé. Si "pistes" est vide, dis qu'aucune
  modification réaliste n'a été identifiée.
- Pour une acceptation : cite les éléments de "facteurs_favorables".
- Si "examen_humain" est renseigné, précise que le dossier a été examiné individuellement par un conseiller.
- Termine par la phrase de "droits" si elle est renseignée, puis une formule de politesse et la signature
  "Le service crédit".
- N'utilise que les faits fournis. Aucun chiffre qui ne figure pas dans les faits. Ne mentionne jamais le sexe,
  l'âge, la nationalité ou le statut de travailleur étranger. Ne promets rien au-delà des faits.
- 250 mots au maximum, ton courtois et direct, sans listes à puces autres que les pistes numérotées.
Réponds par un objet JSON : {"letter": "...", "decision": "approved" ou "refused"}"""

_FORBIDDEN_FR = ("sexe", "âge", "nationalité", "étranger", "étrangère", "homme", "femme", "genre")
RIGHTS = ("Vous pouvez demander le réexamen de votre dossier par un conseiller et obtenir des précisions sur "
          "les éléments pris en compte dans cette évaluation.")


class Letter(BaseModel):
    letter: str = Field(min_length=250, max_length=3200)
    decision: Literal["approved", "refused"]


# --------------------------------------------------------------------------- arbitration
def escalation_reason(score: ScoreResult, flip_ok: bool, cfs: list[Counterfactual], attempts: int,
                      conflict: str | None) -> str | None:
    """The first rule that sends the file to a person, or None when the agents can close it."""
    if not flip_ok:
        return "the decision depends on a sensitive attribute"
    if abs(score.default_probability - score.threshold) <= config.BORDERLINE_MARGIN:
        return "the score falls within the borderline band around the threshold"
    if score.decision == "refused" and not cfs:
        return f"no verified way to approval was found after {plural(attempts, 'attempt')}"
    if conflict:
        return f"{conflict}, so the two outcomes must be reconciled by a person"
    return None


def precedent_conflict(precedents: list[PastAudit], decision: str) -> str | None:
    for p in precedents:
        if p.similarity >= case_store.SAME_CASE_SIMILARITY and p.final_outcome != decision:
            return f"a near-identical past file ({p.applicant_id}) was finally {p.final_outcome}"
    return None


# --------------------------------------------------------------------------- letter
def _pct(p: float, other: float | None = None) -> str:
    """'39 %', or '25,6 %' when rounding would make the risk and the threshold look equal."""
    if other is not None and round(p * 100) == round(other * 100) and p != other:
        return f"{p * 100:.1f}".replace(".", ",") + " %"
    return f"{round(p * 100)} %"


def letter_facts(app: LoanApplication, score: ScoreResult, cfs: list[Counterfactual], final: str,
                 review: dict | None, pending_review: bool, today: datetime | None = None) -> dict[str, Any]:
    """Everything the letter may say. The number guard compares the letter with this dictionary."""
    today = today or datetime.now(timezone.utc)
    visible = [f for f in score.top_factors if not BY_NAME[f.feature].protected]
    ways = sorted(cfs, key=lambda c: c.cost)
    return {
        "dossier": app.applicant_id,
        "date": fr.date(today),
        "demande": {"montant": fr.amount(app.credit_amount), "duree": f"{app.duration_months} mois",
                    "objet": fr.VALUES["purpose"][app.purpose]},
        "decision_modele": score.decision,
        "decision_finale": final,
        "risque_estime": _pct(score.default_probability, score.threshold),
        "seuil": _pct(score.threshold, score.default_probability),
        "facteurs_defavorables": [fr.factor(f.feature, f.value) for f in visible if f.contribution > 0][:3],
        "facteurs_favorables": [fr.factor(f.feature, f.value) for f in visible if f.contribution < 0][:3],
        "pistes": [{"numero": i,
                    "texte": fr.path([(c.feature, c.from_value, c.to_value) for c in cf.changes]),
                    "risque_apres": _pct(cf.new_probability),
                    "delai": "immédiat" if cf.effort == "immediate" else "demande du temps"}
                   for i, cf in enumerate(ways, 1)],
        "examen_humain": ({"conseiller": review.get("reviewer", ""), "decision": review["outcome"]} if review else None),
        "en_attente_d_examen": pending_review,
        "droits": RIGHTS if final == "refused" or pending_review else None,
    }


def template_letter(facts: dict[str, Any]) -> str:
    """Rule-based letter: every sentence is assembled from the facts, nothing else."""
    d, final, reviewed = facts["demande"], facts["decision_finale"], facts["examen_humain"] is not None
    lines = [f"Objet : votre demande de crédit, dossier {facts['dossier']}", "", f"Le {facts['date']}", "",
             "Madame, Monsieur,", "",
             f"Nous avons étudié votre demande de crédit de {d['montant']} sur {d['duree']} ({d['objet']})."]
    opening = "À l'issue d'un examen individuel de votre dossier par un conseiller, " if reviewed else "Après analyse, "
    if final == "approved":
        lines += ["", opening + "nous avons le plaisir de vous informer que votre demande est acceptée."]
        if facts["decision_modele"] == "approved":
            lines.append(f"Le risque de défaut estimé pour votre dossier est de {facts['risque_estime']}, "
                         f"en dessous de notre seuil d'acceptation de {facts['seuil']}.")
        if facts["facteurs_favorables"]:
            lines += ["", "Les éléments qui ont joué en faveur de votre dossier sont : "
                      + " ; ".join(facts["facteurs_favorables"]) + "."]
        lines += ["", "Un conseiller prendra contact avec vous pour finaliser votre contrat."]
    else:
        lines += ["", opening + "nous ne pouvons pas donner une suite favorable à cette demande en l'état."]
        if facts["decision_modele"] == "refused":
            lines.append(f"Le risque de défaut estimé pour votre dossier est de {facts['risque_estime']}, "
                         f"alors que notre seuil d'acceptation est de {facts['seuil']}.")
        if facts["facteurs_defavorables"]:
            lines += ["", "Les éléments qui ont le plus pesé dans cette évaluation sont : "
                      + " ; ".join(facts["facteurs_defavorables"]) + "."]
        if facts["pistes"]:
            lines += ["", "Votre demande pourrait être acceptée dans l'un des cas suivants. Chacun a été vérifié "
                          "sur notre modèle d'évaluation :"]
            for w in facts["pistes"]:
                when = "possible dès maintenant" if w["delai"] == "immédiat" else "demande du temps"
                lines.append(f"{w['numero']}. {w['texte']} (risque estimé : {w['risque_apres']}, {when}).")
            lines += ["", "Ces pistes décrivent ce que notre modèle déciderait pour un dossier ainsi modifié. "
                          "Une nouvelle demande reste soumise à une étude complète."]
        elif facts["decision_modele"] == "refused":
            lines += ["", "Nous n'avons pas identifié de modification réaliste de votre demande qui permettrait "
                          "de l'accepter aujourd'hui."]
    if facts["en_attente_d_examen"]:
        lines += ["", "Votre dossier est transmis à un conseiller pour un examen individuel. Vous recevrez sa "
                      "décision définitive."]
    if facts["droits"]:
        lines += ["", facts["droits"]]
    lines += ["",
              "Nous vous prions d'agréer, Madame, Monsieur, l'expression de nos salutations distinguées.", "",
              "Le service crédit"]
    return "\n".join(lines)


def write_letter(app: LoanApplication, score: ScoreResult, cfs: list[Counterfactual], final: str,
                 review: dict | None = None, pending_review: bool = False) -> tuple[str, str, dict[str, Any]]:
    """(letter, mode, facts). The LLM text is used only when it passes every guard."""
    facts = letter_facts(app, score, cfs if final == "refused" else [], final, review, pending_review)

    def check(a: Letter) -> str | None:
        if a.decision != final:
            return f"the decision of the audit is \"{final}\""
        low = a.letter.lower()
        if facts["dossier"].lower() not in low:
            return f"the letter must quote the file number {facts['dossier']}"
        import re

        named = [w for w in _FORBIDDEN_FR if re.search(rf"(?<![\wàâéèêîôûç]){w}(?![\wàâéèêîôûç])", low)]
        if named:
            return f"the letter mentions a protected attribute: {', '.join(named)}"
        if final == "refused" and facts["pistes"] and not any(w["risque_apres"].split()[0] in a.letter for w in facts["pistes"]):
            return "the letter must present the verified ways to approval with their estimated risk"
        return None

    answer = guarded_answer(SYSTEM, facts, Letter, check=check, text_fields=("letter",), max_tokens=1100)
    return (answer.letter.strip(), "llm", facts) if answer else (template_letter(facts), "rules", facts)


# --------------------------------------------------------------------------- agent step
def _summary(score: ScoreResult, cfs: list[Counterfactual]) -> str:
    close = round(score.default_probability * 100) == round(score.threshold * 100)
    p, t = (f"{score.default_probability:.1%}", f"{score.threshold:.1%}") if close else (
        f"{score.default_probability:.0%}", f"{score.threshold:.0%}")
    if score.decision == "approved":
        return f"Application approved: default risk {p}, below the {t} threshold."
    if cfs:
        best = min(cfs, key=lambda c: c.cost)
        return (f"Application refused: default risk {p}, threshold {t}. "
                f"Easiest verified way to approval: {best.statement[:1].lower() + best.statement[1:]}")
    return f"Application refused: default risk {p}, threshold {t}. No verified way to approval."


def run(state: AuditState) -> AuditState:
    app, score, fairness = state["application"], state["score"], state["fairness"]
    cfs = state.get("counterfactuals", [])
    attempts = state.get("attempts", 0)
    rec = Recorder()

    precedents = rec.call(
        "past_audits", case_store.search, app, 3, exclude_run=state.get("run_id"),
        show={"k": 3, "min_similarity": case_store.MIN_SIMILARITY},
        summary=lambda r: ("no similar file audited before" if not r else
                           "; ".join(f"{p.applicant_id} {p.final_outcome} ({similarity_percent(p.similarity)}% similar)" for p in r)))
    conflict = precedent_conflict(precedents, score.decision)
    reason = rec.call(
        "escalation_rules", escalation_reason, score, fairness.flip_test_passed, cfs, attempts, conflict,
        show={"borderline_margin": config.BORDERLINE_MARGIN, "max_attempts": config.MAX_CF_ATTEMPTS},
        summary=lambda r: f"human review required: {r}" if r else "no rule requires a human review")
    escalated = reason is not None

    letter, mode, _ = write_letter(app, score, cfs, score.decision, pending_review=escalated)
    summary = _summary(score, cfs)
    decision = AuditDecision(
        applicant_id=app.applicant_id, decision=score.decision, default_probability=score.default_probability,
        escalated=escalated, escalation_reason=reason, summary=summary, counterfactuals=cfs, fairness=fairness,
        attempts=attempts, letter=letter, letter_status="draft" if escalated else "final",
        final_outcome=None if escalated else score.decision, precedents=precedents, precedent_conflict=conflict)
    log = f"Sent to human review: {reason}." if escalated else "Audit closed without escalation."
    reasoning = summary + (f" Applicant letter {'drafted' if escalated else 'written'} in French "
                           f"({'language model, guarded' if mode == 'llm' else 'rule-based template'}).")
    return {"decision": decision, "log": log, "reasoning": reasoning, "mode": mode, "tool_calls": rec.calls,
            "status": "escalated" if escalated else "finished"}


def human_review(state: AuditState) -> AuditState:
    """Waits for the reviewer (LangGraph interrupt), then closes the audit with their decision."""
    pending: AuditDecision = state["decision"]
    review = interrupt({
        "applicant_id": pending.applicant_id, "reason": pending.escalation_reason,
        "decision": pending.decision, "default_probability": pending.default_probability})
    # Everything below runs when the review endpoint resumes the graph.
    app, score = state["application"], state["score"]
    final = review["outcome"]
    review = {**review, "at": review.get("at") or datetime.now(timezone.utc).isoformat()}
    cfs = pending.counterfactuals
    letter, mode, _ = write_letter(app, score, cfs, final, review=review)
    overturned = final != pending.decision
    who = review.get("reviewer") or "Reviewer"
    summary = (pending.summary + f" Reviewed by {who}: {final}"
               + (", against the model's decision." if overturned else ", confirming the model's decision."))
    decision = pending.model_copy(update={
        "review": review, "final_outcome": final, "letter": letter, "letter_status": "final", "summary": summary})
    log = (f"Human review by {who}: {final}"
           + (" (model decision overturned)." if overturned else " (model decision confirmed).") + " Audit closed.")
    comment = (review.get("comment") or "").strip()
    return {"decision": decision, "review": review, "log": log,
            "reasoning": (f"Reviewer's reason: {comment} " if comment else "") + "Applicant letter rewritten for the final outcome.",
            "mode": mode, "tool_calls": [], "status": "finished"}


def close(state: AuditState, decision: AuditDecision, trail: list[dict]) -> tuple[AuditDecision, list]:
    """Closing work of a durable run: PDF report, then storage of the case. Returns the tool calls made."""
    run_id = state.get("run_id")
    if not run_id:
        return decision, []
    rec = Recorder()
    app, score = state["application"], state["score"]
    report_id = f"AF-{datetime.now(timezone.utc):%Y%m%d}-{run_id[:8].upper()}"
    decision = decision.model_copy(update={"report_id": report_id})
    path = rec.call("render_report", render_report, decision, trail, application=app, run_id=run_id,
                    show={"report": report_id}, summary=lambda p: f"PDF written: {p}" if p else "no report written")
    decision = decision.model_copy(update={"report_path": path})
    if decision.final_outcome is not None:  # an audit waiting for its reviewer is not a precedent yet
        rec.call("case_store.add", case_store.add, app, decision, run_id, score.model_version,
                 show={"run": run_id}, summary=lambda _: f"case stored ({case_store.count()} in memory)")
    return decision, rec.calls
