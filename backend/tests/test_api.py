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


def test_invalid_file_is_rejected():
    bad = sample("terms").model_dump() | {"age": 12}
    assert client.post("/api/audits", json=bad).status_code == 422


def test_model_card():
    card = client.get("/api/model").json()
    assert card["meta"]["test"]["auc"] > 0.7 and "balanced" in card["meta"]["policies"]
