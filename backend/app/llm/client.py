"""Single entry point for LLM calls. Owner: Imane (task I4).

Agents never import a provider SDK directly. With LLM_PROVIDER=none the
function returns the fallback text, which keeps tests and the demo
skeleton free of network calls.

TODO: implement providers (gemini, groq, ollama), retries, rate limiting,
response caching and structured output parsing.
"""
from __future__ import annotations

from app import config


def complete(prompt: str, fallback: str = "") -> str:
    if config.LLM_PROVIDER == "none":
        return fallback
    raise NotImplementedError(f"LLM provider not implemented: {config.LLM_PROVIDER}")
