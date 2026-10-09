import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


def test_health_reports_status_mode_date_and_version() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "agent_mode": "scripted",
        "demo_today": "2026-10-15",
        "version": "0.1.0",
    }


def test_health_follows_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODE", "live")
    monkeypatch.setenv("DEMO_TODAY", "2026-11-01")
    get_settings.cache_clear()

    body = client.get("/health").json()

    assert body["agent_mode"] == "live"
    assert body["demo_today"] == "2026-11-01"


def test_health_is_readable_from_the_frontend_origin_only() -> None:
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    other = client.get("/health", headers={"Origin": "http://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in other.headers
