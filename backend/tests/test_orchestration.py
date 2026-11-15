"""Durable orchestration (task I3): checkpoints, human interrupt, case store, JSONL trace."""
import json
import uuid

import pytest

from app import config
from app.agents import generateur_contrefactuels
from app.graph import trace
from app.graph.build import build_graph, graph
from app.graph.runner import AuditService
from app.memory import case_store, run_store
from app.memory.checkpointer import sqlite_checkpointer
from app.samples import sample
from app.schemas import AuditDecision, LoanApplication, ScoreResult

config.STEP_DELAY_SECONDS = 0


@pytest.fixture
def service():
    return AuditService()


def test_plain_graph_has_no_side_effect():
    before = case_store.count()
    out = graph.invoke({"application": sample("terms")})
    assert case_store.count() == before and out["decision"].report_path is None
    assert [s["node"] for s in out["trail"]] == ["analyste_dossier", "modele_scoring", "generateur_contrefactuels",
                                                 "verificateur_equite", "arbitre_redacteur"]


def test_escalated_run_waits_for_the_reviewer_and_resumes(service):
    run_id = service.start(sample("no_path"), background=False)
    run = run_store.get(run_id)
    assert run["status"] == run_store.AWAITING_REVIEW and service.awaiting_review(run_id)
    assert run["decision"]["escalated"] and run["decision"]["letter_status"] == "draft"
    assert run["decision"]["final_outcome"] is None
    steps_before = run_store.event_count(run_id)
    cases_before = case_store.count()

    service.review(run_id, {"outcome": "refused", "reviewer": "I. Alouani", "comment": "No realistic path."})
    run = run_store.get(run_id)
    assert run["status"] == run_store.FINISHED and not service.awaiting_review(run_id)
    d = run["decision"]
    assert d["final_outcome"] == "refused" and d["letter_status"] == "final" and d["review"]["reviewer"] == "I. Alouani"
    assert run["review"]["at"]
    events = run_store.events(run_id)
    assert len(events) == steps_before + 1, "the review adds one step and replays none"
    assert events[-1]["node"] == "arbitre_redacteur" and events[-1]["status"] == "finished"
    assert "I. Alouani" in events[-1]["message"]
    assert case_store.count() == cases_before + 1, "the case is stored once a person has decided"


def test_reviewer_can_overturn_the_model_and_the_letter_follows(service):
    run_id = service.start(sample("sensitive"), background=False)
    assert "ne pouvons pas donner une suite favorable" in run_store.get(run_id)["decision"]["letter"]
    service.review(run_id, {"outcome": "approved", "reviewer": "M. Daouki", "comment": "Nationality must not decide."})
    d = run_store.get(run_id)["decision"]
    assert d["decision"] == "refused" and d["final_outcome"] == "approved"
    assert "votre demande est acceptée" in d["letter"] and "examen individuel" in d["letter"]
    assert "against the model's decision" in d["summary"]


def test_waiting_run_survives_a_restart(service):
    """A new service on the same files stands for a restarted backend: other objects, other connections."""
    run_id = service.start(sample("borderline"), background=False)
    restarted = AuditService()
    assert restarted is not service and restarted.awaiting_review(run_id)
    state = restarted.state(run_id)
    assert isinstance(state["application"], LoanApplication) and isinstance(state["score"], ScoreResult)
    assert isinstance(state["decision"], AuditDecision)
    restarted.review(run_id, {"outcome": "approved", "reviewer": "Reviewer", "comment": ""})
    assert run_store.get(run_id)["status"] == run_store.FINISHED


def test_run_killed_in_the_middle_is_resumed_from_its_checkpoint(monkeypatch):
    """The generator crashes once. After the restart, finished steps are not run again."""
    calls = {"scoring": 0, "generator": 0}
    real_generator = generateur_contrefactuels.run
    from app.agents import modele_scoring
    real_scoring = modele_scoring.run

    def counting_scoring(state):
        calls["scoring"] += 1
        return real_scoring(state)

    def crashing_generator(state):
        calls["generator"] += 1
        if calls["generator"] == 1:
            raise RuntimeError("power cut")
        return real_generator(state)

    monkeypatch.setattr(modele_scoring, "run", counting_scoring)
    monkeypatch.setattr(generateur_contrefactuels, "run", crashing_generator)
    first = AuditService()
    run_id = uuid.uuid4().hex[:12]
    run_store.create(run_id, sample("second_attempt"))
    with pytest.raises(RuntimeError):  # what the process would have died on
        for _ in first.graph.stream({"application": sample("second_attempt"), "run_id": run_id},
                                    first._config(run_id), stream_mode="updates"):
            pass
    assert run_store.get(run_id)["status"] == run_store.RUNNING and run_store.event_count(run_id) == 0

    restarted = AuditService()
    assert restarted.recover(background=False) == [run_id]
    run = run_store.get(run_id)
    assert run["status"] == run_store.FINISHED and run["decision"]["attempts"] == 2
    assert calls["scoring"] == 1, "the scoring step was checkpointed and must not run twice"
    nodes = [e["node"] for e in run_store.events(run_id)]
    assert nodes == ["analyste_dossier", "modele_scoring", "generateur_contrefactuels", "verificateur_equite",
                     "generateur_contrefactuels", "verificateur_equite", "arbitre_redacteur"]
    assert len({tuple(map(str, p)) for p in restarted.state(run_id)["cf_plans"]}) == 2


