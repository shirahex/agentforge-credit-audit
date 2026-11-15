"""Agent graph (task I3).

    analyste_dossier -> modele_scoring -+-> generateur_contrefactuels -> verificateur_equite -+-> arbitre_redacteur
                                        |            ^                                        |          |
                                        |            +---- rejected, attempts left -----------+          | escalated
                                        +-> (approved) verificateur_equite                               v
                                                                                                  revue_humaine
                                                                                              (interrupt, resumed
                                                                                               by the reviewer)

Two compiled graphs are built from the same nodes:

* `graph`: no checkpointer, no interrupt. One `invoke` returns the final
  state. Used by the tests, the model report and the evaluation.
* `durable_graph()`: SQLite checkpointer and human interrupt. Every step is
  saved, so a run survives a restart, and an escalated run waits for the
  reviewer. Used by the API through graph/runner.py.

Every node is wrapped by `_step`, which is where the orchestration layer
does its own work without touching the agents: it times the step, measures
the LLM usage, collects the guard outcomes, builds one trail record, writes
it to the JSONL trace and appends it to the state. The API events, the trace
and the PDF report are all derived from these records.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from app import config
from app.agents import (
    analyste_dossier,
    arbitre_redacteur,
    generateur_contrefactuels,
    modele_scoring,
    verificateur_equite,
)
from app.agents.base import start_guard_log
from app.graph import trace
from app.graph.state import AuditState
from app.llm import client as llm

AGENT_LABELS = {
    "analyste_dossier": "Analyste-Dossier",
    "modele_scoring": "Modèle-Scoring",
    "generateur_contrefactuels": "Générateur-Contrefactuels",
    "verificateur_equite": "Vérificateur-Équité",
    "arbitre_redacteur": "Arbitre et Rédacteur",
    "revue_humaine": "Arbitre et Rédacteur",
}
# The reviewer's step is reported under the agent that asked for the review, so the interface
# keeps its five nodes: the Arbitre turns from "escalated" to "finished" once the person has decided.
EVENT_NODE = {"revue_humaine": "arbitre_redacteur"}
_PAYLOAD_KEYS = ("analysis", "score", "fairness", "decision")


def _usage() -> dict[str, float]:
    u = llm.USAGE
    return {"calls": u.calls, "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
            "failures": u.failures, "cached": u.cached, "seconds": u.seconds}


def _payload(out: dict[str, Any]) -> dict[str, Any]:
    payload = {k: out[k].model_dump(mode="json") for k in _PAYLOAD_KEYS if k in out}
    if "counterfactuals" in out:
        payload["counterfactuals"] = [c.model_dump(mode="json") for c in out["counterfactuals"]]
    if "explanation" in out:
        payload["explanation"] = out["explanation"]
    return payload


def _plan_key(plan) -> tuple:
    """Plans are tuples in memory and lists once read back from a checkpoint."""
    return (tuple(plan[0]), plan[1], plan[2])


def _step(node: str, fn: Callable[[AuditState], AuditState], closes: bool = False) -> Callable[[AuditState], AuditState]:
    def run(state: AuditState) -> AuditState:
        if state.get("cf_plans"):
            state = {**state, "cf_plans": [_plan_key(p) for p in state["cf_plans"]]}
        guards = start_guard_log()
        before, started = _usage(), time.perf_counter()
        out = dict(fn(state))  # a human interrupt is raised from here and leaves no record
        after = _usage()
        record: dict[str, Any] = {
            "run_id": state.get("run_id", ""), "seq": len(state.get("trail", [])),
            "ts": datetime.now(timezone.utc).isoformat(),
            "node": EVENT_NODE.get(node, node), "graph_node": node, "agent": AGENT_LABELS[node],
            "status": out.get("status", "completed"), "mode": out.get("mode", "rules"),
            "message": out.get("log", ""), "reasoning": out.get("reasoning", ""),
            "attempt": out.get("attempts", state.get("attempts", 0)),
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "tool_calls": [t.model_dump(mode="json") for t in out.get("tool_calls", [])],
            "llm": {k: round(after[k] - before[k], 3) for k in after},
            "llm_asked": bool(guards), "guards": list(guards),
        }
        if closes and "decision" in out and (out.get("status") == "finished" or node == "arbitre_redacteur"):
            merged = {**state, **out}
            decision, calls = arbitre_redacteur.close(merged, out["decision"], state.get("trail", []) + [
                {**record, "payload": _payload(out)}])
            out["decision"] = decision
            out["tool_calls"] = list(out.get("tool_calls", [])) + calls
            record["tool_calls"] += [t.model_dump(mode="json") for t in calls]
            record["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
        record["payload"] = _payload(out)
        if state.get("run_id"):
            trace.append(state["run_id"], record)
        out["trail"] = [record]
        return out

    return run


def _after_scoring(state: AuditState) -> str:
    return "generateur_contrefactuels" if state["score"].decision == "refused" else "verificateur_equite"


def _after_audit(state: AuditState) -> str:
    refused = state["score"].decision == "refused"
    no_cf = not state.get("counterfactuals")
    if refused and no_cf and state.get("attempts", 0) < config.MAX_CF_ATTEMPTS:
        return "generateur_contrefactuels"
    return "arbitre_redacteur"


def _after_arbitration(state: AuditState) -> str:
    return "revue_humaine" if state["decision"].escalated else END


def build_graph(checkpointer=None, human_review: bool = False, verification_loop: bool = True):
    """Compiles the audit graph.

    checkpointer        saves the state after every step (required for `human_review`)
    human_review        an escalated audit stops on a LangGraph interrupt until a reviewer answers
    verification_loop   False removes the rejection loop: one attempt, whatever the auditor says
                        (ablation of the evaluation, task I6)
    """
    if human_review and checkpointer is None:
        raise ValueError("the human interrupt needs a checkpointer to keep the waiting run")
    g = StateGraph(AuditState)
    g.add_node("analyste_dossier", _step("analyste_dossier", analyste_dossier.run))
    g.add_node("modele_scoring", _step("modele_scoring", modele_scoring.run))
    g.add_node("generateur_contrefactuels", _step("generateur_contrefactuels", generateur_contrefactuels.run))
    g.add_node("verificateur_equite", _step("verificateur_equite", verificateur_equite.run))
    g.add_node("arbitre_redacteur", _step("arbitre_redacteur", arbitre_redacteur.run, closes=True))

    g.add_edge(START, "analyste_dossier")
    g.add_edge("analyste_dossier", "modele_scoring")
    g.add_conditional_edges(
        "modele_scoring", _after_scoring, ["generateur_contrefactuels", "verificateur_equite"]
    )
    g.add_edge("generateur_contrefactuels", "verificateur_equite")
    if verification_loop:
        g.add_conditional_edges(
            "verificateur_equite", _after_audit, ["generateur_contrefactuels", "arbitre_redacteur"]
        )
    else:
        g.add_edge("verificateur_equite", "arbitre_redacteur")
    if human_review:
        g.add_node("revue_humaine", _step("revue_humaine", arbitre_redacteur.human_review, closes=True))
        g.add_conditional_edges("arbitre_redacteur", _after_arbitration, ["revue_humaine", END])
        g.add_edge("revue_humaine", END)
    else:
        g.add_edge("arbitre_redacteur", END)
    return g.compile(checkpointer=checkpointer)


graph = build_graph()


def durable_graph(checkpointer=None):
    """Graph with SQLite checkpoints and the human interrupt, as run by the API."""
    from app.memory.checkpointer import sqlite_checkpointer

    return build_graph(checkpointer=checkpointer or sqlite_checkpointer(), human_review=True)
