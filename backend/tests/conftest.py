"""Test isolation.

* Durable state (checkpoints, runs, cases, traces, reports) goes to a temporary folder.
* Tests never call a real language model: backend/.env may point the agents at Groq or
  Ollama, and the tests must not depend on that model's answers. A test that needs an LLM
  replaces it with a scripted one (fixture `scripted_llm`).
"""
import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="agentforge-tests-")
os.environ.setdefault("LLM_PROVIDER", "none")

import pytest  # noqa: E402

from app import config  # noqa: E402
from app.llm import client  # noqa: E402


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
