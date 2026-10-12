from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Bill, Payee, PendingAction
from app.routers.deps import SessionDep, UserDep
from app.routers.documents import bill_out
from app.schemas import BillOut, PayeeOut

router = APIRouter(tags=["payments"])


@router.get("/bills")
def list_bills(session: SessionDep, user: UserDep) -> list[BillOut]:
    """The user's bills, soonest due first. Bills from risky documents are marked `flagged`."""
    bills = session.scalars(
        select(Bill)
        .where(Bill.user_id == user.id)
        .options(selectinload(Bill.payee), selectinload(Bill.document))
        .order_by(Bill.due_date.is_(None), Bill.due_date, Bill.id)
    )
    return [bill_out(bill) for bill in bills]


@router.get("/payees")
def list_payees(session: SessionDep, user: UserDep) -> list[PayeeOut]:
    """Every payee the student has paid, or that a document asked them to pay."""
    # A first payment that is waiting out its cooling-off time, by payee.
    waiting = session.scalars(
        select(PendingAction).where(
            PendingAction.user_id == user.id, PendingAction.status == "cooling_off", PendingAction.tool == "pay_bill"
        )
    )
    cooling_off = {(action.cost_breakdown or {}).get("payee_id"): action.expires_at for action in waiting}
    payees = session.scalars(
        select(Payee)
        .where(Payee.user_id == user.id)
        .options(selectinload(Payee.institution))
        .order_by(Payee.id)
    )
    return [
        PayeeOut(
            id=payee.id,
            name=payee.name,
            account_ref=payee.account_ref,
            bank_name=payee.bank_name,
            institution_id=payee.institution_id,
            institution_name=payee.institution.name if payee.institution else None,
            verified_source=payee.verified_source,
            created_at=payee.created_at,
            first_paid_at=payee.first_paid_at,
            cooling_off_until=cooling_off.get(payee.id),
        )
        for payee in payees
    ]
