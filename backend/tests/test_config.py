from datetime import date, timezone

import pytest
from pydantic import ValidationError

from app.clock import demo_today, now_utc
from app.config import load_settings


def test_missing_or_blank_variables_keep_their_defaults() -> None:
    settings = load_settings({"LLM_MODEL": "", "AGENT_MODE": "  "})

    assert settings.agent_mode == "scripted"
    assert settings.demo_today == date(2026, 10, 15)
    assert settings.demo_otp == "246810"
    assert settings.cooling_off_seconds == 60
    assert settings.fx_offline is False
    assert settings.database_url == "sqlite:///./data/bridge.db"


def test_variables_are_parsed_into_typed_values() -> None:
    settings = load_settings(
        {
            "AGENT_MODE": "live",
            "DEMO_TODAY": "2026-11-01",
            "COOLING_OFF_SECONDS": "5",
            "FX_OFFLINE": "true",
        }
    )

    assert settings.agent_mode == "live"
    assert settings.demo_today == date(2026, 11, 1)
    assert settings.cooling_off_seconds == 5
    assert settings.fx_offline is True


@pytest.mark.parametrize(
    "env",
    [{"AGENT_MODE": "auto"}, {"DEMO_TODAY": "15/10/2026"}, {"DEMO_OTP": "12ab"}],
)
def test_invalid_values_are_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        load_settings(env)


def test_api_key_is_not_printed() -> None:
    settings = load_settings({"ANTHROPIC_API_KEY": "sk-secret-value"})

    assert "sk-secret-value" not in repr(settings)
    assert settings.anthropic_api_key.get_secret_value() == "sk-secret-value"


def test_clock_uses_the_demo_date_and_real_utc() -> None:
    assert demo_today() == date(2026, 10, 15)
    assert now_utc().tzinfo is timezone.utc
