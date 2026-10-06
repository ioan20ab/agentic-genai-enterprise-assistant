import base64
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from assistant.api import app
from assistant.batch import run_batch

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["llm_provider"] == "offline"
    assert r.json()["indexed_chunks"] > 0


def test_chat_realtime():
    r = client.post("/chat", json={"message": "What is the hotel limit per night in Athens?"})
    assert r.status_code == 200
    body = r.json()
    assert "150 EUR" in body["answer"]
    assert "travel_and_expense_policy.md" in body["sources"]


def test_chat_keeps_session_history():
    from assistant.api import _sessions

    client.post("/chat", json={"message": "How long must a password be?", "session_id": "s1"})
    assert len(_sessions["s1"]) == 2  # user + assistant turn stored


def test_batch_inference_preserves_order():
    qs = ["How often must scaffolding be inspected?", "What is the daily meal allowance when travelling?"]
    r = client.post("/batch", json={"questions": qs})
    results = r.json()["results"]
    assert "7 days" in results[0]["answer"]
    assert "40 EUR" in results[1]["answer"]


def test_api_key_is_enforced_when_set(monkeypatch):
    monkeypatch.setenv("API_KEY", "s3cret")
    assert client.post("/chat", json={"message": "hi"}).status_code == 401
    ok = client.post("/chat", json={"message": "How long must a password be?"}, headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200


def test_teams_outgoing_webhook_verifies_hmac(monkeypatch):
    secret = base64.b64encode(b"teams-shared-secret").decode()
    monkeypatch.setenv("TEAMS_WEBHOOK_SECRET", secret)
    body = json.dumps({"type": "message", "text": "<at>Assistant</at> How quickly must a lost laptop be reported?"}).encode()
    sig = base64.b64encode(hmac.new(base64.b64decode(secret), body, hashlib.sha256).digest()).decode()

    bad = client.post("/integrations/teams", content=body, headers={"Authorization": "HMAC wrong"})
    assert bad.status_code == 401
    good = client.post("/integrations/teams", content=body,
                       headers={"Authorization": f"HMAC {sig}", "Content-Type": "application/json"})
    assert good.status_code == 200
    assert good.json()["type"] == "message"
    assert "2 hours" in good.json()["text"]


def test_batch_cli(tmp_path):
    src = tmp_path / "in.jsonl"
    src.write_text(json.dumps({"id": "a", "question": "How is a private car reimbursed for business trips?"}) + "\n")
    out = tmp_path / "out.jsonl"
    assert run_batch(src, out) == 1
    row = json.loads(out.read_text())
    assert row["id"] == "a" and "0.30 EUR" in row["answer"]
