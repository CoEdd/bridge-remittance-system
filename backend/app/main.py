"""Bridge backend: FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clock import demo_today
from app.config import get_settings
from app.routers import accounts, demo, me, payments
from app.schemas import HealthResponse
from app.seed import ensure_seeded

VERSION = "0.1.0"
FRONTEND_ORIGINS = ["http://localhost:3000"]

# Read the environment at import time so a bad value stops the server from starting.
get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ensure_seeded()  # first start: create the tables and load the demo data
    yield


app = FastAPI(title="Bridge API", version=VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)
for router in (me.router, accounts.router, payments.router, demo.router):
    app.include_router(router)


@app.get("/health")
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        agent_mode=get_settings().agent_mode,
        demo_today=demo_today(),
        version=VERSION,
    )
