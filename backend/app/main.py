"""Bridge backend: FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clock import demo_today
from app.config import get_settings
from app.schemas import HealthResponse

VERSION = "0.1.0"
FRONTEND_ORIGINS = ["http://localhost:3000"]

# Read the environment at import time so a bad value stops the server from starting.
get_settings()

app = FastAPI(title="Bridge API", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        agent_mode=get_settings().agent_mode,
        demo_today=demo_today(),
        version=VERSION,
    )
