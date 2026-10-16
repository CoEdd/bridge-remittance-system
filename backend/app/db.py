"""Database engine, sessions and the declarative base."""

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import DateTime, Dialect, Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class Base(DeclarativeBase):
    pass


# One writer at a time. Everything that changes money, actions or the audit log runs
# under this lock, so the hash chain and the balances can never be updated by two
# threads at once (request handlers and the background sweep share one process).
write_lock = threading.RLock()


class ResetGate:
    """
    A demo reset drops and rebuilds every table. Requests read inside `reading()`; a reset
    waits for the requests already running and holds new ones back until it is done, so no
    request ever sees the tables half built. The requests held back go first after a reset,
    so a second reset cannot keep them waiting.
    """

    def __init__(self) -> None:
        self._changed = threading.Condition()
        self._readers = 0
        self._held = 0  # requests waiting for a reset to finish
        self._resetting = False

    @contextmanager
    def reading(self) -> Iterator[None]:
        with self._changed:
            if self._resetting:
                self._held += 1
                self._changed.wait_for(lambda: not self._resetting)
                self._held -= 1
                self._changed.notify_all()
            self._readers += 1
        try:
            yield
        finally:
            with self._changed:
                self._readers -= 1
                self._changed.notify_all()

    @contextmanager
    def resetting(self) -> Iterator[None]:
        with self._changed:
            self._changed.wait_for(lambda: not self._resetting and self._held == 0)
            self._resetting = True
            self._changed.wait_for(lambda: self._readers == 0)
        try:
            yield
        finally:
            with self._changed:
                self._resetting = False
                self._changed.notify_all()


reset_gate = ResetGate()


class UtcDateTime(TypeDecorator[datetime]):
    """Stores timezone-aware datetimes as UTC. SQLite itself keeps no time zone."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Datetimes must be timezone-aware.")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=timezone.utc)


def make_engine(database_url: str) -> Engine:
    """An engine set up the way every Bridge database is: the live one, and isolated copies of it."""
    url = make_url(database_url)
    if url.database and url.database != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(url.database)), exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: Any, _record: Any) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@lru_cache
def get_engine() -> Engine:
    """The live demo database."""
    return make_engine(get_settings().database_url)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one database session per request, never during a demo reset."""
    with reset_gate.reading(), Session(get_engine()) as session:
        yield session
