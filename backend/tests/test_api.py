import time

from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.samples import REFUSED

config.STEP_DELAY_SECONDS = 0
client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_audit_run_and_event_stream():
    run_id = client.post("/api/audits", json=REFUSED.model_dump()).json()["run_id"]
    for _ in range(100):
        r = client.get(f"/api/audits/{run_id}")
        if r.status_code == 200:
            break
        time.sleep(0.05)
    assert r.status_code == 200 and r.json()["decision"] == "refused"

    body = client.get(f"/api/audits/{run_id}/events").text
    assert body.count("data: ") >= 7  # 5 agents, one loop, end marker
    assert '"status":"rejected"' in body
    assert "event: end" in body


def test_invalid_file_is_rejected():
    bad = REFUSED.model_dump() | {"age": 12}
    assert client.post("/api/audits", json=bad).status_code == 422
