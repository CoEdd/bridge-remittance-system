from fastapi import APIRouter
from sqlalchemy import select

from app import demo_progress, documents
from app.clock import demo_today, now_utc
from app.documents.reader import read_message
from app.routers.deps import SessionDep, UserDep
from app.routers.documents import document_out
from app.config import get_settings
from app.models import Bill, Document, PendingAction
from app.schemas import DemoSettingsOut, DemoStateOut, DemoStepOut, MuleEventOut, ResetOut
from app.seed import reset
from app.seed.demo_docs import DEMO_DOCUMENTS, demo_docs_dir
from app.seed.events import STRANGER_AMOUNT, STRANGER_NAME, stranger_sends_money

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset_demo() -> ResetOut:
    """Rebuild the database: same seed data every time, FX rates fetched again and frozen."""
    source = reset()
    demo_progress.clear()
    return ResetOut(status="reset", demo_today=demo_today(), fx_source=source)


@router.get("/settings")
def demo_settings() -> DemoSettingsOut:
    """The demo's one-time code and cooling-off time, for the approval screen to show."""
    settings = get_settings()
    return DemoSettingsOut(otp=settings.demo_otp, cooling_off_seconds=settings.cooling_off_seconds)


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


# A refusal with one of these reasons is the fake agent's payment (Act 2) or the forward request (Act 3).
AGENT_REASONS = {"PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"}
MULE_REASON = "MONEY_MULE_PATTERN"


@router.get("/state")
def demo_state(session: SessionDep, user: UserDep) -> DemoStateOut:
    """Which demo steps are done, read from the database and from what has been shown since the reset."""
    invoice_name = DEMO_DOCUMENTS["tuition_invoice"].filename
    invoice = session.scalars(
        select(Document).where(Document.user_id == user.id, Document.filename == invoice_name).order_by(Document.id)
    ).first()
    bill = session.scalars(select(Bill).where(Bill.document_id == invoice.id)).first() if invoice else None
    actions = list(session.scalars(select(PendingAction).where(PendingAction.user_id == user.id).order_by(PendingAction.id)))
    for_bill = [action for action in actions if bill is not None and (action.args or {}).get("bill_id") == bill.id]
    planned = bool(for_bill) or any(action.tool == "convert_currency" for action in actions)
    refused = [
        {item["code"] for item in action.reasons or []}
        for action in actions
        if action.tool == "pay_bill" and action.status == "refused"
    ]
    waiting = next(
        (action.plan_id for action in actions if action.plan_id and action.status in ("awaiting_confirm", "awaiting_otp")),
        None,
    )
    seen = demo_progress.seen()
    done = {
        "upload": invoice is not None,
        "verify": "invoice_viewed" in seen,
        "plan": planned,
        "pay": bill is not None and bill.status == "paid",
        "agent": any(codes & AGENT_REASONS for codes in refused),
        "mule": any(MULE_REASON in codes for codes in refused),
        "audit": {"chain_verified", "tamper_simulated"} <= seen,
        "redteam": "redteam_run" in seen,
        "sources": "sources_viewed" in seen,
    }
    return DemoStateOut(
        steps=[DemoStepOut(key=key, done=value) for key, value in done.items()],  # type: ignore[arg-type]
        invoice_document_id=invoice.id if invoice else None,
        pending_plan_id=waiting,
    )

