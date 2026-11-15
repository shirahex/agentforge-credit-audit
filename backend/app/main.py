"""HTTP API.

GET  /health                    liveness, model and LLM status
GET  /api/schema                applicant attributes (labels, options, ranges) for the form
GET  /api/samples               demo applicant files taken from the test set
GET  /api/model                 model card data: metrics, policies, curves, importance
POST /api/audits                start an audit, returns {run_id}
GET  /api/audits                history of audits
GET  /api/audits/{id}           full record: application, events, decision, review
GET  /api/audits/{id}/events    server-sent events, one AgentEvent per agent step
POST /api/audits/{id}/review    human reviewer's decision on an escalated audit

Owner: Imane (task I4) for hardening: persistent run store, LangGraph
interrupt behind the review endpoint, report download. The routes above
are the minimal versions the interface needs.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import config
from app.domain import features
from app.domain.model import MODEL_DIR, ROOT
from app.graph.build import AGENT_LABELS, graph
from app.llm import client as llm
from app.samples import load_samples
from app.schemas import AgentEvent, LoanApplication
from app.tools import scoring

app = FastAPI(title="AgentForge Credit Audit")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS: dict[str, dict] = {}
_PAYLOAD_KEYS = ("analysis", "score", "fairness", "decision")


class Review(BaseModel):
    outcome: Literal["approved", "refused"]
    reviewer: str = Field(default="Reviewer", max_length=60)
    comment: str = Field(default="", max_length=1000)


def _execute(run_id: str, application: LoanApplication) -> None:
    run = RUNS[run_id]
    try:
        for update in graph.stream({"application": application}, stream_mode="updates"):
            for node, out in update.items():
                time.sleep(config.STEP_DELAY_SECONDS)
                payload = {k: out[k].model_dump(mode="json") for k in _PAYLOAD_KEYS if k in out}
                if "counterfactuals" in out:
                    payload["counterfactuals"] = [c.model_dump(mode="json") for c in out["counterfactuals"]]
                if "explanation" in out:
                    payload["explanation"] = out["explanation"]
                if "decision" in out:
                    run["decision"] = out["decision"].model_dump(mode="json")
                run["events"].append(AgentEvent(
                    run_id=run_id, seq=len(run["events"]), agent=AGENT_LABELS.get(node, node), node=node,
                    status=out.get("status", "completed"), message=out.get("log", ""),
                    reasoning=out.get("reasoning", ""), mode=out.get("mode", "rules"),
                    tool_calls=out.get("tool_calls", []), payload=payload))
    except Exception as exc:  # surfaced to the interface instead of a silent stop
        run["events"].append(AgentEvent(run_id=run_id, seq=len(run["events"]), agent="System", node="system",
                                        status="error", message=f"{type(exc).__name__}: {exc}"))
    finally:
        run["done"] = True
        run["finished_at"] = datetime.now(timezone.utc).isoformat()


def _record(run_id: str) -> dict:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown audit")
    return run


def _public(run_id: str, run: dict, full: bool) -> dict:
    d = run["decision"]
    out = {
        "run_id": run_id, "applicant_id": run["application"].applicant_id, "started_at": run["started_at"],
        "finished_at": run.get("finished_at"), "done": run["done"],
        "decision": d["decision"] if d else None,
        "default_probability": d["default_probability"] if d else None,
        "escalated": d["escalated"] if d else False, "attempts": d["attempts"] if d else 0,
        "paths": len(d["counterfactuals"]) if d else 0, "review": run["review"],
    }
    if full:
        out["application"] = run["application"].model_dump(mode="json")
        out["events"] = [e.model_dump(mode="json") for e in run["events"]]
        out["result"] = d
    return out


@app.get("/health")
def health() -> dict:
    m = scoring.model()
    return {"status": "ok", "model": m.version, "variant": m.variant, "threshold": scoring.threshold(),
            "llm": llm.describe()}


@app.get("/api/schema")
def schema() -> dict:
    return {"features": features.describe(), "threshold": scoring.threshold(),
            "borderline_margin": config.BORDERLINE_MARGIN, "max_attempts": config.MAX_CF_ATTEMPTS}


@app.get("/api/samples")
def samples() -> list[dict]:
    return load_samples()


@app.get("/api/model")
def model_card() -> dict:
    variant = scoring.model().variant
    meta = json.loads((MODEL_DIR / f"model_{variant}.json").read_text(encoding="utf-8"))
    other = "unaware" if variant == "full" else "full"
    other_file = MODEL_DIR / f"model_{other}.json"
    curves_file = ROOT / "ml" / "reports" / "summary.json"
    return {
        "meta": meta,
        "comparison": json.loads(other_file.read_text(encoding="utf-8")) if other_file.exists() else None,
        "summary": json.loads(curves_file.read_text(encoding="utf-8")) if curves_file.exists() else None,
        "labels": {f.name: f.label for f in features.FEATURES},
    }


@app.post("/api/audits")
def start_audit(application: LoanApplication) -> dict:
    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {"application": application, "events": [], "done": False, "decision": None, "review": None,
                    "started_at": datetime.now(timezone.utc).isoformat()}
    threading.Thread(target=_execute, args=(run_id, application), daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/audits")
def list_audits() -> list[dict]:
    return [_public(rid, run, full=False) for rid, run in reversed(list(RUNS.items()))]


@app.get("/api/audits/{run_id}")
def audit_record(run_id: str) -> dict:
    return _public(run_id, _record(run_id), full=True)


@app.get("/api/audits/{run_id}/events")
async def audit_events(run_id: str) -> StreamingResponse:
    run = _record(run_id)

    async def stream():
        sent = 0
        while True:
            while sent < len(run["events"]):
                yield f"data: {run['events'][sent].model_dump_json()}\n\n"
                sent += 1
            if run["done"] and sent == len(run["events"]):
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.05)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/audits/{run_id}/review")
def review_audit(run_id: str, review: Review) -> dict:
    run = _record(run_id)
    if not run["done"] or run["decision"] is None:
        raise HTTPException(409, "audit still running")
    if not run["decision"]["escalated"]:
        raise HTTPException(409, "audit was not escalated")
    run["review"] = {**review.model_dump(), "at": datetime.now(timezone.utc).isoformat()}
    return _public(run_id, run, full=True)
