"""Vérificateur-Équité and Arbitre et Rédacteur (task I2), with rules and with a scripted LLM."""
import pytest

from app import config
from app.agents import arbitre_redacteur, generateur_contrefactuels, modele_scoring, verificateur_equite
from app.agents.arbitre_redacteur import letter_facts, template_letter, write_letter
from app.agents.base import invented_numbers
from app.domain import fr
from app.graph.build import graph
from app.llm import client
from app.samples import load_samples, sample
from app.schemas import Counterfactual, FeatureChange
from app.tools import scoring

TAGS = [s["tag"] for s in load_samples()]


@pytest.fixture
def scripted_llm(monkeypatch):
    answers: list[dict] = []
    seen: list[str] = []

    def fake_ask(system, user, **_):
        seen.append(user)
        return answers.pop(0) if answers else None

    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(client, "ask_json", fake_ask)
    return answers, seen


def state_before_audit(tag: str) -> dict:
    state = {"application": sample(tag)}
    state |= modele_scoring.run(state)
    if state["score"].decision == "refused":
        state |= generateur_contrefactuels.run(state)
    return state


# ----------------------------------------------------------------- Vérificateur-Équité
def test_auditor_records_every_tool_and_keeps_only_verified_proposals():
    out = verificateur_equite.run(state_before_audit("terms"))
    names = [t.name for t in out["tool_calls"]]
    assert names == ["sensitive_flip_test", "group_fairness_metrics", "group_context", "check_actionability",
                     "rescore_candidates", "plausibility_score"]
    assert out["mode"] == "rules" and out["status"] == "completed"
    v = out["fairness"]
    assert v.passed and v.candidates_kept == len(out["counterfactuals"]) > 0
    assert {"flip_delta_sex", "dp_diff_sex", "eo_diff_sex", "dp_diff_age_group"} <= set(v.metrics)
    for cf in out["counterfactuals"]:
        assert cf.valid and cf.actionable and cf.robust and cf.plausibility and cf.plausibility.plausible


def test_auditor_does_not_trust_the_flags_of_a_proposal():
    """A proposal that claims to be valid but does not flip the decision is caught by the re-scoring."""
    state = state_before_audit("no_path")
    app = state["application"]
    lie = Counterfactual(
        changes=[FeatureChange(feature="duration_months", from_value=app.duration_months,
                               to_value=app.duration_months - 6)],
        new_probability=0.05, valid=True, actionable=True, robust=True, statement="Repay a little faster.")
    out = verificateur_equite.run({**state, "counterfactuals": [lie]})
    assert out["counterfactuals"] == [] and out["status"] == "rejected"
    assert any("above the threshold" in r for r in out["fairness"].reasons)


def test_auditor_rejects_a_change_of_protected_attribute_and_an_unrealistic_file():
    state = state_before_audit("terms")
    app = state["application"]
    protected = Counterfactual(changes=[FeatureChange(feature="sex", from_value=app.sex, to_value="female")],
                               new_probability=0.01, valid=True, actionable=True, robust=True)
    out = verificateur_equite.run({**state, "counterfactuals": [protected]})
    assert out["counterfactuals"] == [] and any("protected attribute" in r for r in out["fairness"].reasons)

    def far_away(app_, changes):
        r = verificateur_equite_plausibility(app_, changes)
        return r.model_copy(update={"plausible": False, "score": 0.0})

    verificateur_equite_plausibility = verificateur_equite.plausibility_score
    verificateur_equite.plausibility_score = far_away
    try:
        out = verificateur_equite.run(state)
    finally:
        verificateur_equite.plausibility_score = verificateur_equite_plausibility
    assert out["counterfactuals"] == [] and any("unrealistic" in r for r in out["fairness"].reasons)


def test_objections_are_short_and_tell_the_generator_what_to_change():
    state = state_before_audit("second_attempt")
    out = verificateur_equite.run(state)
    reasons = out["fairness"].reasons
    assert out["status"] == "rejected" and reasons
    assert all(len(r) <= 120 for r in reasons)
    assert any(r.startswith("next plan: ") and "financial situation" in r for r in reasons)
    # The generator receives them and must follow a different plan.
    second = generateur_contrefactuels.run({**state, **out})
    assert second["attempts"] == 2 and len(set(second["cf_plans"])) == 2


def test_auditor_verdict_written_by_the_llm_is_accepted(scripted_llm):
    answers, seen = scripted_llm
    state = state_before_audit("terms")   # scripted LLM empty so far: rules for the first agents
    answers.append({"verdict": "The decision does not depend on a sensitive attribute. Two proposals survive every "
                               "check; the others cut the request by more than the rules allow.", "outcome": "accepted"})
    out = verificateur_equite.run(state)
    assert out["mode"] == "llm" and "survive" in out["fairness"].verdict
    assert '"proposals_kept"' in seen[-1]


def test_auditor_verdict_that_contradicts_the_tools_falls_back_to_rules(scripted_llm):
    answers, seen = scripted_llm
    state = state_before_audit("no_path")
    wrong = {"verdict": "Everything is fine, the proposals are all valid and the file can be approved now.",
             "outcome": "accepted"}
    answers.extend([wrong, wrong])
    out = verificateur_equite.run(state)
    assert out["mode"] == "rules" and out["status"] == "rejected"
    assert "decided by the tools" in seen[-1]


def test_auditor_verdict_with_an_invented_number_is_rejected(scripted_llm):
    answers, _ = scripted_llm
    state = state_before_audit("terms")
    bad = {"verdict": "The decision is stable. 17 proposals were checked and 93% of them are realistic changes.",
           "outcome": "accepted"}
    answers.extend([bad, bad])
    assert verificateur_equite.run(state)["mode"] == "rules"


