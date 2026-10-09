"""Runtime settings, read once from environment variables."""

import os
from collections.abc import Mapping
from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

AgentMode = Literal["live", "scripted"]


class Settings(BaseModel):
    """One field per environment variable: the variable is the field name in upper case."""

    model_config = ConfigDict(frozen=True)

    anthropic_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    agent_mode: AgentMode = "scripted"
    demo_today: date = date(2026, 10, 15)
    demo_otp: str = Field(default="246810", pattern=r"^\d{6}$")
    cooling_off_seconds: int = Field(default=60, ge=0)
    fx_offline: bool = False
    database_url: str = "sqlite:///./data/bridge.db"
    # CNY the funding planner keeps spare on top of the bills it counts, in fen.
    funding_buffer_minor: int = Field(default=50_000, ge=0)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings from env vars. A missing or blank variable keeps its default."""
    source = os.environ if env is None else env
    values = {
        name: source[name.upper()]
        for name in Settings.model_fields
        if source.get(name.upper(), "").strip()
    }
    return Settings.model_validate(values)


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def effective_agent_mode() -> AgentMode:
    """Live needs an API key. Without one the app runs scripted, and says so."""
    settings = get_settings()
    has_key = bool(settings.anthropic_api_key.get_secret_value())
    return "live" if settings.agent_mode == "live" and has_key else "scripted"


def agent_note() -> str | None:
    """Why the agent is not in the mode that was asked for, if that is the case."""
    if get_settings().agent_mode == "live" and effective_agent_mode() == "scripted":
        return "no API key"
    return None
