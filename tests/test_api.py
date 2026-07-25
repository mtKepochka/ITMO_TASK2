from pathlib import Path

from fastapi.testclient import TestClient

from ticket_automation.api import create_app


def test_api_exposes_health_process_result_and_metrics(tmp_path: Path) -> None:
    app = create_app(audit_path=tmp_path / "audit.jsonl")
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        response = client.post(
            "/api/v1/tickets/process",
            json={
                "ticket_id": "api-1",
                "channel": "web",
                "subject": "Сбой",
                "text": "Приложение не открывается. Это общий сбой?",
            },
        )
        stored = client.get("/api/v1/tickets/api-1")
        metrics = client.get("/api/v1/metrics")

    assert health.status_code == 200
    assert health.json()["version"] == "0.3.0"
    assert response.status_code == 200
    assert response.json()["result"]["action"] == "suggest_to_agent"
    assert stored.status_code == 200
    assert metrics.json()["requests"] == 1


def test_api_rejects_invalid_payload(tmp_path: Path) -> None:
    app = create_app(audit_path=tmp_path / "audit.jsonl")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tickets/process",
            json={"ticket_id": "", "text": ""},
        )

    assert response.status_code == 422
