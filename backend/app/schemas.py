"""Request and response models for the HTTP API."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.config import AgentMode


class HealthResponse(BaseModel):
    status: Literal["ok"]
    agent_mode: AgentMode
    demo_today: date
    version: str
