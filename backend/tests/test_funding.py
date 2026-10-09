"""The transfer quote, the funding planner, and how a plan's steps depend on each other."""

from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import actions
from app.actions import ActionError
from app.config import get_settings
from app.fx import HIGH_MARKUP_WARNING, FxError, get_transfer_quote, quote_to_receive
from app.models import Bill, FxQuote, PendingAction, Provider
from app.planner.funding import plan_funding
from tests.helpers import (
    CNY_WALLET,
    LANDLORD,
    NOW,
    OTP,
    PHONE_BILL,
    RENT_BILL,
    TODAY,
    UNIVERSITY,
    audit_count,
    balances,
    cny,
    convert_args,
    fund,
    last_audit,
    ledger_is_consistent,
    myr,
    new_bill,
    new_document,
    pay_args,
    posting_count,
    spend,
    the_user,
)

OFFERED = Decimal("1.62") * (1 - Decimal("0.012"))  # 1.60056 CNY per MYR


def tuition(session: Session) -> Bill:
    """The semester's tuition: CNY 12,000.00, due 30 days from the demo date."""
    return new_bill(session, UNIVERSITY, "12000.00")


def plan(session: Session, bill_id: int):  # type: ignore[no-untyped-def]
    return plan_funding(session, the_user(session), bill_id, TODAY, NOW)


# ---------------------------------------------------------------- the transfer quote


def test_a_quote_shows_the_fee_and_the_cost_hidden_in_the_rate(session: Session) -> None:
    quote = get_transfer_quote(session, myr("1000.00"), "MYR", "CNY", NOW)

    assert (quote.mid_rate, quote.offered_rate) == (Decimal("1.62"), OFFERED)
    assert quote.fee_minor == myr("8.00")
    assert quote.markup_cost_minor == myr("12.00")  # MYR 1,000.00 x 1.2%
    assert quote.total_cost_minor == myr("20.00")  # the true cost: fee plus the markup
    assert quote.total_debit_minor == myr("1008.00")
    assert quote.amount_received_minor == cny("1600.56")
    assert quote.received_at_mid_minor == cny("1620.00")
    assert quote.arrives_at == NOW + timedelta(hours=4)
    assert (quote.source, quote.provider_name) == ("simulated", "RemitFast (simulated)")
    assert (quote.quoted_at, quote.expires_at) == (NOW, NOW + timedelta(minutes=10))
    assert quote.warning is None


@pytest.mark.parametrize(("markup", "warned"), [("1.2", False), ("2", False), ("2.01", True), ("3.5", True)])
def test_a_markup_above_two_percent_carries_a_plain_warning(session: Session, markup: str, warned: bool) -> None:
    session.get_one(Provider, 1).markup_pct = markup
    session.commit()

    quote = get_transfer_quote(session, myr("1000.00"), "MYR", "CNY", NOW)

    assert quote.warning == (HIGH_MARKUP_WARNING if warned else None)
    assert quote.as_breakdown()["warning"] == quote.warning


def test_quoting_to_receive_rounds_up_so_the_shortfall_is_covered(session: Session) -> None:
    for target in (1, 99, cny("100.00"), cny("11978.00"), cny("11978.01"), 1_234_567):
        quote = quote_to_receive(session, target, "MYR", "CNY", NOW)
        one_less = get_transfer_quote(session, quote.amount_minor - 1, "MYR", "CNY", NOW) if quote.amount_minor > 1 else None

        assert quote.amount_received_minor >= target
        assert one_less is None or one_less.amount_received_minor < target  # and not a sen more than needed


def test_only_the_supported_pair_can_be_quoted(session: Session) -> None:
    with pytest.raises(FxError):
        get_transfer_quote(session, 10_000, "CNY", "MYR", NOW)
    with pytest.raises(FxError):
        get_transfer_quote(session, 10_000, "MYR", "USD", NOW)


def test_a_conversion_run_within_ten_minutes_uses_the_approved_quote(session: Session) -> None:
    proposal = actions.propose(session, the_user(session), "convert_currency", convert_args(myr("1000.00")), now=NOW)

    action = actions.confirm(session, the_user(session), proposal.action.id, now=NOW + timedelta(minutes=9))

    assert action.status == "executed"
    assert last_audit(session, "action.executed").payload["receipt"]["requoted"] is False


