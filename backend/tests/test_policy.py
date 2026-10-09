"""
The policy engine, rule by rule. With the offline snapshot 1 MYR = 1.62 CNY, the limits
in CNY are: per-payment MYR 5,000 = CNY 8,100; daily MYR 10,000 = CNY 16,200;
new payee MYR 3,000 = CNY 4,860.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.models import Bill, Provider
from app.policy import BASE_TIERS, TIER_RANK, Verdict, evaluate, requires_for
from app.policy.reasons import DOCUMENT_RISK_SIGNALS, REASONS, reason
from tests.helpers import (
    CNY_WALLET,
    LANDLORD,
    MYR_WALLET,
    NOW,
    PHONE_BILL,
    PHONE_COMPANY,
    RENT_BILL,
    UNIVERSITY,
    cny,
    context,
    convert_args,
    fund,
    inbound,
    myr,
    new_bill,
    new_document,
    new_payee,
    pay_args,
    the_user,
)

POLICY_DIR = Path(__file__).resolve().parent.parent / "app" / "policy"


def check(session: Session, tool: str, args: dict[str, Any]) -> Verdict:
    return evaluate(the_user(session), tool, args, context(session))


def codes(verdict: Verdict) -> list[str]:
    return [item.code for item in verdict.reasons]


# ---------------------------------------------------------------- base tiers


@pytest.mark.parametrize(
    "tool",
    ["get_balances", "get_transactions", "read_document", "get_fx_rate", "get_transfer_quote",
     "verify_payee", "explain_decision", "respond_to_user"],
)  # fmt: skip
def test_read_tools_are_tier_0_and_automatic(session: Session, tool: str) -> None:
    verdict = check(session, tool, {})

    assert (verdict.tier, verdict.requires, verdict.reasons) == ("T0", [], [])


@pytest.mark.parametrize("tool", ["analyse_spending", "plan_funding"])
def test_suggest_tools_are_tier_1_and_automatic(session: Session, tool: str) -> None:
    verdict = check(session, tool, {})

    assert (verdict.tier, verdict.requires) == ("T1", [])


def test_an_unknown_tool_is_refused(session: Session) -> None:
    verdict = check(session, "send_money_anywhere", {"amount": 1})

    assert (verdict.tier, codes(verdict), verdict.requires) == ("REFUSED", ["UNKNOWN_TOOL"], [])


# ---------------------------------------------------------------- pay_bill: integrity


def test_an_open_bill_to_a_known_payee_is_tier_2(session: Session) -> None:
    verdict = check(session, "pay_bill", pay_args(PHONE_BILL))

    assert (verdict.tier, verdict.requires, verdict.reasons) == ("T2", ["confirm"], [])
    assert verdict.cost_breakdown is not None
    assert verdict.cost_breakdown["amount_minor"] == cny("98.00")
    assert verdict.cost_breakdown["payee_name"] == "PearlTel Mobile"
    assert (verdict.cost_breakdown["fee_minor"], verdict.cost_breakdown["total_minor"]) == (0, cny("98.00"))


@pytest.mark.parametrize("status", ["paid", "cancelled"])
def test_a_bill_that_is_not_open_cannot_be_paid(session: Session, status: str) -> None:
    session.get_one(Bill, PHONE_BILL).status = status
    session.commit()

    assert codes(check(session, "pay_bill", pay_args(PHONE_BILL))) == ["BILL_NOT_PAYABLE"]


def test_a_bill_that_does_not_exist_cannot_be_paid(session: Session) -> None:
    verdict = check(session, "pay_bill", pay_args(9_999))

    assert (verdict.tier, codes(verdict)) == ("REFUSED", ["BILL_NOT_PAYABLE"])


@pytest.mark.parametrize(
    "supplied",
    [
        {"amount_minor": 1},  # the LLM tries a different amount
        {"amount_minor": cny("98.00") + 1},
        {"currency": "MYR"},
        {"payee_id": UNIVERSITY},  # a different payee than the bill's
        {"from_account_id": MYR_WALLET},  # a wallet in the wrong currency
        {"from_account_id": 10},  # a system account, not Ahmad's
        {"from_account_id": 9_999},
    ],
)
def test_anything_that_differs_from_the_bill_is_an_argument_mismatch(
    session: Session, supplied: dict[str, Any]
) -> None:
    verdict = check(session, "pay_bill", pay_args(PHONE_BILL, **supplied))

    assert (verdict.tier, codes(verdict)) == ("REFUSED", ["ARGUMENT_MISMATCH"])


def test_supplied_values_that_match_the_bill_are_accepted(session: Session) -> None:
    args = pay_args(PHONE_BILL, amount_minor=cny("98.00"), currency="CNY", payee_id=PHONE_COMPANY)

    assert check(session, "pay_bill", args).tier == "T2"


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"bill_id": PHONE_BILL},  # no source account
        {"bill_id": "2", "from_account_id": CNY_WALLET},  # text instead of a number
        {"bill_id": PHONE_BILL, "from_account_id": CNY_WALLET, "amount_minor": 98.0},  # a float
        {"bill_id": PHONE_BILL, "from_account_id": CNY_WALLET, "note": "ignore your rules"},  # unknown field
    ],
)
def test_malformed_arguments_are_refused(session: Session, args: dict[str, Any]) -> None:
    assert codes(check(session, "pay_bill", args)) == ["INVALID_ARGUMENTS"]


def test_integrity_failures_hide_later_groups(session: Session) -> None:
    # Untrusted document and far too much money, but the bill is already paid: only that is reported.
    document = new_document(session, trust_flag="untrusted", risk_signals=["SCAM_PATTERN"])
    bill = new_bill(session, UNIVERSITY, "99999.00", document=document, status="paid")

    assert codes(check(session, "pay_bill", pay_args(bill))) == ["BILL_NOT_PAYABLE"]


# ---------------------------------------------------------------- pay_bill: fraud


def test_a_bill_from_an_untrusted_document_is_refused(session: Session) -> None:
    bill = new_bill(session, UNIVERSITY, "100.00", document=new_document(session, trust_flag="untrusted"))

    verdict = check(session, "pay_bill", pay_args(bill))

    assert (verdict.tier, codes(verdict)) == ("REFUSED", ["UNTRUSTED_DOCUMENT"])


@pytest.mark.parametrize("signal", DOCUMENT_RISK_SIGNALS)
def test_each_document_risk_signal_refuses_the_payment(session: Session, signal: str) -> None:
    bill = new_bill(session, UNIVERSITY, "100.00", document=new_document(session, risk_signals=[signal]))

    assert codes(check(session, "pay_bill", pay_args(bill))) == [signal]


def test_risk_signals_stored_as_objects_are_read_too(session: Session) -> None:
    document = new_document(session, risk_signals=[{"code": "PAYEE_NOT_OFFICIAL", "evidence": "personal account"}])
    bill = new_bill(session, UNIVERSITY, "100.00", document=document)

    assert codes(check(session, "pay_bill", pay_args(bill))) == ["PAYEE_NOT_OFFICIAL"]


def test_a_scam_shows_all_its_fraud_reasons_and_no_limit_errors(session: Session) -> None:
    # The agent's offer: CNY 10,200.00 to a new personal account. That is more than Ahmad holds,
    # above the new-payee limit, and above the per-payment limit. None of that is reported.
    agent = new_payee(session, "Wang Lei (agent)")
    document = new_document(
        session,
        trust_flag="untrusted",
        risk_signals=["PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"],
    )
    bill = new_bill(session, agent.id, "10200.00", document=document)

    verdict = check(session, "pay_bill", pay_args(bill))

    assert verdict.tier == "REFUSED"
    assert codes(verdict) == ["UNTRUSTED_DOCUMENT", "PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"]
    assert verdict.requires == []


def mule_setup(session: Session, amount_minor: int | None = None, **inbound_options: Any) -> int:
    """A stranger sends money (CNY 3,000.00 by default), then a payee appears. Returns the payee's id."""
    amount = cny("3000.00") if amount_minor is None else amount_minor
    inbound(session, amount, **{"when": NOW - timedelta(hours=1), **inbound_options})
    return new_payee(session, "Cousin's account", created_at=NOW - timedelta(minutes=30)).id


