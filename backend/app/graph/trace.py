"""JSONL trace of a run (task I3).

One line per finished agent step, written as soon as the step ends:

    {"run_id", "seq", "ts", "node", "agent", "status", "mode", "message", "reasoning", "attempt",
     "duration_ms", "tool_calls": [{"name", "arguments", "result", "duration_ms"}],
     "llm": {"calls", "prompt_tokens", "completion_tokens", "failures", "cached", "seconds"},
     "guards": [{"guard", "accepted", "detail"}], "payload": {...}}

The file is the audit trail kept outside the database and the raw material
of the evaluation (eval/run_eval.py): tool calls, tokens, latency, answers
rejected by each guard and steps that fell back to rules are all read here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.memory.db import data_dir


def trace_file(run_id: str) -> Path:
    return data_dir("traces") / f"{run_id}.jsonl"


def append(run_id: str, record: dict[str, Any]) -> None:
    with trace_file(run_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read(run_id: str) -> list[dict[str, Any]]:
    """Steps of a run in order. A step replayed after a restart keeps its last record."""
    file = trace_file(run_id)
    if not file.exists():
        return []
    steps: dict[int, dict[str, Any]] = {}
    for line in file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            steps[record["seq"]] = record
    return [steps[k] for k in sorted(steps)]


def summarise(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals of one run, as used in the evaluation tables."""
    guards = [g for s in steps for g in s.get("guards", [])]
    llm_steps = [s for s in steps if s.get("llm_asked")]
    return {
        "steps": len(steps),
        "tool_calls": sum(len(s.get("tool_calls", [])) for s in steps),
        "duration_ms": round(sum(s.get("duration_ms", 0.0) for s in steps), 1),
        "llm_calls": sum(s.get("llm", {}).get("calls", 0) for s in steps),
        "prompt_tokens": sum(s.get("llm", {}).get("prompt_tokens", 0) for s in steps),
        "completion_tokens": sum(s.get("llm", {}).get("completion_tokens", 0) for s in steps),
        "llm_steps": len(llm_steps),
        "fallback_steps": sum(1 for s in llm_steps if s.get("mode") == "rules"),
        "answers": len(guards),
        "rejected_structure": sum(1 for g in guards if g["guard"] == "structure"),
        "rejected_check": sum(1 for g in guards if g["guard"] == "check"),
        "rejected_numbers": sum(1 for g in guards if g["guard"] == "numbers"),
        "no_answer": sum(1 for g in guards if g["guard"] == "no_answer"),
    }