def test_a_conversion_run_after_its_quote_expired_is_quoted_again(session: Session) -> None:
    proposal = actions.propose(session, the_user(session), "convert_currency", convert_args(myr("1000.00")), now=NOW)

    action = actions.confirm(session, the_user(session), proposal.action.id, now=NOW + timedelta(minutes=11))

    # The rates are frozen, so the new quote gives exactly what was approved.
    receipt = last_audit(session, "action.executed").payload["receipt"]
    assert action.status == "executed"
    assert (receipt["requoted"], receipt["amount_received_minor"]) == (True, cny("1600.56"))
    assert balances(session)["CNY"] == cny("3420.00") + cny("1600.56")


def test_a_new_quote_that_differs_from_the_approved_one_is_not_executed(session: Session) -> None:
    proposal = actions.propose(session, the_user(session), "convert_currency", convert_args(myr("1000.00")), now=NOW)
    session.scalars(select(FxQuote).where(FxQuote.base == "MYR", FxQuote.quote == "CNY")).one().mid_rate = "1.50"
    session.commit()
    money = balances(session)

    action = actions.confirm(session, the_user(session), proposal.action.id, now=NOW + timedelta(minutes=11))

    assert action.status == "refused"
    assert [item["code"] for item in action.reasons] == ["QUOTE_CHANGED"]
    assert balances(session) == money


# ---------------------------------------------------------------- the funding planner


def test_the_plan_counts_the_bill_the_bills_due_before_it_and_the_buffer(session: Session) -> None:
    bill = tuition(session)

    result = plan(session, bill.id)

    assert result.status == "needs_conversion"
    assert [(item["bill_id"], item["amount_minor"]) for item in result.counted_bills] == [
        (PHONE_BILL, cny("98.00")),
        (RENT_BILL, cny("2800.00")),
        (bill.id, cny("12000.00")),
    ]
    assert result.buffer_minor == cny("500.00")
    assert result.required_minor == cny("15398.00")
    assert (result.balance_minor, result.shortfall_minor) == (cny("3420.00"), cny("11978.00"))
    assert (result.source_currency, result.source_balance_minor) == ("MYR", myr("9850.00"))
    for words in ("PearlTel Mobile CNY 98.00", "Lingnan Student Housing CNY 2,800.00", "buffer CNY 500.00", "Short by CNY 11,978.00"):
        assert words in result.explanation


def test_the_shortfall_is_covered_by_one_conversion_that_is_never_split(session: Session) -> None:
    bill = tuition(session)

    result = plan(session, bill.id)

    convert, pay = result.steps
    assert [step.tool for step in result.steps] == ["convert_currency", "pay_bill"]
    assert convert.args == convert_args(myr("7483.64"))
    assert convert.cost_breakdown["amount_received_minor"] == cny("11978.01") >= result.shortfall_minor
    assert convert.cost_breakdown["fee_minor"] == myr("8.00")
    assert convert.cost_breakdown["total_cost_minor"] == myr("8.00") + myr("89.80")
    # Above the MYR 5,000.00 per-payment limit: one Tier 3 step with a one-time code, not two smaller ones.
    assert (convert.predicted_tier, convert.requires, convert.reasons) == ("T3", ["confirm", "otp"], ["OVER_TXN_LIMIT"])
    assert (pay.predicted_tier, pay.requires) == ("T3", ["confirm", "otp"])
    assert pay.args == pay_args(bill.id)


def test_planning_writes_nothing(session: Session) -> None:
    bill = tuition(session)
    before = (audit_count(session), posting_count(session), balances(session))

    plan(session, bill.id)

    assert (audit_count(session), posting_count(session), balances(session)) == before
    assert session.scalars(select(PendingAction)).all() == []


def test_the_predicted_tiers_match_what_the_policy_engine_then_says(session: Session) -> None:
    bill = tuition(session)
    user = the_user(session)

    result = plan(session, bill.id)
    proposals = [actions.propose(session, user, step.tool, step.args, "plan-test", now=NOW) for step in result.steps]

    assert [proposal.status for proposal in proposals] == ["pending", "pending"]
    assert [proposal.verdict.tier for proposal in proposals] == [step.predicted_tier for step in result.steps]
    assert [proposal.verdict.requires for proposal in proposals] == [step.requires for step in result.steps]