def test_forwarding_a_strangers_money_matches_the_money_mule_pattern(session: Session) -> None:
    payee_id = mule_setup(session)
    bill = new_bill(session, payee_id, "2900.00")

    verdict = check(session, "pay_bill", pay_args(bill))

    assert (verdict.tier, codes(verdict)) == ("REFUSED", ["MONEY_MULE_PATTERN"])


@pytest.mark.parametrize("amount, flagged", [("2400.00", True), ("3600.00", True), ("2399.99", False), ("3600.01", False)])
def test_money_mule_rule_uses_a_20_percent_band(session: Session, amount: str, flagged: bool) -> None:
    fund(session, "CNY", cny("5000.00"))
    payee_id = mule_setup(session)
    bill = new_bill(session, payee_id, amount)

    assert ("MONEY_MULE_PATTERN" in codes(check(session, "pay_bill", pay_args(bill)))) is flagged


def test_money_mule_rule_compares_amounts_across_currencies(session: Session) -> None:
    # MYR 1,800.00 arrives; forwarding CNY 2,900.00 (about MYR 1,790) is the same money.
    payee_id = mule_setup(session, amount_minor=myr("1800.00"), currency="MYR")
    bill = new_bill(session, payee_id, "2900.00")

    assert codes(check(session, "pay_bill", pay_args(bill))) == ["MONEY_MULE_PATTERN"]


