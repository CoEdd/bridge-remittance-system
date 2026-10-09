"""
Chat turns as event streams.

POST /chat starts a turn in a background thread and returns a stream id. The events are
kept in memory, so GET /chat/stream/{id} can replay them from the start and then follow
along until the turn is done. The turn finishes even if nobody is listening.
"""

import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.agent.loop import run_turn
from app.agent.types import Trigger
from app.db import get_engine
from app.models import User
from app.seed import DEMO_USER_ID

logger = logging.getLogger(__name__)

MAX_STREAMS = 50
Event = tuple[str, dict[str, Any]]


class Stream:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self._changed = threading.Condition()
        self.finished = False

    def add(self, name: str, payload: dict[str, Any]) -> None:
        with self._changed:
            self.events.append((name, payload))
            if name == "done":
                self.finished = True
            self._changed.notify_all()

    def follow(self) -> Iterator[Event]:
        """Every event so far, then each new one as it happens, ending after "done"."""
        position = 0
        while True:
            with self._changed:
                while position >= len(self.events) and not self.finished:
                    self._changed.wait(timeout=30)
                batch = self.events[position:]
                position = len(self.events)
                finished = self.finished
            yield from batch
            if finished and position >= len(self.events):
                return


_streams: OrderedDict[str, Stream] = OrderedDict()
_lock = threading.Lock()


def _run(stream: Stream, trigger: Trigger) -> None:
    try:
        with Session(get_engine()) as session:
            run_turn(session, session.get_one(User, DEMO_USER_ID), trigger, stream.add)
    except Exception:
        logger.exception("The agent turn failed.")
        stream.add("error", {"message": "Something went wrong. No money has moved.", "message_en": "Something went wrong. No money has moved."})
        stream.add("done", {})


def start(trigger: Trigger) -> str:
    """Begin a turn in the background and return the id of its event stream."""
    stream_id = uuid.uuid4().hex
    stream = Stream()
    with _lock:
        _streams[stream_id] = stream
        while len(_streams) > MAX_STREAMS:
            _streams.popitem(last=False)
    threading.Thread(target=_run, args=(stream, trigger), daemon=True, name=f"turn-{stream_id[:8]}").start()
    return stream_id


def get(stream_id: str) -> Stream | None:
    with _lock:
        return _streams.get(stream_id)
