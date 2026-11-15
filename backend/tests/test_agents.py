"""Agents with a scripted LLM: accepted answers are used, bad answers are refused."""
import json

import pytest

from app import config
from app.agents import analyste_dossier, generateur_contrefactuels, modele_scoring
from app.agents.base import invented_numbers
from app.llm import client
from app.samples import sample


@pytest.fixture
def scripted_llm(monkeypatch):
    """Replaces the HTTP call; `answers` is consumed one JSON object per LLM call."""
    answers: list[dict] = []
    seen: list[str] = []

    def fake_ask(system, user, **_):
        seen.append(user)
        return answers.pop(0) if answers else None

    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(client, "ask_json", fake_ask)
    return answers, seen


def test_number_guard():
    facts = {"default_probability_percent": 39, "threshold": 0.26, "amount": 3500}
    assert invented_numbers("Risk of 39% against 26%, for 3,500 DM.", facts) == []
    assert invented_numbers("Risk of 45% for this file.", facts) == ["45"]


def test_agents_run_on_rules_without_llm():
    state = {"application": sample("terms")}
    for agent in (analyste_dossier, modele_scoring, generateur_contrefactuels):
        out = agent.run(state)
        assert out["mode"] == "rules" and out["reasoning"] and out["tool_calls"]
        state |= out


def test_scoring_explanation_accepted(scripted_llm):
    answers, _ = scripted_llm
    state = {"application": sample("terms")}
    score = modele_scoring.run(state)["score"]
    answers.append({"explanation": f"The file is refused. The {score.top_factors[0].label.lower()} raises the risk the most.",
                    "cited_features": [score.top_factors[0].feature]})
    out = modele_scoring.run(state)
    assert out["mode"] == "llm" and "refused" in out["explanation"]


def test_scoring_explanation_with_invented_number_is_rejected_then_fallback(scripted_llm):
    answers, seen = scripted_llm
    bad = {"explanation": "The applicant has a 93% chance of default because of a salary of 1200 DM.",
           "cited_features": ["checking_status"]}
    answers.extend([bad, bad])
    out = modele_scoring.run({"application": sample("terms")})
    assert out["mode"] == "rules"
    assert "rejected" in seen[1], "the second call must carry the guard's objection"


def test_scoring_explanation_citing_unknown_factor_is_rejected(scripted_llm):
    answers, _ = scripted_llm
    answers.extend([{"explanation": "Refused because of the applicant's nationality and shoe size.",
                     "cited_features": ["shoe_size"]}] * 2)
    assert modele_scoring.run({"application": sample("terms")})["mode"] == "rules"


def test_generator_follows_a_valid_llm_plan(scripted_llm):
    answers, seen = scripted_llm
    state = {"application": sample("second_attempt")}
    state |= modele_scoring.run(state)
    answers.append({"features": ["savings", "checking_status", "duration_months"], "max_changes": 3, "widen": False,
                    "rationale": "The account standing drives the risk, so the search targets it."})
    out = generateur_contrefactuels.run(state)
    assert out["mode"] == "llm"
    touched = {c.feature for cf in out["counterfactuals"] if cf.source == "exhaustive" for c in cf.changes}
    assert touched <= {"savings", "checking_status", "duration_months"}
    assert "permitted_values" in seen[-1]


def test_generator_refuses_a_plan_on_protected_attributes(scripted_llm):
    answers, _ = scripted_llm
    state = {"application": sample("second_attempt")}
    state |= modele_scoring.run(state)
    plan = {"features": ["age", "sex"], "max_changes": 2, "widen": False, "rationale": "Make the applicant older."}
    answers.extend([plan, plan])
    out = generateur_contrefactuels.run(state)
    assert out["mode"] == "rules"
    assert all(c.feature not in ("age", "sex") for cf in out["counterfactuals"] for c in cf.changes)


def test_client_parses_provider_answer(monkeypatch):
    class Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "```json\n" + json.dumps({"note": "ok"}) + "\n```"}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 3}}

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, body=json, headers=headers)
        return Resp()

    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(client.httpx, "post", fake_post)
    assert client.ask_json("system", "user-unique-1") == {"note": "ok"}
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_client_returns_none_on_http_error(monkeypatch):
    class Resp:
        status_code = 401
        text = "invalid key"

    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(client.httpx, "post", lambda *a, **k: Resp())
    assert client.ask_json("system", "user-unique-2") is None
    assert "401" in client.USAGE.last_error
