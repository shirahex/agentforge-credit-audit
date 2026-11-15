"""Durable execution of audits (tasks I3 and I4).

The API never runs the graph itself: it calls this service, which

* starts a run in a background thread, one LangGraph thread per run id;
* turns every finished step into an AgentEvent stored in SQLite, from which
  the event stream and the history are served;
* stops when the graph interrupts for a human review, and resumes the same
  run when the reviewer answers;
* at startup, resumes the runs that a crash or a restart left unfinished,
  from their last checkpoint.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command

from app import config
from app.graph.build import durable_graph
from app.memory import run_store
from app.schemas import AgentEvent, LoanApplication


def event_from_record(run_id: str, record: dict[str, Any]) -> dict[str, Any]:
    """AgentEvent of one trail record. The trail is in the checkpoint, so events can always be rebuilt."""
    return AgentEvent(
        run_id=run_id, seq=record["seq"], agent=record["agent"], node=record["node"], status=record["status"],
        message=record["message"], reasoning=record["reasoning"], mode=record["mode"],
        tool_calls=record["tool_calls"], payload=record["payload"], ts=record["ts"]).model_dump(mode="json")


class AuditService:
    def __init__(self, checkpointer=None) -> None:
        self.graph = durable_graph(checkpointer)
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _config(run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}}

    # ------------------------------------------------------------------ public
    def start(self, application: LoanApplication, run_id: str | None = None, background: bool = True) -> str:
        run_id = run_id or uuid.uuid4().hex[:12]
        run_store.create(run_id, application)
        self._launch(run_id, {"application": application, "run_id": run_id}, background)
        return run_id

    def review(self, run_id: str, review: dict[str, Any]) -> None:
        """Answers the human interrupt of an escalated run and lets the graph finish it (synchronous)."""
        review = {**review, "at": review.get("at") or datetime.now(timezone.utc).isoformat()}
        run_store.update(run_id, status=run_store.RUNNING, review=review)
        self._execute(run_id, Command(resume=review), pace=False)

    def awaiting_review(self, run_id: str) -> bool:
        state = self.graph.get_state(self._config(run_id))
        return bool(state.next) and any(task.interrupts for task in state.tasks)

    def recover(self, background: bool = True) -> list[str]:
        """Resumes the runs left in the `running` state by a previous process."""
        resumed = []
        for run_id in run_store.with_status(run_store.RUNNING):
            if run_id in self._threads and self._threads[run_id].is_alive():
                continue
            state = self.graph.get_state(self._config(run_id))
            if state.values:  # a checkpoint exists: continue from it
                self._backfill(run_id, state.values.get("trail", []))
                if any(task.interrupts for task in state.tasks):
                    self._settle(run_id)
                    continue
                self._launch(run_id, None, background)
            else:  # stopped before the first checkpoint: start over
                record = run_store.get(run_id)
                self._launch(run_id, {"application": LoanApplication(**record["application"]), "run_id": run_id},
                             background)
            resumed.append(run_id)
        return resumed

    def state(self, run_id: str) -> dict[str, Any]:
        return self.graph.get_state(self._config(run_id)).values

    def wait(self, run_id: str, timeout: float = 30) -> None:
        thread = self._threads.get(run_id)
        if thread:
            thread.join(timeout)

    # ------------------------------------------------------------------ internals
    def _launch(self, run_id: str, graph_input, background: bool) -> None:
        if not background:
            self._execute(run_id, graph_input, pace=False)
            return
        thread = threading.Thread(target=self._execute, args=(run_id, graph_input), daemon=True, name=f"audit-{run_id}")
        with self._lock:
            self._threads[run_id] = thread
        thread.start()

    def _backfill(self, run_id: str, trail: list[dict]) -> None:
        for record in trail[run_store.event_count(run_id):]:
            run_store.add_event(run_id, record["seq"], event_from_record(run_id, record))

    def _execute(self, run_id: str, graph_input, pace: bool = True) -> None:
        try:
            for update in self.graph.stream(graph_input, self._config(run_id), stream_mode="updates"):
                for node, out in update.items():
                    if node == "__interrupt__":
                        continue
                    if pace:
                        time.sleep(config.STEP_DELAY_SECONDS)
                    for record in out.get("trail", []):
                        run_store.add_event(run_id, record["seq"], event_from_record(run_id, record))
                    if "decision" in out:
                        run_store.update(run_id, decision=out["decision"].model_dump(mode="json"))
            self._settle(run_id)
        except Exception as exc:  # surfaced to the interface instead of a silent stop
            seq = run_store.event_count(run_id)
            run_store.add_event(run_id, seq, AgentEvent(
                run_id=run_id, seq=seq, agent="System", node="system", status="error",
                message=f"{type(exc).__name__}: {exc}").model_dump(mode="json"))
            run_store.update(run_id, status=run_store.ERROR, error=f"{type(exc).__name__}: {exc}", finished=True)

    def _settle(self, run_id: str) -> None:
        """Run stopped: either the graph is waiting for a reviewer, or it has reached its end."""
        state = self.graph.get_state(self._config(run_id))
        decision = state.values.get("decision")
        if decision is not None:
            run_store.update(run_id, decision=decision.model_dump(mode="json"))
        if state.next and any(task.interrupts for task in state.tasks):
            run_store.update(run_id, status=run_store.AWAITING_REVIEW, finished=True)
        else:
            run_store.update(run_id, status=run_store.FINISHED, finished=True)


_service: AuditService | None = None
_service_lock = threading.Lock()


def service() -> AuditService:
    global _service
    with _service_lock:
        if _service is None:
            _service = AuditService()
        return _service
