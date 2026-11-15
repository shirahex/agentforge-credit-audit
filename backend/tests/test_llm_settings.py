"""Request settings of the LLM client: answer budget factor and extra body fields."""
from app import config
from app.llm import client


def test_answer_budget_and_extra_fields_reach_the_request(monkeypatch):
    sent = {}

    class Resp:
        status_code, text = 200, ""

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}], "usage": {}}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(json)
        return Resp()

    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "LLM_MODEL", "")
    monkeypatch.setattr(config, "LLM_MAX_TOKENS_SCALE", 4.0)
    monkeypatch.setattr(config, "LLM_EXTRA_BODY", {"reasoning_effort": "low"})
    monkeypatch.setattr(client.httpx, "post", fake_post)
    assert client.ask_json("system", "user-settings-1", max_tokens=500) == {"ok": True}
    assert sent["max_tokens"] == 2000 and sent["reasoning_effort"] == "low"
    assert sent["model"] == "openai/gpt-oss-120b", "the retired Llama names are no longer the Groq default"
