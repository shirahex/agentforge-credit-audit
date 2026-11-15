"""Single entry point for LLM calls.

Every supported provider exposes the OpenAI chat-completions format, so one
HTTP client covers them all:

    groq     https://api.groq.com/openai/v1
    gemini   https://generativelanguage.googleapis.com/v1beta/openai
    ollama   http://localhost:11434/v1          (local, no key)
    openai_compatible   any other server, set LLM_BASE_URL

Resilience, in order:
  1. answers are cached on disk, so a file audited once costs no tokens again;
  2. a provider that answers 429 (rate limit) is retried after a short
     wait, or put aside until its limit resets when the wait is long;
  3. the fallback provider (LLM_FALLBACK_PROVIDER, typically a local Ollama
     model) takes over while the primary is unavailable;
  4. when nothing answers, `ask_json` returns None and the calling agent
     uses its deterministic rules. An audit never fails because of the LLM.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app import config

_DEFAULTS = {
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.8-flash"),
    "ollama": ("http://localhost:11434/v1", "llama3"),
    "openai_compatible": ("", ""),
}
MAX_SHORT_WAIT_SECONDS = 6.0


@dataclass
class Provider:
    name: str
    base: str
    model: str
    key: str = ""


@dataclass
class Usage:
    calls: int = 0
    cached: int = 0
    failures: int = 0
    rate_limited: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    last_error: str = ""
    by_model: dict = field(default_factory=dict)


USAGE = Usage()
_cache: dict[str, dict] = {}
_cache_loaded_from: str | None = None
_cooling: dict[str, float] = {}  # provider name -> time (monotonic) when it may be used again
_lock = threading.Lock()
_last_call = 0.0


def _provider(name: str, model: str, base: str, key: str) -> Provider | None:
    if name not in _DEFAULTS:
        return None
    default_base, default_model = _DEFAULTS[name]
    p = Provider(name, (base or default_base).rstrip("/"), model or default_model, key)
    return p if p.base and p.model else None


def chain() -> list[Provider]:
    """Providers to try, in order: the primary, then the fallback."""
    out = []
    primary = _provider(config.LLM_PROVIDER, config.LLM_MODEL, config.LLM_BASE_URL, config.LLM_API_KEY)
    if primary:
        out.append(primary)
    fallback = _provider(config.LLM_FALLBACK_PROVIDER, config.LLM_FALLBACK_MODEL, config.LLM_FALLBACK_BASE_URL,
                         config.LLM_FALLBACK_API_KEY)
    if fallback and (not primary or (fallback.name, fallback.model) != (primary.name, primary.model)):
        out.append(fallback)
    return out


def _endpoint() -> tuple[str, str]:
    """Base URL and model of the primary provider (kept for the evaluation scripts)."""
    providers = chain()
    return (providers[0].base, providers[0].model) if providers else ("", "")


def enabled() -> bool:
    return bool(chain())


def describe() -> dict:
    providers = chain()
    now = time.monotonic()
    return {
        "provider": providers[0].name if providers else "none",
        "model": providers[0].model if providers else "",
        "fallback": f"{providers[1].name}: {providers[1].model}" if len(providers) > 1 else "",
        "enabled": bool(providers),
        "calls": USAGE.calls, "failures": USAGE.failures, "cached": USAGE.cached,
        "rate_limited": USAGE.rate_limited, "by_model": dict(USAGE.by_model),
        "paused_seconds": {n: round(t - now) for n, t in _cooling.items() if t > now},
        "prompt_tokens": USAGE.prompt_tokens, "completion_tokens": USAGE.completion_tokens,
        "last_error": USAGE.last_error,
    }


# --------------------------------------------------------------------------- cache
def _load_cache() -> None:
    global _cache_loaded_from
    path = config.LLM_CACHE_FILE
    if _cache_loaded_from == path:
        return
    _cache_loaded_from = path
    if path and Path(path).exists():
        try:
            _cache.update(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass


def _store(key: str, data: dict) -> None:
    _cache[key] = data
    if config.LLM_CACHE_FILE:
        try:
            Path(config.LLM_CACHE_FILE).write_text(json.dumps(_cache), encoding="utf-8")
        except OSError:
            pass


# --------------------------------------------------------------------------- one provider
def _extract_json(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _post(p: Provider, body: dict) -> httpx.Response | None:
    global _last_call
    headers = {"Content-Type": "application/json"}
    if p.key:
        headers["Authorization"] = f"Bearer {p.key}"
    with _lock:  # one call at a time keeps free-tier rate limits under control
        wait = config.LLM_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        started = time.monotonic()
        try:
            for attempt in range(2):  # one immediate retry: a dropped connection is usually transient
                try:
                    return httpx.post(f"{p.base}/chat/completions", json=body, headers=headers,
                                      timeout=config.LLM_TIMEOUT_SECONDS)
                except httpx.HTTPError as exc:
                    USAGE.last_error = f"{p.name}: {type(exc).__name__}: {exc}"
            USAGE.failures += 1
            _cooling[p.name] = time.monotonic() + 15  # unreachable: leave it alone for a moment
            return None
        finally:
            _last_call = time.monotonic()
            USAGE.seconds += _last_call - started


def _ask(p: Provider, system: str, user: str, temperature: float, max_tokens: int) -> dict | None:
    body = {
        "model": p.model, "temperature": temperature, "max_tokens": int(max_tokens * config.LLM_MAX_TOKENS_SCALE),
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if p.name == "groq" and "gpt-oss" in p.model:
        # Reasoning models: keep the hidden reasoning short and out of the answer.
        body.update(reasoning_effort="low", include_reasoning=False, max_tokens=max(body["max_tokens"], 1500))
    body.update(config.LLM_EXTRA_BODY)  # explicit settings win over the defaults above

    for attempt in range(3):
        resp = _post(p, body)
        if resp is None:
            return None
        if resp.status_code == 429:
            USAGE.rate_limited += 1
            try:
                retry_after = float(resp.headers.get("retry-after", "20"))
            except ValueError:
                retry_after = 20.0
            if retry_after <= MAX_SHORT_WAIT_SECONDS and attempt < 2:
                time.sleep(retry_after + 0.2)
                continue
            _cooling[p.name] = time.monotonic() + min(retry_after, 900)
            USAGE.last_error = f"{p.name}: rate limit reached, paused for {retry_after:.0f} s"
            return None
        if resp.status_code == 400 and "json_validate_failed" in resp.text and "response_format" in body:
            body.pop("response_format")  # the strict JSON mode refused the answer: parse it ourselves
            continue
        if resp.status_code in (500, 502, 503, 529) and attempt < 2:
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code != 200:
            USAGE.failures += 1
            USAGE.last_error = f"{p.name}: HTTP {resp.status_code}: {resp.text[:200]}"
            return None
        payload = resp.json()
        usage = payload.get("usage") or {}
        USAGE.calls += 1
        USAGE.by_model[p.model] = USAGE.by_model.get(p.model, 0) + 1
        USAGE.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        USAGE.completion_tokens += int(usage.get("completion_tokens") or 0)
        try:
            text = payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            text = ""
        data = _extract_json(text)
        if data is None:
            USAGE.failures += 1
            USAGE.last_error = f"{p.name}: answer was not a JSON object"
        return data
    return None


def ask_json(system: str, user: str, temperature: float = 0.0, max_tokens: int = 500) -> dict | None:
    """One JSON-object answer, or None when no provider can give a usable one."""
    providers = chain()
    if not providers:
        return None
    _load_cache()
    key = hashlib.sha256(f"{providers[0].model}|{temperature}|{system}|{user}".encode()).hexdigest()
    if key in _cache:
        USAGE.cached += 1
        return _cache[key]
    for p in providers:
        if _cooling.get(p.name, 0) > time.monotonic():
            continue
        data = _ask(p, system, user, temperature, max_tokens)
        if data is not None:
            if p is providers[0]:  # a fallback answer must not be replayed as the primary model's
                _store(key, data)
            return data
    return None
