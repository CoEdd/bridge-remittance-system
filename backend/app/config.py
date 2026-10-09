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
