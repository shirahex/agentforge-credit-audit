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
    up = [f for f in score.top_factors if f.contribution > 0][:2]
    answers.append({"explanation": f"The file is refused. The risk is raised by {up[0].label.lower()} ({up[0].value_label}) "
                                   f"and by {up[1].label.lower()} ({up[1].value_label}).",
                    "raises_risk": [f.feature for f in up]})
    out = modele_scoring.run(state)
    assert out["mode"] == "llm" and "refused" in out["explanation"]


def test_scoring_explanation_with_invented_number_is_rejected_then_fallback(scripted_llm):
    answers, seen = scripted_llm
    bad = {"explanation": "The applicant has a 93% chance of default because of a salary of 1200 DM.",
           "raises_risk": ["checking_status"]}
    answers.extend([bad, bad])
    out = modele_scoring.run({"application": sample("terms")})
    assert out["mode"] == "rules"
    assert "rejected" in seen[1], "the second call must carry the guard's objection"


def test_scoring_explanation_citing_unknown_factor_is_rejected(scripted_llm):
    answers, _ = scripted_llm
    answers.extend([{"explanation": "Refused because of the applicant's nationality and shoe size.",
                     "raises_risk": ["shoe_size"]}] * 2)
    assert modele_scoring.run({"application": sample("terms")})["mode"] == "rules"


def test_generator_follows_a_valid_llm_plan(scripted_llm):
    answers, seen = scripted_llm
    state = {"application": sample("second_attempt")}
    state |= modele_scoring.run(state)
    answers.append({"features": ["credit_amount", "duration_months", "other_debtors", "savings"], "max_changes": 3,
                    "widen": False, "rationale": "Loan terms first, and savings because they raise the risk."})
    out = generateur_contrefactuels.run(state)
    assert out["mode"] == "llm"
    touched = {c.feature for cf in out["counterfactuals"] if cf.source == "exhaustive" for c in cf.changes}
    assert touched <= {"credit_amount", "duration_months", "other_debtors", "savings"}
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


def test_scoring_explanation_with_swapped_direction_is_rejected(scripted_llm):
    answers, _ = scripted_llm
    state = {"application": sample("terms")}
    score = modele_scoring.run(state)["score"]
    riser = next(f for f in score.top_factors if f.contribution > 0)
    answers.extend([{"explanation": f"The file is refused although {riser.label.lower()} lowers the risk for this applicant.",
                     "lowers_risk": [riser.feature]}] * 2)
    assert modele_scoring.run(state)["mode"] == "rules"


def test_generator_refuses_a_first_plan_without_the_guarantor(scripted_llm):
    answers, seen = scripted_llm
    state = {"application": sample("terms")}
    state |= modele_scoring.run(state)
    plan = {"features": ["credit_amount", "duration_months"], "max_changes": 2, "widen": False,
            "rationale": "Reduce the amount and the duration of the loan."}
    answers.extend([plan, plan])
    out = generateur_contrefactuels.run(state)
    assert out["mode"] == "rules" and "other_debtors" in seen[1]


def test_generator_refuses_a_later_plan_that_adds_nothing(scripted_llm):
    answers, _ = scripted_llm
    state = {"application": sample("second_attempt")}
    state |= modele_scoring.run(state)
    state |= generateur_contrefactuels.run(state)  # attempt 1 on rules: loan terms
    again = {"features": ["credit_amount", "duration_months"], "max_changes": 1, "widen": False,
             "rationale": "Reduce the amount and the duration a little."}
    answers.extend([again, again])
    out = generateur_contrefactuels.run(state)
    assert out["mode"] == "rules"
    assert any(BY in out["cf_plans"][-1][0] for BY in ("savings", "checking_status"))


def test_vague_explanation_is_rejected(scripted_llm):
    answers, _ = scripted_llm
    state = {"application": sample("terms")}
    score = modele_scoring.run(state)["score"]
    vague = {"explanation": "The applicant was refused. The model identified factors that raised the risk and others that lowered it.",
             "raises_risk": [f.feature for f in score.top_factors if f.contribution > 0][:2]}
    answers.extend([vague, vague])
    assert modele_scoring.run(state)["mode"] == "rules"


class _Resp:
    def __init__(self, status=200, content="", text="", headers=None):
        self.status_code, self.text, self.headers, self._content = status, text, headers or {}, content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}], "usage": {"prompt_tokens": 12, "completion_tokens": 3}}


def test_client_parses_provider_answer(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, body=json, headers=headers)
        return _Resp(content='```json\n{"note": "ok"}\n```')

    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(client.httpx, "post", fake_post)
    assert client.ask_json("system", "user") == {"note": "ok"}
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["reasoning_effort"] == "low"  # default Groq model is a reasoning model


def test_client_returns_none_on_http_error(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(client.httpx, "post", lambda *a, **k: _Resp(status=401, text="invalid key"))
    assert client.ask_json("system", "user") is None
    assert "401" in client.USAGE.last_error


def test_client_retries_without_json_mode_when_the_provider_rejects_it(monkeypatch):
    bodies = []

    def fake_post(url, json=None, headers=None, timeout=None):
        bodies.append(dict(json))
        if "response_format" in json:
            return _Resp(status=400, text='{"error": {"code": "json_validate_failed"}}')
        return _Resp(content='Here it is: {"note": "ok"}')

    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(client.httpx, "post", fake_post)
    assert client.ask_json("system", "user") == {"note": "ok"}
    assert len(bodies) == 2 and "response_format" not in bodies[1]


def test_rate_limited_provider_is_paused_and_the_fallback_answers(monkeypatch):
    urls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        urls.append(url)
        if "groq" in url:
            return _Resp(status=429, text="rate limit", headers={"retry-after": "120"})
        return _Resp(content='{"note": "from the local model"}')

    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "LLM_FALLBACK_PROVIDER", "ollama")
    monkeypatch.setattr(client.httpx, "post", fake_post)
    assert client.ask_json("system", "first") == {"note": "from the local model"}
    assert client.ask_json("system", "second") == {"note": "from the local model"}
    assert sum("groq" in u for u in urls) == 1, "a paused provider must not be called again"
    assert client.describe()["paused_seconds"]["groq"] > 60


def test_answers_are_cached_on_disk(monkeypatch, tmp_path):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(url)
        return _Resp(content='{"note": "ok"}')

    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(config, "LLM_CACHE_FILE", str(tmp_path / "cache.json"))
    monkeypatch.setattr(client.httpx, "post", fake_post)
    assert client.ask_json("system", "same question") == {"note": "ok"}
    client._cache.clear()
    monkeypatch.setattr(client, "_cache_loaded_from", None)
    assert client.ask_json("system", "same question") == {"note": "ok"}
    assert len(calls) == 1 and (tmp_path / "cache.json").exists()