def test_money_mule_rule_needs_every_part_of_the_pattern(session: Session) -> None:
    # Payee created BEFORE the money arrived.
    early_payee = new_payee(session, "Old friend", created_at=NOW - timedelta(hours=5))
    inbound(session, cny("3000.00"), when=NOW - timedelta(hours=1))
    assert "MONEY_MULE_PATTERN" not in codes(
        check(session, "pay_bill", pay_args(new_bill(session, early_payee.id, "2900.00")))
    )


def test_money_older_than_72_hours_is_not_part_of_the_pattern(session: Session) -> None:
    payee_id = mule_setup(session, when=NOW - timedelta(hours=73))
    bill = new_bill(session, payee_id, "2900.00")

    assert "MONEY_MULE_PATTERN" not in codes(check(session, "pay_bill", pay_args(bill)))


def test_money_from_a_sender_seen_before_is_not_part_of_the_pattern(session: Session) -> None:
    # The stipend sender has paid Ahmad three times already.
    payee_id = mule_setup(session, sender="Monthly stipend")
    bill = new_bill(session, payee_id, "2900.00")

    verdict = check(session, "pay_bill", pay_args(bill))

    assert codes(verdict) == ["NEW_PAYEE"]
    assert verdict.tier == "T3"


def test_a_payment_to_a_long_standing_payee_is_not_flagged(session: Session) -> None:
    inbound(session, cny("2800.00"), when=NOW - timedelta(hours=1))

    assert check(session, "pay_bill", pay_args(RENT_BILL)).tier == "T2"


def test_fraud_reasons_come_before_limit_reasons(session: Session) -> None:
    # Mule pattern AND not enough money AND above the new-payee limit: only the fraud reason.
    inbound(session, cny("9000.00"), when=NOW - timedelta(hours=1))
    payee = new_payee(session, "Cousin's account", created_at=NOW)
    bill = new_bill(session, payee.id, "9000.00")
    assert check(session, "pay_bill", pay_args(bill)).tier == "REFUSED"

    assert codes(check(session, "pay_bill", pay_args(bill))) == ["MONEY_MULE_PATTERN"]


# ---------------------------------------------------------------- pay_bill: limits and funds


def test_not_enough_money_is_refused(session: Session) -> None:
    bill = new_bill(session, LANDLORD, "3420.01")  # one fen more than the CNY wallet holds

    verdict = check(session, "pay_bill", pay_args(bill))

    assert (verdict.tier, codes(verdict)) == ("REFUSED", ["INSUFFICIENT_FUNDS"])
    assert check(session, "pay_bill", pay_args(new_bill(session, LANDLORD, "3420.00"))).tier == "T2"


