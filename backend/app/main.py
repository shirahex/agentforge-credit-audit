"""HTTP API. Owner: Imane (task I4).

POST /api/audits              start an audit, returns {run_id}
GET  /api/audits/{id}/events  server-sent events, one AgentEvent per agent step
GET  /api/audits/{id}         final AuditDecision (404 until finished)
GET  /api/samples             demo applicant files

TODO: persistent run store, human review endpoint, report download.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import config
from app.graph.build import AGENT_LABELS, graph
from app.samples import SAMPLES
from app.schemas import AgentEvent, AuditDecision, LoanApplication

app = FastAPI(title="AgentForge Credit Audit")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS: dict[str, dict] = {}


def _execute(run_id: str, application: LoanApplication) -> None:
    run = RUNS[run_id]
    try:
        for update in graph.stream({"application": application}, stream_mode="updates"):
            for node, out in update.items():
                time.sleep(config.STEP_DELAY_SECONDS)
                payload = {}
                for key in ("score", "fairness", "decision"):
                    if key in out:
                        payload[key] = out[key].model_dump(mode="json")
                if "counterfactuals" in out:
                    payload["counterfactuals"] = [c.model_dump(mode="json") for c in out["counterfactuals"]]
                if "decision" in out:
                    run["result"] = out["decision"]
                run["events"].append(
                    AgentEvent(
                        run_id=run_id,
                        seq=len(run["events"]),
                        agent=AGENT_LABELS.get(node, node),
                        status=out.get("status", "completed"),
                        message=out.get("log", ""),
                        payload=payload,
                    )
                )
    except Exception as exc:  # surfaced to the interface instead of a silent stop
        run["events"].append(
            AgentEvent(run_id=run_id, seq=len(run["events"]), agent="system", status="error", message=str(exc))
        )
    finally:
        run["done"] = True


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm_provider": config.LLM_PROVIDER}


@app.get("/api/samples")
def samples() -> list[LoanApplication]:
    return SAMPLES


@app.post("/api/audits")
def start_audit(application: LoanApplication) -> dict:
    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {"events": [], "done": False, "result": None}
    threading.Thread(target=_execute, args=(run_id, application), daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/audits/{run_id}/events")
async def audit_events(run_id: str) -> StreamingResponse:
    if run_id not in RUNS:
        raise HTTPException(404, "unknown run")

    async def stream():
        run, sent = RUNS[run_id], 0
        while True:
            while sent < len(run["events"]):
                yield f"data: {run['events'][sent].model_dump_json()}\n\n"
                sent += 1
            if run["done"] and sent == len(run["events"]):
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.05)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/audits/{run_id}")
def audit_result(run_id: str) -> AuditDecision:
    run = RUNS.get(run_id)
    if run is None or run["result"] is None:
        raise HTTPException(404, "audit not finished or unknown")
    return run["result"]
