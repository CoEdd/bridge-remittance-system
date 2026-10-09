from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.clock import demo_today
from app.fx import HOME_CURRENCY, QUOTE_CURRENCIES, get_mid_rate, get_quote
from app.models import Account, Entry, Posting
from app.money import Currency, convert
from app.planner.spending import analyse_spending, category_label
from app.routers.deps import SessionDep, UserDep
from app.schemas import (
    AccountOut,
    AccountsOut,
    AmountOut,
    RateOut,
    SpendingInsightsOut,
    TransactionOut,
)

router = APIRouter(tags=["accounts"])


@router.get("/accounts")
def list_accounts(session: SessionDep, user: UserDep) -> AccountsOut:
    """Wallet balances with their home-currency equivalents at the frozen mid-market rate."""
    wallets = session.scalars(
        select(Account).where(Account.user_id == user.id).order_by(Account.id)
    ).all()
    accounts = []
    for wallet in wallets:
        rate = None
        if wallet.currency != user.home_currency:
            quote = get_quote(session, user.home_currency, wallet.currency)
            rate = RateOut(
                base=quote.base,
                quote=quote.quote,
                mid_rate=quote.mid_rate,
                source=quote.source,
                fetched_at=quote.fetched_at,
            )
        to_home = get_mid_rate(session, wallet.currency, user.home_currency)
        accounts.append(
            AccountOut(
                id=wallet.id,
                currency=wallet.currency,
                name=wallet.name,
                balance_minor=wallet.balance_minor,
                home_equivalent_minor=convert(wallet.balance_minor, to_home),
                rate=rate,
            )
        )
    source = get_quote(session, HOME_CURRENCY, QUOTE_CURRENCIES[0]).source
    return AccountsOut(home_currency=user.home_currency, fx_source=source, accounts=accounts)


@router.get("/transactions")
def list_transactions(
    session: SessionDep,
    user: UserDep,
    currency: Currency | None = None,
    category: str | None = None,
    days: Annotated[int | None, Query(ge=1, le=366)] = None,
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
) -> list[TransactionOut]:
    """The user's postings, newest first. `days` counts back from the demo date."""
    user_entries = (
        select(Entry.posting_id)
        .join(Account, Entry.account_id == Account.id)
        .where(Account.user_id == user.id)
    )
    if currency:
        user_entries = user_entries.where(Entry.currency == currency)

    query = (
        select(Posting)
        .where(Posting.id.in_(user_entries))
        .options(selectinload(Posting.entries).selectinload(Entry.account))
        .order_by(Posting.business_date.desc(), Posting.id.desc())
    )
    if category:
        query = query.where(Posting.category == category)
    if days:
        query = query.where(Posting.business_date > demo_today() - timedelta(days=days))
    if limit:
        query = query.limit(limit)

    return [
        TransactionOut(
            id=posting.id,
            business_date=posting.business_date,
            created_at=posting.created_at,
            kind=posting.kind,
            category=posting.category,
            category_label=category_label(posting.category),
            counterparty=posting.counterparty,
            description=posting.description,
            amounts=[
                AmountOut(currency=entry.currency, amount_minor=entry.amount_minor)
                for entry in posting.entries
                if entry.account.user_id == user.id
            ],
        )
        for posting in session.scalars(query)
    ]


@router.get("/insights/spending")
def spending_insights(session: SessionDep, user: UserDep) -> SpendingInsightsOut:
    """Category totals for the last 30 days, change against the 30 before, and one insight."""
    return SpendingInsightsOut.model_validate(analyse_spending(session, user, demo_today()))