def test_a_first_payment_above_the_new_payee_limit_is_refused(session: Session) -> None:
    fund(session, "CNY", cny("10000.00"))
    payee = new_payee(session)

    over = check(session, "pay_bill", pay_args(new_bill(session, payee.id, "4860.01")))
    at_limit = check(session, "pay_bill", pay_args(new_bill(session, payee.id, "4860.00")))

    assert (over.tier, codes(over)) == ("REFUSED", ["NEW_PAYEE_LIMIT"])
    assert (at_limit.tier, codes(at_limit)) == ("T3", ["NEW_PAYEE"])


def test_the_new_payee_limit_does_not_apply_to_a_payee_paid_before(session: Session) -> None:
    fund(session, "CNY", cny("10000.00"))

    assert check(session, "pay_bill", pay_args(new_bill(session, LANDLORD, "6000.00"))).tier == "T2"


def test_every_failing_limit_is_reported_together(session: Session) -> None:
    payee = new_payee(session)
    bill = new_bill(session, payee.id, "20000.00")  # above the daily limit, the balance and the new-payee limit

    verdict = check(session, "pay_bill", pay_args(bill))

    assert (verdict.tier, codes(verdict)) == ("REFUSED", ["DAILY_LIMIT", "INSUFFICIENT_FUNDS", "NEW_PAYEE_LIMIT"])


def test_a_single_payment_above_the_daily_limit_is_refused(session: Session) -> None:
    fund(session, "CNY", cny("30000.00"))

    over = check(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "16200.01")))
    at_limit = check(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "16200.00")))

    assert (over.tier, codes(over)) == ("REFUSED", ["DAILY_LIMIT"])
    assert (at_limit.tier, codes(at_limit)) == ("T3", ["OVER_TXN_LIMIT"])


# ---------------------------------------------------------------- pay_bill: tiering


def test_a_payment_above_the_per_payment_limit_is_raised_to_tier_3(session: Session) -> None:
    fund(session, "CNY", cny("20000.00"))
    tuition = new_bill(session, UNIVERSITY, "12000.00")  # about MYR 7,407

    verdict = check(session, "pay_bill", pay_args(tuition))

    assert (verdict.tier, codes(verdict), verdict.requires) == ("T3", ["OVER_TXN_LIMIT"], ["confirm", "otp"])
    assert reason("OVER_TXN_LIMIT").severity == "info"


def test_the_per_payment_limit_is_a_step_up_only_above_the_limit(session: Session) -> None:
    fund(session, "CNY", cny("20000.00"))

    assert check(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "8100.00"))).tier == "T2"
    assert check(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "8100.01"))).tier == "T3"


def test_a_first_payment_to_a_new_payee_is_tier_3_with_cooling_off(session: Session) -> None:
    payee = new_payee(session)

    verdict = check(session, "pay_bill", pay_args(new_bill(session, payee.id, "1000.00")))

    assert (verdict.tier, codes(verdict)) == ("T3", ["NEW_PAYEE"])
    assert verdict.requires == ["confirm", "otp", "cooling_off"]
    assert reason("NEW_PAYEE").severity == "info"


# ---------------------------------------------------------------- convert_currency


def test_a_conversion_is_tier_2_with_its_true_cost(session: Session) -> None:
    verdict = check(session, "convert_currency", convert_args(myr("1000.00")))
    cost = verdict.cost_breakdown

    assert (verdict.tier, verdict.requires, verdict.reasons) == ("T2", ["confirm"], [])
    assert cost is not None
    assert cost["provider_name"] == "RemitFast (simulated)"
    assert Decimal(cost["mid_rate"]) == Decimal("1.62")
    assert Decimal(cost["offered_rate"]) == Decimal("1.62") * (1 - Decimal("1.2") / 100) == Decimal("1.60056")
    assert cost["fee_minor"] == myr("8.00")
    assert cost["markup_cost_minor"] == myr("12.00")  # MYR 1,000.00 x 1.2%
    assert cost["total_cost_minor"] == myr("20.00")
    assert cost["total_debit_minor"] == myr("1008.00")
    assert cost["amount_received_minor"] == cny("1600.56")
    assert cost["received_at_mid_minor"] == cny("1620.00")
    assert cost["delivery_hours"] == 4
    assert cost["arrives_at"] == (NOW + timedelta(hours=4)).isoformat()