def test_with_enough_in_the_wallet_the_plan_is_just_the_payment(session: Session) -> None:
    # The rent is due before the tuition, so the tuition is not counted here.
    tuition(session)

    result = plan(session, RENT_BILL)

    assert result.status == "ready"
    assert [item["bill_id"] for item in result.counted_bills] == [PHONE_BILL, RENT_BILL]
    assert (result.required_minor, result.shortfall_minor) == (cny("3398.00"), 0)
    assert [step.tool for step in result.steps] == ["pay_bill"]
    assert result.steps[0].predicted_tier == "T2"
    assert result.source_currency is None and "No conversion is needed." in result.explanation


def test_bills_from_flagged_or_untrusted_documents_are_not_counted(session: Session) -> None:
    bill = tuition(session)
    new_bill(session, LANDLORD, "900.00", document=new_document(session, trust_flag="untrusted"))
    scam = new_document(session, risk_signals=[{"code": "SCAM_PATTERN", "evidence": []}])
    new_bill(session, LANDLORD, "700.00", document=scam)
    trusted = new_bill(session, LANDLORD, "300.00", document=new_document(session))

    result = plan(session, bill.id)

    assert [item["bill_id"] for item in result.counted_bills] == [PHONE_BILL, RENT_BILL, bill.id, trusted.id]
    assert result.required_minor == cny("15398.00") + cny("300.00")


def test_paid_bills_later_bills_and_other_currencies_are_not_counted(session: Session) -> None:
    bill = tuition(session)
    new_bill(session, LANDLORD, "400.00", status="paid")
    new_bill(session, LANDLORD, "50.00", currency="USD")
    later = new_bill(session, LANDLORD, "600.00")
    later.due_date = bill.due_date + timedelta(days=1)
    session.commit()

    result = plan(session, bill.id)

    assert [item["bill_id"] for item in result.counted_bills] == [PHONE_BILL, RENT_BILL, bill.id]


