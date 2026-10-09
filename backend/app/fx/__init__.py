"""Mid-market FX rates. Fetched once at each demo reset, then frozen."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, ROUND_UP, Decimal
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import FxQuote, Provider
from app.money import convert

logger = logging.getLogger(__name__)

# ECB reference rates. api.frankfurter.app redirects here.
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
HOME_CURRENCY = "MYR"
QUOTE_CURRENCIES = ("CNY", "USD")

# Used when FX_OFFLINE=true or the request fails: units per 1 MYR.
OFFLINE_SNAPSHOT: dict[str, Decimal] = {"CNY": Decimal("1.62"), "USD": Decimal("0.23")}

# The one simulated transfer service only sells MYR for CNY.
SUPPORTED_CONVERSIONS = {("MYR", "CNY")}

_INVERSE_PLACES = Decimal("0.0000000001")
_HUNDRED = Decimal(100)

Rates = dict[str, Decimal]


class FxError(RuntimeError):
    pass


def fetch_frankfurter(client: httpx.Client | None = None) -> Rates:
    """Ask Frankfurter for 1 MYR in CNY and USD. Numbers are parsed straight to Decimal."""
    params = {"from": HOME_CURRENCY, "to": ",".join(QUOTE_CURRENCIES)}
    get = client.get if client else httpx.get
    response = get(FRANKFURTER_URL, params=params, timeout=5.0, follow_redirects=True)
    response.raise_for_status()
    body = json.loads(response.text, parse_float=Decimal, parse_int=Decimal)
    if body["base"] != HOME_CURRENCY:
        raise ValueError("Frankfurter answered for a different base currency.")
    rates = {currency: body["rates"][currency] for currency in QUOTE_CURRENCIES}
    if any(not isinstance(rate, Decimal) or rate <= 0 for rate in rates.values()):
        raise ValueError("Frankfurter returned a rate that is not a positive number.")
    return rates


def freeze_rates(
    session: Session,
    *,
    offline: bool,
    now: datetime,
    fetch: Callable[[], Rates] = fetch_frankfurter,
) -> str:
    """
    Replace the stored quotes with fresh ones and return their source.

    Each pair is stored in both directions; the inverse is derived from the same
    fetched number so the two directions always agree.
    """
    rates, source = OFFLINE_SNAPSHOT, "offline_snapshot"
    if not offline:
        try:
            rates, source = fetch(), "frankfurter"
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ArithmeticError) as error:
            logger.warning("Frankfurter request failed (%s); using the offline snapshot.", error)

    session.execute(delete(FxQuote))
    for currency in QUOTE_CURRENCIES:
        rate = rates[currency]
        inverse = (Decimal(1) / rate).quantize(_INVERSE_PLACES)
        for base, quote, mid_rate in (
            (HOME_CURRENCY, currency, rate),
            (currency, HOME_CURRENCY, inverse),
        ):
            session.add(
                FxQuote(base=base, quote=quote, mid_rate=str(mid_rate), source=source, fetched_at=now)
            )
    session.flush()
    return source


def get_quote(session: Session, base: str, quote: str) -> FxQuote:
    """The frozen quote for a pair, with its source and time."""
    found = session.scalars(
        select(FxQuote).where(FxQuote.base == base, FxQuote.quote == quote)
    ).one_or_none()
    if found is None:
        raise FxError(f"No frozen rate for {base} to {quote}.")
    return found


def get_mid_rate(session: Session, base: str, quote: str) -> Decimal:
    """Frozen mid-market rate: units of `quote` per 1 `base`."""
    if base == quote:
        return Decimal(1)
    return get_quote(session, base, quote).rate


@dataclass(frozen=True)
class TransferQuote:
    """What one conversion costs with the simulated transfer service, in full."""

    provider_id: int
    provider_name: str
    from_currency: str
    to_currency: str
    amount_minor: int  # sold, in from_currency
    mid_rate: Decimal
    offered_rate: Decimal  # mid x (1 - markup)
    markup_pct: Decimal
    fee_minor: int  # in from_currency
    markup_cost_minor: int  # amount x markup, in from_currency
    total_cost_minor: int  # fee + markup cost
    total_debit_minor: int  # amount + fee: what leaves the wallet
    amount_received_minor: int  # in to_currency, rounded down
    received_at_mid_minor: int  # what the mid-market rate would have given
    delivery_hours: int
    arrives_at: datetime

    def as_breakdown(self) -> dict[str, Any]:
        """Plain JSON form, stored with the pending action and shown on the approval sheet."""
        return {
            "kind": "conversion",
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "from_currency": self.from_currency,
            "to_currency": self.to_currency,
            "amount_minor": self.amount_minor,
            "mid_rate": str(self.mid_rate),
            "offered_rate": str(self.offered_rate),
            "markup_pct": str(self.markup_pct),
            "fee_minor": self.fee_minor,
            "markup_cost_minor": self.markup_cost_minor,
            "total_cost_minor": self.total_cost_minor,
            "total_debit_minor": self.total_debit_minor,
            "amount_received_minor": self.amount_received_minor,
            "received_at_mid_minor": self.received_at_mid_minor,
            "delivery_hours": self.delivery_hours,
            "arrives_at": self.arrives_at.isoformat(),
        }


def _percent_of(amount_minor: int, percent: Decimal, rounding: str) -> int:
    return int((Decimal(amount_minor) * percent / _HUNDRED).to_integral_value(rounding=rounding))


def transfer_quote(
    session: Session, provider: Provider, from_currency: str, to_currency: str, amount_minor: int, now: datetime
) -> TransferQuote:
    """The true cost of converting `amount_minor`: the fee plus what the rate markup costs."""
    if (from_currency, to_currency) not in SUPPORTED_CONVERSIONS or provider.fee_currency != from_currency:
        raise FxError(f"{provider.name} does not convert {from_currency} to {to_currency}.")
    mid_rate = get_mid_rate(session, from_currency, to_currency)
    markup_pct = Decimal(provider.markup_pct)
    offered_rate = mid_rate * (1 - markup_pct / _HUNDRED)
    fee_minor = provider.fee_fixed_minor + _percent_of(amount_minor, Decimal(provider.fee_pct), ROUND_UP)
    markup_cost_minor = _percent_of(amount_minor, markup_pct, ROUND_HALF_UP)
    return TransferQuote(
        provider_id=provider.id,
        provider_name=provider.name,
        from_currency=from_currency,
        to_currency=to_currency,
        amount_minor=amount_minor,
        mid_rate=mid_rate,
        offered_rate=offered_rate,
        markup_pct=markup_pct,
        fee_minor=fee_minor,
        markup_cost_minor=markup_cost_minor,
        total_cost_minor=fee_minor + markup_cost_minor,
        total_debit_minor=amount_minor + fee_minor,
        amount_received_minor=convert(amount_minor, offered_rate),
        received_at_mid_minor=convert(amount_minor, mid_rate),
        delivery_hours=provider.delivery_hours,
        arrives_at=now + timedelta(hours=provider.delivery_hours),
    )
