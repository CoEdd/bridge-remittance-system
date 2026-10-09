from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.clock import demo_today
from app.models import Bill, Payee
from app.routers.deps import SessionDep, UserDep
from app.schemas import BillOut, PayeeOut

router = APIRouter(tags=["payments"])


@router.get("/bills")
def list_bills(session: SessionDep, user: UserDep) -> list[BillOut]:
    """The user's bills, soonest due first."""
    today = demo_today()
    bills = session.scalars(
        select(Bill)
        .where(Bill.user_id == user.id)
        .options(selectinload(Bill.payee))
        .order_by(Bill.due_date, Bill.id)
    )
    return [
        BillOut(
            id=bill.id,
            payee_id=bill.payee_id,
            payee_name=bill.payee.name,
            amount_minor=bill.amount_minor,
            currency=bill.currency,
            due_date=bill.due_date,
            due_in_days=(bill.due_date - today).days,
            late_fee_terms=bill.late_fee_terms,
            status=bill.status,
        )
        for bill in bills
    ]


@router.get("/payees")
def list_payees(session: SessionDep, user: UserDep) -> list[PayeeOut]:
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
            cooling_off_until=payee.cooling_off_until,
        )
        for payee in payees
    ]