def test_plans_read_back_from_a_checkpoint_still_block_a_replay():
    """Checkpoints turn tuples into lists: the graph restores the keys the generator compares."""
    g = build_graph(checkpointer=sqlite_checkpointer(), human_review=True)
    cfg = {"configurable": {"thread_id": uuid.uuid4().hex}}
    out = g.invoke({"application": sample("no_path")}, cfg)
    assert out["decision"].attempts == 3
    assert len({json.dumps(p) for p in g.get_state(cfg).values["cf_plans"]}) == 3


def test_second_similar_file_retrieves_the_first_one(service):
    case_store.clear()
    first = sample("terms")
    run_a = service.start(first, background=False)
    assert case_store.count() == 1
    assert run_store.events(run_a)[0]["payload"]["analysis"]["precedents"] == []

    similar = first.model_copy(update={"applicant_id": "NEW-0001", "credit_amount": first.credit_amount + 150})
    run_b = service.start(similar, background=False)
    analyst = run_store.events(run_b)[0]
    precedents = analyst["payload"]["analysis"]["precedents"]
    assert precedents and precedents[0]["run_id"] == run_a and precedents[0]["applicant_id"] == first.applicant_id
    assert precedents[0]["similarity"] > 0.97
    assert first.applicant_id in analyst["payload"]["analysis"]["note"], "the Analyste-Dossier cites the past audit"
    assert any(t["name"] == "past_audits" and first.applicant_id in t["result"] for t in analyst["tool_calls"])
    assert run_store.get(run_b)["decision"]["precedents"][0]["run_id"] == run_a


def test_similarity_ignores_protected_attributes_and_unrelated_files():
    case_store.clear()
    app = sample("approved")
    decision = AuditDecision(applicant_id=app.applicant_id, decision="approved", default_probability=0.05,
                             final_outcome="approved")
    case_store.add(app, decision, "run-a")
    twin = app.model_copy(update={"sex": "female" if app.sex == "male" else "male", "age": 70, "foreign_worker": False})
    assert case_store.search(twin)[0].similarity == 1.0
    assert case_store.search(sample("no_path")) == [], "an unrelated file is not a precedent"
    assert case_store.search(app, exclude_run="run-a") == []


def test_near_identical_file_with_the_opposite_outcome_goes_to_a_person(service):
    case_store.clear()
    app = sample("terms")  # refused by the model, closed by the agents
    past = AuditDecision(applicant_id="GC-PAST", decision="refused", default_probability=0.39,
                         final_outcome="approved", review={"outcome": "approved", "reviewer": "R"}, escalated=True)
    case_store.add(app.model_copy(update={"applicant_id": "GC-PAST"}), past, "run-past")
    run_id = service.start(app, background=False)
    d = run_store.get(run_id)["decision"]
    assert d["escalated"] and "near-identical past file (GC-PAST)" in d["escalation_reason"]
    assert d["precedent_conflict"]
    case_store.clear()


def test_trace_records_every_step_and_tool_call(service):
    run_id = service.start(sample("second_attempt"), background=False)
    lines = trace.trace_file(run_id).read_text(encoding="utf-8").splitlines()
    steps = [json.loads(line) for line in lines]
    assert [s["seq"] for s in steps] == list(range(7)) and steps == trace.read(run_id)
    for s in steps:
        assert {"run_id", "ts", "node", "agent", "status", "mode", "message", "duration_ms", "tool_calls", "llm",
                "guards", "payload"} <= set(s)
        assert s["run_id"] == run_id and all({"name", "arguments", "result", "duration_ms"} <= set(t) for t in s["tool_calls"])
    assert steps[3]["status"] == "rejected"
    names = [t["name"] for s in steps for t in s["tool_calls"]]
    assert {"validate_application", "score_applicant", "shap_explain", "generate_counterfactuals", "closest_miss",
            "sensitive_flip_test", "plausibility_score", "render_report", "case_store.add"} <= set(names)
    totals = trace.summarise(steps)
    assert totals["steps"] == 7 and totals["tool_calls"] == len(names) and totals["llm_calls"] == 0


def test_trace_counts_guard_rejections_and_fallbacks(monkeypatch):
    from app.llm import client

    from app.tools.scoring import score_applicant

    factors = score_applicant(sample("approved")).top_factors
    up = next(f for f in factors if f.contribution > 0)
    down = next(f for f in factors if f.contribution < 0)
    # Passes the direction and naming checks of the Modèle-Scoring, so that only the number guard objects.
    bad = {"explanation": f"The applicant has a 93% chance of default with a salary of 1200 DM: {up.label.lower()} "
                          f"({up.value_label}) raises the risk and {down.label.lower()} ({down.value_label}) lowers it.",
           "raises_risk": [up.feature], "lowers_risk": [down.feature]}
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(client, "ask_json", lambda system, user, **_: bad if "scoring analyst" in system else None)
    out = graph.invoke({"application": sample("approved")})
    scoring_step = out["trail"][1]
    assert scoring_step["mode"] == "rules" and scoring_step["llm_asked"]
    assert [g["guard"] for g in scoring_step["guards"]] == ["numbers", "numbers"]
    totals = trace.summarise(out["trail"])
    assert totals["rejected_numbers"] == 2 and totals["fallback_steps"] == totals["llm_steps"] == 4
    assert totals["no_answer"] == 3


def test_ablation_graph_has_no_rejection_loop():
    out = build_graph(verification_loop=False).invoke({"application": sample("second_attempt")})
    d = out["decision"]
    assert d.attempts == 1 and d.counterfactuals == [] and d.escalated
