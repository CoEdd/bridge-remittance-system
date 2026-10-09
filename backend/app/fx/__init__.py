"""Mid-market FX rates. Fetched once at each demo reset, then frozen."""

import json
import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import FxQuote

logger = logging.getLogger(__name__)

# ECB reference rates. api.frankfurter.app redirects here.
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
HOME_CURRENCY = "MYR"
QUOTE_CURRENCIES = ("CNY", "USD")

# Used when FX_OFFLINE=true or the request fails: units per 1 MYR.
OFFLINE_SNAPSHOT: dict[str, Decimal] = {"CNY": Decimal("1.62"), "USD": Decimal("0.23")}

_INVERSE_PLACES = Decimal("0.0000000001")

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
