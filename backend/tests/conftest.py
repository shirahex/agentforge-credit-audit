"""Tests never call a real language model.

backend/.env may point the agents at Ollama or a hosted provider. Without
this fixture the tests would then depend on that model's answers. Tests
that need an LLM replace it with a scripted one (see test_agents.py).
"""
import pytest

from app import config
from app.llm import client


@pytest.fixture(autouse=True)
def llm_disabled(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "none")
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(config, "LLM_BASE_URL", "")
    monkeypatch.setattr(config, "LLM_MODEL", "")
    monkeypatch.setattr(config, "LLM_FALLBACK_PROVIDER", "none")
    monkeypatch.setattr(config, "LLM_CACHE_FILE", "")
    monkeypatch.setattr(config, "STEP_DELAY_SECONDS", 0)
    client._cooling.clear()
    client._cache.clear()
