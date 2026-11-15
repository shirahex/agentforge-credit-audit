"""HTTP API (task I4 on top of the first routes).

GET  /health                    liveness, model, LLM status, state of the stores
GET  /api/schema                applicant attributes (labels, options, ranges) for the form
GET  /api/samples               demo applicant files taken from the test set
GET  /api/model                 model card data: metrics, policies, curves, importance, group fairness
GET  /api/fairness              Fairlearn group metrics of both model variants
POST /api/audits                start an audit, returns {run_id}
GET  /api/audits                history of audits, kept across restarts
GET  /api/audits/{id}           full record: application, events, decision, review
GET  /api/audits/{id}/events    server-sent events, one AgentEvent per agent step
POST /api/audits/{id}/review    reviewer's decision: resumes the interrupted graph and closes the audit
GET  /api/audits/{id}/report    PDF audit report
GET  /api/audits/{id}/letter    applicant letter (French, plain text)
GET  /api/audits/{id}/trace     JSONL trace of every step and tool call

Runs are executed by graph/runner.py on the durable graph (SQLite
checkpoints, human interrupt). Runs and events live in SQLite
(memory/run_store.py): nothing is kept in the memory of this process, so
the history, an event stream and a pending review survive a restart, and
the runs a restart interrupted are resumed when the API starts.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app import config
from app.domain import features
from app.domain.model import MODEL_DIR, ROOT
from app.graph import trace
from app.graph.runner import service
from app.llm import client as llm
from app.memory import case_store, run_store
from app.samples import load_samples
from app.schemas import AuditDecision, LoanApplication
from app.tools import scoring
from app.tools.fairness import group_fairness_comparison
from app.tools.report import render_report


@asynccontextmanager
async def lifespan(_: FastAPI):
    resumed = service().recover()  # runs interrupted by the previous shutdown continue from their checkpoint
    if resumed:
        print(f"Resumed {len(resumed)} interrupted audit(s): {', '.join(resumed)}")
    yield


app = FastAPI(title="AgentForge Credit Audit", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


class Review(BaseModel):
    outcome: Literal["approved", "refused"]
    reviewer: str = Field(default="Reviewer", max_length=60)
    comment: str = Field(default="", max_length=1000)


def _record(run_id: str) -> dict:
    run = run_store.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown audit")
    return run


def _public(run: dict, full: bool) -> dict:
    d = run["decision"]
    out = {
        "run_id": run["run_id"], "applicant_id": run["applicant_id"], "started_at": run["started_at"],
        "finished_at": run["finished_at"], "status": run["status"], "done": run["status"] != run_store.RUNNING,
        "decision": d["decision"] if d else None,
        "final_outcome": d.get("final_outcome") if d else None,
        "default_probability": d["default_probability"] if d else None,
        "escalated": d["escalated"] if d else False, "attempts": d["attempts"] if d else 0,
        "paths": len(d["counterfactuals"]) if d else 0, "review": run["review"],
        "report_id": d.get("report_id") if d else None, "error": run["error"],
    }
    if full:
        out["application"] = run["application"]
        out["events"] = run_store.events(run["run_id"])
        out["result"] = d
    return out


@app.get("/health")
def health() -> dict:
    m = scoring.model()
    return {"status": "ok", "model": m.version, "variant": m.variant, "threshold": scoring.threshold(),
            "llm": llm.describe(),
            "store": {"audits": len(run_store.list_runs(10_000)), "cases": case_store.count(),
                      "awaiting_review": len(run_store.with_status(run_store.AWAITING_REVIEW))}}


@app.get("/api/schema")
def schema() -> dict:
    return {"features": features.describe(), "threshold": scoring.threshold(),
            "borderline_margin": config.BORDERLINE_MARGIN, "max_attempts": config.MAX_CF_ATTEMPTS}


@app.get("/api/samples")
def samples() -> list[dict]:
    return load_samples()


@app.get("/api/fairness")
def fairness() -> dict:
    return group_fairness_comparison()


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
        "fairness": group_fairness_comparison(),
    }


@app.post("/api/audits")
def start_audit(application: LoanApplication) -> dict:
    return {"run_id": service().start(application)}


@app.get("/api/audits")
def list_audits() -> list[dict]:
    return [_public(run, full=False) for run in run_store.list_runs()]


@app.get("/api/audits/{run_id}")
def audit_record(run_id: str) -> dict:
    return _public(_record(run_id), full=True)


@app.get("/api/audits/{run_id}/events")
async def audit_events(run_id: str) -> StreamingResponse:
    _record(run_id)

    async def stream():
        sent = -1
        while True:
            status = run_store.status(run_id)  # read before the events: nothing is written after a run stops
            for event in run_store.events(run_id, after=sent):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                sent = event["seq"]
            if status != run_store.RUNNING:
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.08)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/audits/{run_id}/review")
def review_audit(run_id: str, review: Review) -> dict:
    run = _record(run_id)
    if run["status"] == run_store.RUNNING or run["decision"] is None:
        raise HTTPException(409, "audit still running")
    if not run["decision"]["escalated"]:
        raise HTTPException(409, "audit was not escalated")
    if run["status"] != run_store.AWAITING_REVIEW or not service().awaiting_review(run_id):
        raise HTTPException(409, "audit already reviewed")
    service().review(run_id, review.model_dump())  # resumes the LangGraph interrupt
    return _public(_record(run_id), full=True)


def _finished(run_id: str) -> tuple[dict, AuditDecision]:
    run = _record(run_id)
    if run["status"] == run_store.RUNNING or run["decision"] is None:
        raise HTTPException(409, "audit still running")
    return run, AuditDecision(**run["decision"])


@app.get("/api/audits/{run_id}/report")
def audit_report(run_id: str) -> FileResponse:
    run, decision = _finished(run_id)
    path = Path(decision.report_path) if decision.report_path else None
    if path is None or not path.exists():  # report folder emptied: the trace is enough to rebuild it
        steps = trace.read(run_id) or [{**e, "duration_ms": 0.0} for e in run_store.events(run_id)]
        rebuilt = render_report(decision, steps, application=LoanApplication(**run["application"]), run_id=run_id)
        if rebuilt is None:
            raise HTTPException(404, "no report for this audit")
        path = Path(rebuilt)
    return FileResponse(path, media_type="application/pdf",
                        filename=f"audit-{run['applicant_id']}-{decision.report_id or run_id}.pdf")


@app.get("/api/audits/{run_id}/letter")
def audit_letter(run_id: str) -> PlainTextResponse:
    run, decision = _finished(run_id)
    if not decision.letter:
        raise HTTPException(404, "no letter for this audit")
    return PlainTextResponse(decision.letter, media_type="text/plain; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="lettre-{run["applicant_id"]}.txt"'})


@app.get("/api/audits/{run_id}/trace")
def audit_trace(run_id: str) -> FileResponse:
    _record(run_id)
    file = trace.trace_file(run_id)
    if not file.exists():
        raise HTTPException(404, "no trace for this audit")
    return FileResponse(file, media_type="application/x-ndjson", filename=f"trace-{run_id}.jsonl")
