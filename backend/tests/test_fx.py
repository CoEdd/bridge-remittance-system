from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fx import FxError, fetch_frankfurter, freeze_rates, get_mid_rate, get_quote
from app.models import FxQuote

NOW = datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)
FRANKFURTER_BODY = '{"amount":1.0,"base":"MYR","date":"2026-10-08","rates":{"CNY":1.6381,"USD":0.24441}}'


def client_answering(status: int, body: str) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, text=body)))


def test_reset_with_fx_offline_freezes_the_snapshot(session: Session) -> None:
    quotes = session.scalars(select(FxQuote).order_by(FxQuote.id)).all()

    assert [(quote.base, quote.quote) for quote in quotes] == [
        ("MYR", "CNY"),
        ("CNY", "MYR"),
        ("MYR", "USD"),
        ("USD", "MYR"),
    ]
    assert {quote.source for quote in quotes} == {"offline_snapshot"}
    assert get_mid_rate(session, "MYR", "CNY") == Decimal("1.62")
    assert get_mid_rate(session, "MYR", "USD") == Decimal("0.23")
    assert get_mid_rate(session, "CNY", "MYR") == Decimal("0.6172839506")
    assert get_mid_rate(session, "MYR", "MYR") == Decimal(1)


def test_quote_exposes_rate_source_and_time(session: Session) -> None:
    quote = get_quote(session, "MYR", "CNY")

    assert quote.rate == Decimal("1.62")
    assert quote.source == "offline_snapshot"
    assert quote.fetched_at.tzinfo is timezone.utc


def test_frankfurter_numbers_are_parsed_as_exact_decimals() -> None:
    rates = fetch_frankfurter(client_answering(200, FRANKFURTER_BODY))

    assert rates == {"CNY": Decimal("1.6381"), "USD": Decimal("0.24441")}
    assert all(isinstance(rate, Decimal) for rate in rates.values())


def test_live_rates_are_frozen_with_their_source(session: Session) -> None:
    source = freeze_rates(
        session, offline=False, now=NOW, fetch=lambda: fetch_frankfurter(client_answering(200, FRANKFURTER_BODY))
    )

    assert source == "frankfurter"
    assert get_mid_rate(session, "MYR", "CNY") == Decimal("1.6381")
    assert get_quote(session, "MYR", "USD").source == "frankfurter"
    assert get_quote(session, "MYR", "USD").fetched_at == NOW
    # The stored inverse agrees with the fetched rate to ten decimal places.
    assert abs(get_mid_rate(session, "CNY", "MYR") * Decimal("1.6381") - 1) < Decimal("0.000000001")


@pytest.mark.parametrize(
    "status, body",
    [
        (500, "server error"),
        (200, "not json"),
        (200, '{"base":"MYR","rates":{"CNY":1.6381}}'),  # USD missing
        (200, '{"base":"MYR","rates":{"CNY":0,"USD":0.24}}'),  # zero rate
        (200, '{"base":"EUR","rates":{"CNY":7.7,"USD":1.1}}'),  # wrong base
    ],
)
def test_a_failed_or_bad_answer_falls_back_to_the_snapshot(session: Session, status: int, body: str) -> None:
    source = freeze_rates(
        session, offline=False, now=NOW, fetch=lambda: fetch_frankfurter(client_answering(status, body))
    )

    assert source == "offline_snapshot"
    assert get_mid_rate(session, "MYR", "CNY") == Decimal("1.62")


def test_a_network_error_falls_back_to_the_snapshot(session: Session) -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network", request=request)

    client = httpx.Client(transport=httpx.MockTransport(unreachable))
    source = freeze_rates(session, offline=False, now=NOW, fetch=lambda: fetch_frankfurter(client))

    assert source == "offline_snapshot"


def test_offline_mode_never_calls_frankfurter(session: Session) -> None:
    def must_not_run() -> dict[str, Decimal]:
        raise AssertionError("fetch was called although FX_OFFLINE is true")

    assert freeze_rates(session, offline=True, now=NOW, fetch=must_not_run) == "offline_snapshot"


def test_asking_for_a_pair_that_was_not_frozen_fails(session: Session) -> None:
    with pytest.raises(FxError):
        get_mid_rate(session, "CNY", "USD")
