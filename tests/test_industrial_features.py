from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ask_returns_traceable_runbook_and_audit_event():
    response = client.post(
        "/api/ask",
        json={"question": "Why would read retry count spike after a firmware update?", "top_k": 4},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["trace_id"].startswith("QA-")
    assert payload["audit_event"]["trace_id"] == payload["trace_id"]
    assert payload["investigation_runbook"]["owner_team"] == "NAND Reliability"
    assert "required_evidence" in payload["investigation_runbook"]
    assert payload["risk_controls"]["grounding_policy"] == "context-only"


def test_audit_log_endpoint_exposes_recent_questions():
    response = client.get("/api/audit-log")

    assert response.status_code == 200
    payload = response.json()

    assert "events" in payload
    assert payload["retention_policy"] == "in-memory demo audit trail"
