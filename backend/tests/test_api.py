import time

from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.samples import load_samples, sample

config.STEP_DELAY_SECONDS = 0
client = TestClient(app)


def run_audit(tag: str) -> dict:
    run_id = client.post("/api/audits", json=sample(tag).model_dump()).json()["run_id"]
    for _ in range(200):
        record = client.get(f"/api/audits/{run_id}").json()
        if record["done"]:
            return record
        time.sleep(0.05)
    raise AssertionError("audit did not finish")


def test_health_and_schema():
    h = client.get("/health").json()
    assert h["status"] == "ok" and 0 < h["threshold"] < 1 and h["model"]
    schema = client.get("/api/schema").json()
    names = {f["name"] for f in schema["features"]}
    assert names == set(sample("terms").features())


def test_samples_cover_every_path():
    tags = {s["tag"] for s in load_samples()}
    assert {"terms", "second_attempt", "approved", "borderline", "sensitive", "no_path"} <= tags


def test_audit_record_and_event_stream():
    record = run_audit("second_attempt")
    assert record["decision"] == "refused" and record["attempts"] == 2 and record["paths"] >= 1
    nodes = [e["node"] for e in record["events"]]
    assert nodes == ["analyste_dossier", "modele_scoring", "generateur_contrefactuels", "verificateur_equite",
                     "generateur_contrefactuels", "verificateur_equite", "arbitre_redacteur"]
    assert record["events"][3]["status"] == "rejected"
    assert all(e["tool_calls"] for e in record["events"][:4])

    body = client.get(f"/api/audits/{record['run_id']}/events").text
    assert body.count("data: ") == len(record["events"]) + 1 and "event: end" in body
    assert any(a["run_id"] == record["run_id"] for a in client.get("/api/audits").json())


def test_review_only_for_escalated_audits():
    normal = run_audit("terms")
    assert client.post(f"/api/audits/{normal['run_id']}/review", json={"outcome": "approved"}).status_code == 409
    escalated = run_audit("borderline")
    r = client.post(f"/api/audits/{escalated['run_id']}/review",
                    json={"outcome": "approved", "reviewer": "M. Daouki", "comment": "Stable employment."})
    assert r.status_code == 200 and r.json()["review"]["outcome"] == "approved"


# ----------------------------------------------------------------- task I4
def test_review_resumes_the_interrupted_graph_and_cannot_be_sent_twice():
    escalated = run_audit("no_path")
    assert escalated["status"] == "awaiting_review" and escalated["escalated"] and escalated["final_outcome"] is None
    assert client.get("/health").json()["store"]["awaiting_review"] >= 1
    url = f"/api/audits/{escalated['run_id']}/review"
    done = client.post(url, json={"outcome": "refused", "reviewer": "I. Alouani", "comment": "No path."}).json()
    assert done["status"] == "finished" and done["final_outcome"] == "refused"
    assert len(done["events"]) == len(escalated["events"]) + 1
    assert done["events"][-1]["status"] == "finished" and done["result"]["letter_status"] == "final"
    assert client.post(url, json={"outcome": "approved"}).status_code == 409


def test_history_and_records_survive_a_restart():
    """Nothing is kept in the process: a second application object on the same files serves the same audits."""
    from importlib import reload

    import app.graph.runner as runner
    import app.main as main

    record = run_audit("terms")
    runner._service = None  # the restarted process builds its own service and its own connections
    restarted = TestClient(reload(main).app)
    again = restarted.get(f"/api/audits/{record['run_id']}").json()
    assert again["events"] == record["events"] and again["result"] == record["result"]
    assert any(a["run_id"] == record["run_id"] for a in restarted.get("/api/audits").json())
    body = restarted.get(f"/api/audits/{record['run_id']}/events").text
    assert body.count("data: ") == len(record["events"]) + 1 and "event: end" in body


def test_report_letter_and_trace_downloads():
    record = run_audit("terms")
    rid = record["run_id"]
    pdf = client.get(f"/api/audits/{rid}/report")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:5] == b"%PDF-" and record["report_id"] in pdf.headers["content-disposition"]
    letter = client.get(f"/api/audits/{rid}/letter")
    assert letter.status_code == 200 and letter.text.startswith("Objet : ")
    lines = client.get(f"/api/audits/{rid}/trace").text.strip().splitlines()
    assert len(lines) == len(record["events"])
    assert client.get("/api/audits/unknown/report").status_code == 404


def test_report_is_rebuilt_when_its_file_is_gone():
    from pathlib import Path

    record = run_audit("approved")
    Path(record["result"]["report_path"]).unlink()
    pdf = client.get(f"/api/audits/{record['run_id']}/report")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"


def test_fairness_endpoint_and_model_card_carry_the_group_metrics():
    f = client.get("/api/fairness").json()
    assert set(f["full"]["attributes"]) == {"sex", "age_group", "foreign_worker"} and f["unaware"]["variant"] == "unaware"
    card = client.get("/api/model").json()
    assert card["fairness"]["full"]["attributes"]["sex"]["demographic_parity_difference"] >= 0


def test_invalid_file_is_rejected():
    bad = sample("terms").model_dump() | {"age": 12}
    assert client.post("/api/audits", json=bad).status_code == 422


def test_model_card():
    card = client.get("/api/model").json()
    assert card["meta"]["test"]["auc"] > 0.7 and "balanced" in card["meta"]["policies"]


def test_score_route_scores_without_agents():
    app = sample("terms").model_dump()
    out = client.post("/api/score", json=app).json()
    assert out["decision"] == "refused" and 0 < out["default_probability"] < 1 and out["top_factors"]
    shorter = {**app, "duration_months": 8}
    assert client.post("/api/score", json=shorter).json()["default_probability"] < out["default_probability"]


def test_demo_limit_answers_429(monkeypatch):
    from app import config, main

    monkeypatch.setattr(config, "DEMO_AUDITS_PER_HOUR", 1)
    main._started.clear()
    monkeypatch.setattr(main, "service", lambda: type("S", (), {"start": lambda self, a: "run-x"})())
    assert client.post("/api/audits", json=sample("approved").model_dump()).status_code == 200
    assert client.post("/api/audits", json=sample("approved").model_dump()).status_code == 429
    main._started.clear()
