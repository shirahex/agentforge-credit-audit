"""Single entry point for LLM calls.

Every supported provider exposes the OpenAI chat-completions format, so one
HTTP client covers them all:

    gemini   https://generativelanguage.googleapis.com/v1beta/openai
    groq     https://api.groq.com/openai/v1
    ollama   http://localhost:11434/v1          (local, no key)
    openai_compatible   any other server, set LLM_BASE_URL

With LLM_PROVIDER=none, or when a call fails, `ask_json` returns None and
the calling agent falls back to its deterministic rules. An agent therefore
never blocks an audit because of the LLM.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field

import httpx

from app import config

_DEFAULTS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.8-flash"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "ollama": ("http://localhost:11434/v1", "llama3.2"),
    "openai_compatible": ("", ""),
}


@dataclass
class Usage:
    calls: int = 0
    cached: int = 0
    failures: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    last_error: str = ""
    history: list = field(default_factory=list)


USAGE = Usage()
_cache: dict[str, dict] = {}
_lock = threading.Lock()
_last_call = 0.0


def enabled() -> bool:
    return config.LLM_PROVIDER in _DEFAULTS


def describe() -> dict:
    base, model = _endpoint()
    return {"provider": config.LLM_PROVIDER, "model": model if enabled() else "", "enabled": enabled(),
            "calls": USAGE.calls, "failures": USAGE.failures, "cached": USAGE.cached,
            "prompt_tokens": USAGE.prompt_tokens, "completion_tokens": USAGE.completion_tokens,
            "last_error": USAGE.last_error}


def _endpoint() -> tuple[str, str]:
    base, model = _DEFAULTS.get(config.LLM_PROVIDER, ("", ""))
    return (config.LLM_BASE_URL or base).rstrip("/"), config.LLM_MODEL or model


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def ask_json(system: str, user: str, temperature: float = 0.2, max_tokens: int = 500) -> dict | None:
    """One JSON-object answer, or None when the LLM is disabled or unusable."""
    global _last_call
    if not enabled():
        return None
    base, model = _endpoint()
    if not base or not model:
        USAGE.last_error = "LLM_BASE_URL or LLM_MODEL missing"
        return None
    key = hashlib.sha256(f"{model}|{temperature}|{system}|{user}".encode()).hexdigest()
    if key in _cache:
        USAGE.cached += 1
        return _cache[key]

    body = {
        "model": model, "temperature": temperature, "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    headers = {"Content-Type": "application/json"}
    if config.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"

    for attempt in range(3):
        with _lock:  # one call at a time keeps free-tier rate limits under control
            wait = config.LLM_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            started = time.monotonic()
            try:
                resp = httpx.post(f"{base}/chat/completions", json=body, headers=headers,
                                  timeout=config.LLM_TIMEOUT_SECONDS)
            except httpx.HTTPError as exc:
                USAGE.failures += 1
                USAGE.last_error = f"{type(exc).__name__}: {exc}"
                return None
            finally:
                _last_call = time.monotonic()
        USAGE.seconds += time.monotonic() - started
        if resp.status_code in (429, 500, 502, 503, 529) and attempt < 2:
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code != 200:
            USAGE.failures += 1
            USAGE.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            return None
        payload = resp.json()
        usage = payload.get("usage") or {}
        USAGE.calls += 1
        USAGE.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        USAGE.completion_tokens += int(usage.get("completion_tokens") or 0)
        try:
            text = payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            text = ""
        data = _extract_json(text)
        if data is None:
            USAGE.failures += 1
            USAGE.last_error = "answer was not a JSON object"
            return None
        _cache[key] = data
        return data
    return None
