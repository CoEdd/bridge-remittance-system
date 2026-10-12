import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from app.agent import streams
from app.agent.loop import shared_line
from app.agent.types import Trigger
from app.models import ChatMessage, Document
from app.routers.deps import SessionDep, UserDep
from app.schemas import ChatIn, ChatMessageOut, ChatStartOut

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
def send_message(body: ChatIn) -> ChatStartOut:
    """Send a chat message. The agent's turn runs in the background; follow it with the stream id."""
    text = body.text.strip()
    return ChatStartOut(stream_id=streams.start(Trigger(kind="message", text=text)), text=text)


@router.post("/document/{document_id}")
def document_uploaded(document_id: int, session: SessionDep, user: UserDep) -> ChatStartOut:
    """Tell the agent a document was uploaded or pasted, so it reads and explains it."""
    document = session.get(Document, document_id)
    if document is None or document.user_id != user.id:
        raise HTTPException(status_code=404, detail="There is no such document.")
    return ChatStartOut(
        stream_id=streams.start(Trigger(kind="document", document_id=document_id)), text=shared_line(document)
    )


@router.get("/stream/{stream_id}")
def follow_stream(stream_id: str) -> EventSourceResponse:
    """
    Server-Sent Events for one turn: step, message, approval_required or blocked, error, done.
    Each event's data is a JSON object.
    """
    stream = streams.get(stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="There is no such stream.")

    def events() -> Iterator[dict[str, str]]:
        for name, payload in stream.follow():
            yield {"event": name, "data": json.dumps(payload, ensure_ascii=False, default=str)}

    return EventSourceResponse(iterate_in_threadpool(events()))


@router.get("/history")
def history(session: SessionDep) -> list[ChatMessageOut]:
    """Every chat message, oldest first."""
    rows = session.scalars(select(ChatMessage).order_by(ChatMessage.id))
    return [
        ChatMessageOut(
            id=row.id,
            role=row.role,
            text=row.text,
            text_en=row.text_en,
            language=row.language,
            created_at=row.created_at,
            events=row.events or [],
        )
        for row in rows
    ]
