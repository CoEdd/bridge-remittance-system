from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine


@pytest.fixture(autouse=True)
def demo_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """
    Pin the settings every test sees, whatever the container's .env says:
    a private empty database per test, and no network (offline FX snapshot).
    """
    monkeypatch.setenv("AGENT_MODE", "scripted")
    monkeypatch.setenv("DEMO_TODAY", "2026-10-15")
    monkeypatch.setenv("FX_OFFLINE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def session() -> Iterator[Session]:
    """A session on a freshly reset (seeded) database."""
    from app.seed import reset

    reset()
    with Session(get_engine()) as db:
        yield db


@pytest.fixture
def client() -> Iterator[TestClient]:
    """An API client. Starting the app seeds the empty database, as on first start."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