def test_the_buffer_can_be_changed(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    bill = tuition(session)
    monkeypatch.setenv("FUNDING_BUFFER_MINOR", "120000")
    get_settings.cache_clear()

    result = plan(session, bill.id)

    assert (result.buffer_minor, result.required_minor) == (cny("1200.00"), cny("16098.00"))


def test_the_plan_never_asks_for_more_than_the_home_wallet_holds(session: Session) -> None:
    bill = tuition(session)
    spend(session, "MYR", myr("4850.00"))  # MYR 5,000.00 left

    result = plan(session, bill.id)

    most = myr("5000.00") - myr("8.00")
    assert result.status == "insufficient_funds"
    assert result.steps == []
    assert result.affordable == {
        "amount_minor": most,
        "fee_minor": myr("8.00"),
        "receives_minor": int((Decimal(most) * OFFERED).to_integral_value(rounding=ROUND_DOWN)),
    }
    assert result.affordable["amount_minor"] + result.affordable["fee_minor"] == balances(session)["MYR"]
    assert "more than the MYR wallet holds" in result.explanation


def test_a_wallet_exactly_large_enough_is_enough(session: Session) -> None:
    bill = tuition(session)
    spend(session, "MYR", myr("9850.00") - myr("7483.64") - myr("8.00"))

    assert plan(session, bill.id).status == "needs_conversion"
    spend(session, "MYR", 1)
    assert plan(session, bill.id).status == "insufficient_funds"


def test_a_shortfall_in_a_currency_that_cannot_be_bought_is_said_plainly(session: Session) -> None:
    bill = new_bill(session, LANDLORD, "500.00", currency="USD")

    result = plan(session, bill.id)

    assert (result.status, result.buffer_minor, result.shortfall_minor) == ("insufficient_funds", 0, 32_000)
    assert result.steps == [] and result.affordable is None
    assert "MYR cannot be converted to USD here" in result.explanation


def test_a_paid_or_unknown_bill_cannot_be_planned(session: Session) -> None:
    paid = new_bill(session, LANDLORD, "400.00", status="paid")

    assert plan(session, paid.id).status == "not_payable"
    assert plan(session, 9_999).status == "not_payable"


# ---------------------------------------------------------------- a plan's steps depend on each other


def test_a_payment_alone_is_refused_when_the_wallet_cannot_cover_it(session: Session) -> None:
    bill = tuition(session)

    proposal = actions.propose(session, the_user(session), "pay_bill", pay_args(bill.id), now=NOW)

    assert proposal.status == "refused"
    assert [item.code for item in proposal.verdict.reasons] == ["INSUFFICIENT_FUNDS"]


def test_a_payment_can_wait_behind_the_conversion_that_funds_it(session: Session) -> None:
    bill = tuition(session)
    user = the_user(session)
    actions.propose(session, user, "convert_currency", convert_args(myr("7483.64")), "plan-a", now=NOW)

    same_plan = actions.propose(session, user, "pay_bill", pay_args(bill.id), "plan-a", now=NOW)
    other_plan = actions.propose(session, user, "pay_bill", pay_args(bill.id), "plan-b", now=NOW)

    assert (same_plan.status, same_plan.verdict.tier) == ("pending", "T3")
    assert other_plan.status == "refused"
    assert [item.code for item in other_plan.verdict.reasons] == ["INSUFFICIENT_FUNDS"]


def test_a_conversion_too_small_for_the_bill_does_not_unlock_the_payment(session: Session) -> None:
    bill = tuition(session)
    user = the_user(session)
    actions.propose(session, user, "convert_currency", convert_args(myr("1000.00")), "plan-a", now=NOW)

    proposal = actions.propose(session, user, "pay_bill", pay_args(bill.id), "plan-a", now=NOW)

    assert [item.code for item in proposal.verdict.reasons] == ["INSUFFICIENT_FUNDS"]


def test_the_steps_of_a_plan_are_confirmed_in_order(session: Session) -> None:
    bill = tuition(session)
    user = the_user(session)
    convert = actions.propose(session, user, "convert_currency", convert_args(myr("7483.64")), "plan-a", now=NOW).action
    pay = actions.propose(session, user, "pay_bill", pay_args(bill.id), "plan-a", now=NOW).action

    with pytest.raises(ActionError, match="earlier step"):
        actions.confirm(session, user, pay.id, now=NOW)

    assert session.get_one(PendingAction, pay.id).status == "awaiting_confirm"
    actions.confirm(session, user, convert.id, now=NOW)
    with pytest.raises(ActionError, match="earlier step"):  # the conversion still waits for its code
        actions.confirm(session, user, pay.id, now=NOW)
    assert actions.submit_otp(session, user, convert.id, OTP, now=NOW).accepted
    actions.confirm(session, user, pay.id, now=NOW)
    assert actions.submit_otp(session, user, pay.id, OTP, now=NOW).action.status == "executed"
    assert session.get_one(Bill, bill.id).status == "paid"
    assert ledger_is_consistent(session)


def test_cancelling_the_conversion_means_the_payment_is_refused_when_confirmed(session: Session) -> None:
    bill = tuition(session)
    user = the_user(session)
    convert = actions.propose(session, user, "convert_currency", convert_args(myr("7483.64")), "plan-a", now=NOW).action
    pay = actions.propose(session, user, "pay_bill", pay_args(bill.id), "plan-a", now=NOW).action
    money = balances(session)

    actions.cancel(session, user, convert.id, now=NOW)
    action = actions.confirm(session, user, pay.id, now=NOW)

    # The policy is checked again on confirming: the money never arrived, so the payment
    # is refused before a code is even asked for.
    assert action.status == "refused"
    assert [item["code"] for item in action.reasons] == ["INSUFFICIENT_FUNDS"]
    assert last_audit(session, "action.refused").payload["action_id"] == pay.id
    assert balances(session) == money
    assert session.get_one(Bill, bill.id).status == "open"


def test_extra_cny_makes_the_conversion_smaller(session: Session) -> None:
    bill = tuition(session)
    fund(session, "CNY", cny("10000.00"))

    result = plan(session, bill.id)

    assert result.shortfall_minor == cny("1978.00")
    assert result.steps[0].args["amount_minor"] < myr("5000.00")
    assert (result.steps[0].predicted_tier, result.steps[0].requires) == ("T2", ["confirm"])
    assert CNY_WALLET == result.steps[1].args["from_account_id"]