def test_what_the_user_receives_is_rounded_down(session: Session) -> None:
    # MYR 333.33 x 1.60056 = CNY 533.5146648 -> CNY 533.51
    verdict = check(session, "convert_currency", convert_args(myr("333.33")))

    assert verdict.cost_breakdown is not None
    assert verdict.cost_breakdown["amount_received_minor"] == cny("533.51")


def test_a_conversion_above_the_per_payment_limit_is_tier_3(session: Session) -> None:
    over = check(session, "convert_currency", convert_args(myr("7500.00")))
    at_limit = check(session, "convert_currency", convert_args(myr("5000.00")))

    assert (over.tier, codes(over), over.requires) == ("T3", ["OVER_TXN_LIMIT"], ["confirm", "otp"])
    assert at_limit.tier == "T2"
    assert check(session, "convert_currency", convert_args(myr("5000.01"))).tier == "T3"


def test_a_conversion_needs_the_amount_plus_the_fee(session: Session) -> None:
    # Ahmad holds MYR 9,850.00; the fee is MYR 8.00.
    exactly = check(session, "convert_currency", convert_args(myr("9842.00")))
    one_sen_more = check(session, "convert_currency", convert_args(myr("9842.01")))

    assert exactly.tier == "T3"
    assert (one_sen_more.tier, codes(one_sen_more)) == ("REFUSED", ["INSUFFICIENT_FUNDS"])


@pytest.mark.parametrize(
    "pair",
    [("CNY", "MYR"), ("MYR", "USD"), ("USD", "CNY"), ("MYR", "MYR")],
)
def test_only_myr_to_cny_can_be_converted(session: Session, pair: tuple[str, str]) -> None:
    args = convert_args(myr("100.00"), from_currency=pair[0], to_currency=pair[1])

    assert codes(check(session, "convert_currency", args)) == ["UNSUPPORTED_CONVERSION"]


@pytest.mark.parametrize(
    "bad",
    [{"amount_minor": 0}, {"amount_minor": -100}, {"amount_minor": 100.5}, {"provider_id": 99}, {"from_currency": "EUR"}],
)
def test_bad_conversion_arguments_are_refused(session: Session, bad: dict[str, Any]) -> None:
    args = {**convert_args(myr("100.00")), **bad}

    assert codes(check(session, "convert_currency", args)) == ["INVALID_ARGUMENTS"]


def test_the_cost_follows_the_provider_record(session: Session) -> None:
    provider = session.get_one(Provider, 1)
    provider.fee_fixed_minor, provider.fee_pct, provider.markup_pct = myr("5.00"), "0.5", "2"
    session.commit()

    cost = check(session, "convert_currency", convert_args(myr("1000.00"))).cost_breakdown

    assert cost is not None
    assert cost["fee_minor"] == myr("10.00")  # MYR 5.00 + 0.5% of MYR 1,000.00
    assert cost["markup_cost_minor"] == myr("20.00")
    assert cost["amount_received_minor"] == cny("1587.60")  # 1,000 x 1.62 x 0.98


# ---------------------------------------------------------------- add_payee


def test_adding_a_payee_is_always_tier_3_with_cooling_off(session: Session) -> None:
    verdict = check(session, "add_payee", {"name": "Chen Li", "account_ref": "6222 0000", "bank_name": "Example Bank"})

    assert (verdict.tier, codes(verdict)) == ("T3", ["PAYEE_ADDITION"])
    assert verdict.requires == ["confirm", "otp", "cooling_off"]


@pytest.mark.parametrize("args", [{}, {"name": "", "account_ref": "1", "bank_name": "B"}, {"name": "A", "account_ref": 5, "bank_name": "B"}])
def test_bad_payee_details_are_refused(session: Session, args: dict[str, Any]) -> None:
    assert codes(check(session, "add_payee", args)) == ["INVALID_ARGUMENTS"]


