from fastapi import APIRouter

from app import documents
from app.clock import demo_today, now_utc
from app.documents.reader import read_message
from app.routers.deps import SessionDep, UserDep
from app.routers.documents import document_out
from app.schemas import MuleEventOut, ResetOut
from app.seed import reset
from app.seed.demo_docs import DEMO_DOCUMENTS, demo_docs_dir
from app.seed.events import STRANGER_AMOUNT, STRANGER_NAME, stranger_sends_money

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset_demo() -> ResetOut:
    """Rebuild the database: same seed data every time, FX rates fetched again and frozen."""
    source = reset()
    return ResetOut(status="reset", demo_today=demo_today(), fx_source=source)


@router.post("/events/mule")
def mule_event(session: SessionDep, user: UserDep) -> MuleEventOut:
    """
    Act 3: a stranger sends CNY 3,000.00, then their "please forward it" message arrives.
    The message is ingested exactly like a pasted one.
    """
    posting = stranger_sends_money(session, user, now_utc())
    demo = DEMO_DOCUMENTS["mule_message"]
    text = (demo_docs_dir() / demo.filename).read_text(encoding="utf-8")
    document = documents.ingest(
        session, user, filename=demo.filename, kind="message", read=read_message(text), source="demo event"
    )
    return MuleEventOut(
        posting_id=posting.id,
        sender=STRANGER_NAME,
        amount_minor=STRANGER_AMOUNT,
        currency="CNY",
        document=document_out(session, document),
    )
