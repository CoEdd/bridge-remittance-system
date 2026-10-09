"""Bridge backend: FastAPI application entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import actions, documents
from app.clock import demo_today
from app.config import get_settings
from app.db import get_engine
from app.documents.index import index
from app.routers import accounts, demo, me, payments
from app.routers import actions as actions_router
from app.routers import audit as audit_router
from app.routers import documents as documents_router
from app.schemas import HealthResponse
from app.seed import ensure_seeded

VERSION = "0.1.0"
FRONTEND_ORIGINS = ["http://localhost:3000"]
SWEEP_SECONDS = 2

logger = logging.getLogger(__name__)

# Read the environment at import time so a bad value stops the server from starting.
get_settings()


def run_due_actions() -> None:
    """One sweep: run cooling-off actions whose wait is over and expire stale approvals."""
    with Session(get_engine()) as session:
        actions.sweep(session)


async def _sweep_forever() -> None:
    while True:
        await asyncio.sleep(SWEEP_SECONDS)
        try:
            await asyncio.to_thread(run_due_actions)
        except Exception:
            logger.exception("The background sweep failed; it will try again.")


def warm_up_index() -> None:
    """Re-index stored documents and load the embedding model, so the first upload is not slow."""
    try:
        with Session(get_engine()) as session:
            documents.reindex(session)
        index.warm_up()
    except Exception:
        logger.exception("The passage index could not be warmed up; it will load on first use.")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ensure_seeded()  # first start: create the tables and load the demo data
    sweeper = asyncio.create_task(_sweep_forever())
    warm_up = asyncio.create_task(asyncio.to_thread(warm_up_index))
    yield
    sweeper.cancel()
    warm_up.cancel()


app = FastAPI(title="Bridge API", version=VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
for router in (
    me.router,
    accounts.router,
    payments.router,
    actions_router.router,
    audit_router.router,
    documents_router.router,
    demo.router,
):
    app.include_router(router)


@app.get("/health")
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        agent_mode=get_settings().agent_mode,
        demo_today=demo_today(),
        version=VERSION,
    )