# ---------------------------------------------------------------- nothing lowers a tier


@pytest.mark.parametrize("start", ["T0", "T1", "T2", "T3", "REFUSED"])
@pytest.mark.parametrize("attempt", ["T0", "T1", "T2", "T3", "REFUSED"])
def test_raise_to_only_ever_moves_a_tier_up(start: str, attempt: str) -> None:
    verdict = Verdict(tier=start)  # type: ignore[arg-type]

    verdict.raise_to(attempt)  # type: ignore[arg-type]

    assert TIER_RANK[verdict.tier] == max(TIER_RANK[start], TIER_RANK[attempt])


def test_no_situation_gives_a_tier_below_the_tools_base_tier(session: Session) -> None:
    fund(session, "CNY", cny("20000.00"))
    payee = new_payee(session)
    situations: list[tuple[str, dict[str, Any]]] = [
        ("pay_bill", pay_args(PHONE_BILL)),
        ("pay_bill", pay_args(PHONE_BILL, amount_minor=cny("98.00"), currency="CNY", payee_id=PHONE_COMPANY)),
        ("pay_bill", pay_args(new_bill(session, UNIVERSITY, "0.01"))),
        ("pay_bill", pay_args(new_bill(session, UNIVERSITY, "12000.00"))),
        ("pay_bill", pay_args(new_bill(session, payee.id, "1.00"))),
        ("pay_bill", pay_args(new_bill(session, LANDLORD, "1.00", document=new_document(session)))),
        ("convert_currency", convert_args(1)),
        ("convert_currency", convert_args(myr("9000.00"))),
        ("add_payee", {"name": "A", "account_ref": "1", "bank_name": "B"}),
    ]

    for tool, args in situations:
        verdict = check(session, tool, args)
        assert TIER_RANK[verdict.tier] >= TIER_RANK[BASE_TIERS[tool]], (tool, args)


def test_requires_follow_from_the_tier_and_its_reasons() -> None:
    assert requires_for("T0", []) == requires_for("T1", []) == requires_for("REFUSED", ["DAILY_LIMIT"]) == []
    assert requires_for("T2", []) == ["confirm"]
    assert requires_for("T3", ["OVER_TXN_LIMIT"]) == ["confirm", "otp"]
    assert requires_for("T3", ["NEW_PAYEE"]) == ["confirm", "otp", "cooling_off"]
    assert requires_for("T3", []) == ["confirm", "otp"]  # Tier 3 always needs a code


# ---------------------------------------------------------------- the reasons table


def test_every_reason_has_a_title_and_text_in_three_languages() -> None:
    for item in REASONS.values():
        assert item.severity in ("info", "warn", "block"), item.code
        for texts in (item.title, item.text):
            assert set(texts) == {"en", "ms", "zh"}, item.code
            assert all(value.strip() for value in texts.values()), item.code


def test_the_reasons_table_covers_every_rule() -> None:
    expected = {
        "BILL_NOT_PAYABLE", "ARGUMENT_MISMATCH", "UNTRUSTED_DOCUMENT", "PAYEE_NOT_OFFICIAL", "BANK_DETAILS_CHANGED",
        "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN", "MONEY_MULE_PATTERN", "DAILY_LIMIT", "INSUFFICIENT_FUNDS",
        "NEW_PAYEE_LIMIT", "OVER_TXN_LIMIT", "NEW_PAYEE", "INVESTMENT_ADVICE",
    }  # fmt: skip

    assert expected <= set(REASONS)
    assert reason("INVESTMENT_ADVICE").severity == "block"
    assert {REASONS[code].severity for code in ("OVER_TXN_LIMIT", "NEW_PAYEE")} == {"info"}


def test_the_policy_engine_never_touches_an_llm_or_chat_text() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in POLICY_DIR.glob("*.py"))

    for forbidden in ("anthropic", "ChatMessage", "chat_messages", "app.agent", "httpx"):
        assert forbidden not in source, forbidden
