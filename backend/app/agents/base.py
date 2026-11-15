"""Shared agent machinery: tool-call recording and guarded LLM answers.

An agent step always follows the same pattern:
  1. call deterministic tools through a Recorder (every call lands in the audit trail);
  2. ask the LLM for a decision or a wording, as a JSON object;
  3. validate the answer with guards (schema, allowed values, no invented number);
  4. on any failure, retry once with the guard's objection, then use the rule-based fallback.
"""
from __future__ import annotations

import json
import re
import time
from contextvars import ContextVar
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.llm import client
from app.schemas import ToolCall

def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def similarity_percent(similarity: float) -> int:
    """Whole percent, rounded down: only an identical file is shown as 100% similar."""
    return 100 if similarity >= 1 else min(99, int(similarity * 100))


_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*\.?\d*")

# Outcome of every LLM answer of the current agent step, read by the graph for the trace (task I3):
# which guard refused an answer, and whether the step ended on the LLM or on rules.
_GUARD_LOG: ContextVar[list[dict] | None] = ContextVar("guard_log", default=None)


def start_guard_log() -> list[dict]:
    """Starts recording guard outcomes for one agent step and returns the list they are written to."""
    log: list[dict] = []
    _GUARD_LOG.set(log)
    return log


def _note(guard: str, detail: str = "") -> None:
    log = _GUARD_LOG.get()
    if log is not None:
        log.append({"guard": guard, "accepted": guard == "accepted", "detail": detail[:200]})


class Recorder:
    def __init__(self) -> None:
        self.calls: list[ToolCall] = []

    def call(self, name: str, fn: Callable, *args, summary: Callable[[Any], str] | None = None,
             show: dict | None = None, **kwargs):
        started = time.perf_counter()
        result = fn(*args, **kwargs)
        self.calls.append(ToolCall(
            name=name, arguments=show or {}, result=summary(result) if summary else "",
            duration_ms=round((time.perf_counter() - started) * 1000, 1)))
        return result


def _numbers_in(obj: Any, out: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
        out.add(round(float(obj) * 100, 4))  # probabilities are often quoted as percentages
    elif isinstance(obj, str):
        for m in _NUMBER.findall(obj):
            try:
                out.add(float(m.replace(",", "")))
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in(v, out)


def invented_numbers(text: str, facts: Any) -> list[str]:
    """Numbers quoted in `text` that do not come from `facts` (tool outputs)."""
    allowed: set[float] = set()
    _numbers_in(facts, allowed)
    bad = []
    for raw in _NUMBER.findall(text):
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if not any(abs(value - a) <= max(0.51, 0.01 * abs(a)) for a in allowed):
            bad.append(raw)
    return bad


def guarded_answer(system: str, facts: dict, model: type[BaseModel],
                   check: Callable[[BaseModel], str | None] | None = None,
                   text_fields: tuple[str, ...] = (), max_tokens: int = 500) -> BaseModel | None:
    """LLM answer validated against `model`, the custom `check` and the number guard."""
    if not client.enabled():
        return None
    user = "Facts from tools (JSON):\n" + json.dumps(facts, ensure_ascii=False, default=str)
    objection = ""
    for _ in range(2):
        data = client.ask_json(system, user + objection, max_tokens=max_tokens)
        if data is None:
            _note("no_answer", client.USAGE.last_error)
            return None
        try:
            answer = model.model_validate(data)
        except ValidationError as exc:
            _note("structure", exc.errors()[0]["msg"])
            objection = f"\n\nThe previous answer was rejected: invalid structure ({exc.errors()[0]['msg']}). Answer again."
            continue
        problem = check(answer) if check else None
        guard = "check"
        if problem is None:
            for name in text_fields:
                bad = invented_numbers(str(getattr(answer, name, "")), facts)
                if bad:
                    problem = f"the text quotes numbers that are not in the facts: {', '.join(bad[:4])}"
                    guard = "numbers"
                    break
        if problem is None:
            _note("accepted")
            return answer
        _note(guard, problem)
        objection = f"\n\nThe previous answer was rejected: {problem}. Answer again, using only the facts."
    return None