# ----------------------------------------------------------------- Arbitre et Rédacteur
def test_french_wording_covers_every_attribute_and_category():
    assert fr.check() == []
    assert fr.amount(12500) == "12 500 DM"


@pytest.mark.parametrize("tag", TAGS)
def test_letter_of_each_demo_file_quotes_no_number_absent_from_the_tool_outputs(tag):
    out = graph.invoke({"application": sample(tag)})
    d, app, score = out["decision"], out["application"], out["score"]
    facts = letter_facts(app, score, d.counterfactuals if d.decision == "refused" else [], d.decision, None, d.escalated)
    assert d.letter == template_letter(facts)
    assert invented_numbers(d.letter, facts) == []
    assert app.applicant_id in d.letter and d.letter.startswith("Objet : ")
    assert ("votre demande est acceptée" in d.letter) == (d.decision == "approved")
    low = d.letter.lower()
    assert not any(word in low for word in (" sexe", " âge", "nationalité", "étranger"))
    assert d.letter_status == ("draft" if d.escalated else "final")


def test_letter_lists_every_verified_way_with_its_risk():
    d = graph.invoke({"application": sample("terms")})["decision"]
    for i, cf in enumerate(sorted(d.counterfactuals, key=lambda c: c.cost), 1):
        assert f"{i}. " in d.letter and f"{round(cf.new_probability * 100)} %" in d.letter


def test_letter_written_by_the_llm_is_used_when_it_passes_the_guards(scripted_llm):
    answers, seen = scripted_llm
    state = state_before_audit("approved")
    state |= verificateur_equite.run(state)
    facts = letter_facts(state["application"], state["score"], [], "approved", None, False)
    good = (f"Objet : votre demande de crédit, dossier {facts['dossier']}\n\nMadame, Monsieur,\n\n"
            f"Nous avons étudié votre demande de crédit de {facts['demande']['montant']} sur {facts['demande']['duree']}. "
            f"Nous avons le plaisir de vous informer que votre demande est acceptée : le risque de défaut estimé est de "
            f"{facts['risque_estime']}, en dessous de notre seuil de {facts['seuil']}.\n\n"
            "Un conseiller prendra contact avec vous pour finaliser votre contrat.\n\n"
            "Nous vous prions d'agréer, Madame, Monsieur, l'expression de nos salutations distinguées.\n\nLe service crédit")
    answers.append({"letter": good, "decision": "approved"})
    out = arbitre_redacteur.run(state)
    assert out["mode"] == "llm" and out["decision"].letter == good
    assert '"decision_finale": "approved"' in seen[-1]


def test_llm_letter_with_an_invented_number_or_a_protected_attribute_is_replaced_by_the_template(scripted_llm):
    answers, seen = scripted_llm
    state = state_before_audit("terms")
    state |= verificateur_equite.run(state)
    app = state["application"]
    kept = letter_facts(app, state["score"], state["counterfactuals"], "refused", None, False)["pistes"]
    base = (f"Objet : votre demande de crédit, dossier {app.applicant_id}\n\nMadame, Monsieur,\n\nVotre demande est "
            f"refusée. Une piste vérifiée ramène le risque estimé à {kept[0]['risque_apres']}. "
            + "Nous restons à votre disposition pour toute précision. " * 4)
    invented = {"letter": base + "Votre taux d'endettement atteint 47 % et votre score est de 512.", "decision": "refused"}
    protected = {"letter": base + "Cette décision tient compte de votre âge.", "decision": "refused"}
    answers.extend([invented, protected])
    out = arbitre_redacteur.run(state)
    assert out["mode"] == "rules"
    assert "numbers that are not in the facts" in seen[-1]
    facts = letter_facts(app, state["score"], out["decision"].counterfactuals, "refused", None, False)
    assert invented_numbers(out["decision"].letter, facts) == []


def test_llm_letter_announcing_the_wrong_decision_is_refused(scripted_llm):
    answers, _ = scripted_llm
    state = state_before_audit("terms")
    state |= verificateur_equite.run(state)
    lie = {"letter": "Objet : dossier " + state["application"].applicant_id + ". Madame, Monsieur, " + "bonne nouvelle ! " * 30,
           "decision": "approved"}
    answers.extend([lie, lie])
    letter, mode, _ = write_letter(state["application"], state["score"], state["counterfactuals"], "refused")
    assert mode == "rules" and "ne pouvons pas donner une suite favorable" in letter


def test_escalation_rules_in_order():
    rule = arbitre_redacteur.escalation_reason
    score = scoring.score_applicant(sample("terms"))
    assert rule(score, True, [object()], 1, None) is None
    assert "sensitive" in rule(score, False, [object()], 1, None)
    assert "no verified way" in rule(score, True, [], 3, None)
    assert "near-identical" in rule(score, True, [object()], 1, "a near-identical past file (GC-1) was finally approved")
    edge = score.model_copy(update={"default_probability": score.threshold + 0.01})
    assert "borderline" in rule(edge, True, [object()], 1, None)


def test_arbitre_records_its_tools_and_keeps_the_letter_a_draft_when_escalated():
    out = graph.invoke({"application": sample("no_path")})
    step = out["trail"][-1]
    assert [t["name"] for t in step["tool_calls"]] == ["past_audits", "escalation_rules"]
    d = out["decision"]
    assert d.escalated and d.letter_status == "draft" and d.final_outcome is None
    assert "transmis à un conseiller" in d.letter
