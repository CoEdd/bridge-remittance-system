from collections.abc import Iterator

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def demo_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin the settings every test sees, whatever the container's .env says."""
    monkeypatch.setenv("AGENT_MODE", "scripted")
    monkeypatch.setenv("DEMO_TODAY", "2026-10-15")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
