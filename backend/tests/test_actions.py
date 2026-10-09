"""Proposing, confirming, one-time codes, cooling-off, cancelling, and the executor's re-check."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import actions, audit
from app.actions import ActionError, Proposal
from app.models import Bill, Document, Payee, PendingAction, Posting, Provider
from tests.helpers import (
    CNY_WALLET,
    LANDLORD,
    MYR_WALLET,
    NOW,
    OTP,
    PHONE_BILL,
    PHONE_COMPANY,
    TODAY,
    UNIVERSITY,
    audit_count,
    audit_events,
    balance,
    balances,
    cny,
    convert_args,
    fund,
    last_audit,
    ledger_is_consistent,
    myr,
    new_bill,
    new_document,
    new_payee,
    pay_args,
    posting_count,
    spend,
    the_user,
)


def propose(session: Session, tool: str, args: dict[str, Any], **options: Any) -> Proposal:
    return actions.propose(session, the_user(session), tool, args, now=NOW, **options)


def confirm(session: Session, action_id: int, after: timedelta = timedelta(0)) -> PendingAction:
    return actions.confirm(session, the_user(session), action_id, now=NOW + after)


def otp(session: Session, action_id: int, code: str = OTP, after: timedelta = timedelta(0)) -> actions.OtpResult:
    return actions.submit_otp(session, the_user(session), action_id, code, now=NOW + after)


def pending_id(proposal: Proposal) -> int:
    assert proposal.action is not None
    return proposal.action.id


# ---------------------------------------------------------------- propose


def test_a_read_tool_gets_the_go_ahead_and_is_logged(session: Session) -> None:
    before = audit_count(session)

    proposal = propose(session, "get_balances", {})

    assert (proposal.status, proposal.verdict.tier, proposal.action) == ("allowed", "T0", None)
    assert audit_events(session, before) == ["agent.proposed", "policy.verdict"]
    assert last_audit(session, "policy.verdict").payload["tier"] == "T0"
    assert session.scalars(select(PendingAction)).all() == []


def test_a_payment_becomes_a_pending_action_that_waits_for_the_student(session: Session) -> None:
    before = audit_count(session)
    money = balances(session)

    proposal = propose(session, "pay_bill", pay_args(PHONE_BILL), plan_id="plan-1")
    action = proposal.action

    assert proposal.status == "pending" and action is not None
    assert (action.tool, action.tier, action.status, action.plan_id) == ("pay_bill", "T2", "awaiting_confirm", "plan-1")
    assert action.expires_at == NOW + timedelta(minutes=15)
    assert action.cost_breakdown["amount_minor"] == cny("98.00")
    assert audit_events(session, before) == ["agent.proposed", "policy.verdict"]
    assert last_audit(session, "agent.proposed").payload == {
        "tool": "pay_bill",
        "args": pay_args(PHONE_BILL),
        "plan_id": "plan-1",
    }
    assert last_audit(session, "policy.verdict").payload["action_id"] == action.id
    assert balances(session) == money  # nothing moves on a proposal
    assert [item.id for item in actions.pending(session, the_user(session))] == [action.id]


def test_a_refused_proposal_is_recorded_and_can_never_run(session: Session) -> None:
    before = audit_count(session)
    bill = new_bill(session, UNIVERSITY, "100.00", document=new_document(session, trust_flag="untrusted"))

    proposal = propose(session, "pay_bill", pay_args(bill))
    action = proposal.action

    assert proposal.status == "refused" and action is not None
    assert (action.status, action.tier, action.expires_at) == ("refused", "REFUSED", None)
    assert [item["code"] for item in action.reasons] == ["UNTRUSTED_DOCUMENT"]
    assert set(action.reasons[0]["title"]) == {"en", "ms", "zh"}
    assert audit_events(session, before) == ["agent.proposed", "policy.verdict", "action.refused"]
    assert last_audit(session, "action.refused").payload["reasons"] == ["UNTRUSTED_DOCUMENT"]
    assert actions.pending(session, the_user(session)) == []
    for attempt in (confirm, lambda s, i: otp(s, i), lambda s, i: actions.cancel(s, the_user(s), i, now=NOW)):
        with pytest.raises(ActionError):
            attempt(session, action.id)
    assert session.get_one(Bill, bill.id).status == "open"


def test_a_mismatched_amount_from_the_llm_is_refused_at_proposal(session: Session) -> None:
    proposal = propose(session, "pay_bill", pay_args(PHONE_BILL, amount_minor=1))

    assert proposal.status == "refused"
    assert [item.code for item in proposal.verdict.reasons] == ["ARGUMENT_MISMATCH"]


# ---------------------------------------------------------------- tier 2: confirm then execute


def test_confirming_a_tier_2_payment_executes_it(session: Session) -> None:
    action_id = pending_id(propose(session, "pay_bill", pay_args(PHONE_BILL)))
    before = audit_count(session)
    cny_before = balance(session, CNY_WALLET)

    action = confirm(session, action_id)

    assert action.status == "executed"
    assert balance(session, CNY_WALLET) == cny_before - cny("98.00")
    assert session.get_one(Bill, PHONE_BILL).status == "paid"
    posting = session.get_one(Posting, action.executed_posting_id)
    assert (posting.kind, posting.action_id, posting.business_date, posting.counterparty) == (
        "payment",
        action.id,
        TODAY,
        "PearlTel Mobile",
    )
    assert audit_events(session, before) == ["user.confirmed", "policy.verdict", "action.executed"]
    executed = last_audit(session, "action.executed").payload
    assert executed["posting_id"] == posting.id
    assert executed["receipt"]["amount_minor"] == cny("98.00")
    assert executed["receipt"]["payee_name"] == "PearlTel Mobile"
    assert last_audit(session, "policy.verdict").payload["stage"] == "execution"
    assert ledger_is_consistent(session)
    assert audit.verify(session)["ok"] is True


def test_the_executor_pays_the_bills_amount_and_payee(session: Session) -> None:
    args = pay_args(PHONE_BILL, amount_minor=cny("98.00"), currency="CNY", payee_id=PHONE_COMPANY)
    action = confirm(session, pending_id(propose(session, "pay_bill", args)))

    posting = session.get_one(Posting, action.executed_posting_id)
    paid = [entry.amount_minor for entry in posting.entries if entry.account_id == CNY_WALLET]

    assert paid == [-cny("98.00")]
    assert posting.counterparty == session.get_one(Bill, PHONE_BILL).payee.name


def test_confirming_a_conversion_moves_both_wallets(session: Session) -> None:
    action = confirm(session, pending_id(propose(session, "convert_currency", convert_args(myr("1000.00")))))

    assert action.status == "executed"
    assert balances(session) == {
        "MYR": myr("9850.00") - myr("1008.00"),  # amount plus the MYR 8.00 fee
        "CNY": cny("3420.00") + cny("1600.56"),
        "USD": 18_000,
    }
    receipt = last_audit(session, "action.executed").payload["receipt"]
    assert (receipt["fee_minor"], receipt["amount_received_minor"]) == (myr("8.00"), cny("1600.56"))
    assert session.get_one(Posting, action.executed_posting_id).kind == "conversion"
    assert ledger_is_consistent(session)


def test_an_action_cannot_be_confirmed_twice(session: Session) -> None:
    action_id = pending_id(propose(session, "pay_bill", pay_args(PHONE_BILL)))
    confirm(session, action_id)
    postings = posting_count(session)

    with pytest.raises(ActionError):
        confirm(session, action_id)

    assert posting_count(session) == postings


def test_someone_elses_or_missing_action_is_not_found(session: Session) -> None:
    with pytest.raises(ActionError) as error:
        confirm(session, 9_999)

    assert error.value.not_found is True


# ---------------------------------------------------------------- tier 3: one-time code


def tuition_action(session: Session) -> int:
    """A CNY 12,000.00 payment to the university: above the per-payment limit, so Tier 3."""
    fund(session, "CNY", cny("20000.00"))
    return pending_id(propose(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "12000.00"))))


def test_a_tier_3_payment_needs_the_one_time_code(session: Session) -> None:
    action_id = tuition_action(session)
    cny_before = balance(session, CNY_WALLET)

    action = confirm(session, action_id)
    assert (action.tier, action.status) == ("T3", "awaiting_otp")
    assert balance(session, CNY_WALLET) == cny_before  # confirming alone moves nothing

    result = otp(session, action_id)

    assert result.accepted is True
    assert result.action.status == "executed"  # a payee paid before: no cooling-off
    assert balance(session, CNY_WALLET) == cny_before - cny("12000.00")
    assert audit_events(session)[-4:] == ["user.confirmed", "user.otp_verified", "policy.verdict", "action.executed"]


def test_the_code_cannot_be_entered_before_confirming(session: Session) -> None:
    action_id = tuition_action(session)

    with pytest.raises(ActionError):
        otp(session, action_id)


def test_three_wrong_codes_cancel_the_action_and_each_attempt_is_logged(session: Session) -> None:
    action_id = tuition_action(session)
    confirm(session, action_id)
    before = audit_count(session)
    money = balances(session)

    first = otp(session, action_id, "000000")
    second = otp(session, action_id, "111111")
    assert (first.accepted, first.attempts_left, first.action.status) == (False, 2, "awaiting_otp")
    assert (second.accepted, second.attempts_left) == (False, 1)
    third = otp(session, action_id, "246811")

    assert (third.accepted, third.attempts_left, third.action.status) == (False, 0, "cancelled")
    assert audit_events(session, before) == ["user.otp_failed", "user.otp_failed", "user.otp_failed", "user.cancelled"]
    assert last_audit(session, "user.otp_failed").payload == {"action_id": action_id, "attempt": 3, "max_attempts": 3}
    assert last_audit(session, "user.cancelled").payload["cause"] == "otp_attempts_exhausted"
    # The right code no longer helps, and no money moved.
    with pytest.raises(ActionError):
        otp(session, action_id)
    assert balances(session) == money


def test_wrong_codes_are_never_written_to_the_log(session: Session) -> None:
    action_id = tuition_action(session)
    confirm(session, action_id)

    otp(session, action_id, "135790")

    assert "135790" not in audit.export(session, "json")
    assert OTP not in audit.export(session, "json")


def test_two_wrong_codes_then_the_right_one_still_works(session: Session) -> None:
    action_id = tuition_action(session)
    confirm(session, action_id)
    otp(session, action_id, "000000")
    otp(session, action_id, "111111")

    assert otp(session, action_id).action.status == "executed"


# ---------------------------------------------------------------- cooling-off


def first_payment(session: Session) -> tuple[int, Bill]:
    """A first payment of CNY 1,000.00 to a new payee, confirmed and with the code accepted."""
    bill = new_bill(session, new_payee(session).id, "1000.00")
    action_id = pending_id(propose(session, "pay_bill", pay_args(bill)))
    confirm(session, action_id)
    otp(session, action_id)
    return action_id, bill


def test_a_first_payment_waits_in_cooling_off_then_executes(session: Session) -> None:
    money = balances(session)
    action_id, bill = first_payment(session)
    action = session.get_one(PendingAction, action_id)

    assert action.status == "cooling_off"
    assert action.expires_at == NOW + timedelta(seconds=60)
    assert balances(session) == money

    actions.sweep(session, now=NOW + timedelta(seconds=59))
    assert session.get_one(PendingAction, action_id).status == "cooling_off"
    assert balances(session) == money

    actions.sweep(session, now=NOW + timedelta(seconds=60))

    assert session.get_one(PendingAction, action_id).status == "executed"
    assert balance(session, CNY_WALLET) == money["CNY"] - cny("1000.00")
    assert session.get_one(Bill, bill.id).status == "paid"
    assert session.get_one(Payee, bill.payee_id).first_paid_at == TODAY
    assert audit_events(session)[-2:] == ["policy.verdict", "action.executed"]
    assert ledger_is_consistent(session)


def test_cancelling_during_cooling_off_leaves_the_balances_unchanged(session: Session) -> None:
    money = balances(session)
    postings = posting_count(session)
    action_id, bill = first_payment(session)

    cancelled = actions.cancel(session, the_user(session), action_id, now=NOW + timedelta(seconds=30))
    actions.sweep(session, now=NOW + timedelta(hours=1))

    assert cancelled.status == "cancelled"
    assert session.get_one(PendingAction, action_id).status == "cancelled"
    assert balances(session) == money
    assert posting_count(session) == postings
    assert session.get_one(Bill, bill.id).status == "open"
    assert session.get_one(Payee, bill.payee_id).first_paid_at is None
    assert last_audit(session, "user.cancelled").payload == {"action_id": action_id, "tool": "pay_bill", "cause": "user"}


def test_adding_a_payee_runs_after_code_and_cooling_off(session: Session) -> None:
    details = {"name": "Chen Li", "account_ref": "6222 0000 1111 2222", "bank_name": "Example Bank"}
    action_id = pending_id(propose(session, "add_payee", details))

    assert confirm(session, action_id).status == "awaiting_otp"
    assert otp(session, action_id).action.status == "cooling_off"
    assert session.scalars(select(Payee).where(Payee.name == "Chen Li")).first() is None

    actions.sweep(session, now=NOW + timedelta(seconds=61))

    payee = session.scalars(select(Payee).where(Payee.name == "Chen Li")).one()
    assert (payee.account_ref, payee.verified_source, payee.first_paid_at) == ("6222 0000 1111 2222", "manual", None)
    assert session.get_one(PendingAction, action_id).status == "executed"
    assert last_audit(session, "action.executed").payload["receipt"]["payee_id"] == payee.id


# ---------------------------------------------------------------- cancel and expiry


@pytest.mark.parametrize("stage", ["awaiting_confirm", "awaiting_otp"])
def test_an_action_can_be_cancelled_before_it_runs(session: Session, stage: str) -> None:
    action_id = tuition_action(session)
    money = balances(session)
    if stage == "awaiting_otp":
        confirm(session, action_id)

    action = actions.cancel(session, the_user(session), action_id, now=NOW)

    assert action.status == "cancelled"
    assert balances(session) == money
    with pytest.raises(ActionError):
        confirm(session, action_id)


def test_an_executed_action_cannot_be_cancelled(session: Session) -> None:
    action_id = pending_id(propose(session, "pay_bill", pay_args(PHONE_BILL)))
    confirm(session, action_id)

    with pytest.raises(ActionError):
        actions.cancel(session, the_user(session), action_id, now=NOW)

    assert session.get_one(PendingAction, action_id).status == "executed"


def test_an_approval_left_for_15_minutes_expires(session: Session) -> None:
    action_id = pending_id(propose(session, "pay_bill", pay_args(PHONE_BILL)))
    money = balances(session)

    actions.sweep(session, now=NOW + timedelta(minutes=14, seconds=59))
    assert session.get_one(PendingAction, action_id).status == "awaiting_confirm"
    actions.sweep(session, now=NOW + timedelta(minutes=15))

    assert session.get_one(PendingAction, action_id).status == "expired"
    assert last_audit(session, "action.expired").payload == {"action_id": action_id, "tool": "pay_bill"}
    with pytest.raises(ActionError):
        confirm(session, action_id, after=timedelta(minutes=16))
    assert balances(session) == money


def test_a_late_confirmation_expires_the_action_even_before_the_sweep(session: Session) -> None:
    action_id = pending_id(propose(session, "pay_bill", pay_args(PHONE_BILL)))

    with pytest.raises(ActionError, match="expired"):
        confirm(session, action_id, after=timedelta(minutes=15))

    assert session.get_one(PendingAction, action_id).status == "expired"
    assert session.get_one(Bill, PHONE_BILL).status == "open"


# ---------------------------------------------------------------- the executor re-checks


def test_executor_refuses_when_the_money_is_gone(session: Session) -> None:
    action_id = pending_id(propose(session, "pay_bill", pay_args(PHONE_BILL)))
    spend(session, "CNY", cny("3400.00"))  # CNY 20.00 left, the bill is CNY 98.00
    postings = posting_count(session)
    before = audit_count(session)

    action = confirm(session, action_id)

    assert (action.status, action.tier) == ("refused", "REFUSED")
    assert [item["code"] for item in action.reasons] == ["INSUFFICIENT_FUNDS"]
    assert posting_count(session) == postings
    assert balance(session, CNY_WALLET) == cny("20.00")
    assert session.get_one(Bill, PHONE_BILL).status == "open"
    assert audit_events(session, before) == ["user.confirmed", "policy.verdict", "action.refused"]
    assert last_audit(session, "action.refused").payload == {
        "action_id": action_id,
        "tool": "pay_bill",
        "reasons": ["INSUFFICIENT_FUNDS"],
        "stage": "execution",
    }


def test_executor_refuses_when_the_bill_was_paid_meanwhile(session: Session) -> None:
    first = pending_id(propose(session, "pay_bill", pay_args(PHONE_BILL)))
    second = pending_id(propose(session, "pay_bill", pay_args(PHONE_BILL)))
    confirm(session, first)
    money = balances(session)

    action = confirm(session, second)

    assert action.status == "refused"
    assert [item["code"] for item in action.reasons] == ["BILL_NOT_PAYABLE"]
    assert balances(session) == money  # the bill was paid once, not twice


def test_executor_refuses_when_the_document_was_flagged_after_approval(session: Session) -> None:
    document = new_document(session)
    bill = new_bill(session, new_payee(session).id, "1000.00", document=document)
    action_id = pending_id(propose(session, "pay_bill", pay_args(bill)))
    confirm(session, action_id)
    otp(session, action_id)  # now cooling off
    money = balances(session)

    session.get_one(Document, document.id).trust_flag = "untrusted"
    session.commit()
    actions.sweep(session, now=NOW + timedelta(seconds=61))

    action = session.get_one(PendingAction, action_id)
    assert action.status == "refused"
    assert [item["code"] for item in action.reasons] == ["UNTRUSTED_DOCUMENT"]
    assert balances(session) == money


def test_executor_refuses_when_the_cost_changed_after_approval(session: Session) -> None:
    action_id = pending_id(propose(session, "convert_currency", convert_args(myr("1000.00"))))
    session.get_one(Provider, 1).fee_fixed_minor = myr("80.00")
    session.commit()
    money = balances(session)

    action = confirm(session, action_id)

    assert action.status == "refused"
    assert [item["code"] for item in action.reasons] == ["QUOTE_CHANGED"]
    assert balances(session) == money


def test_executor_refuses_when_the_daily_limit_was_used_up_meanwhile(session: Session) -> None:
    fund(session, "CNY", cny("30000.00"))
    waiting = pending_id(propose(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "8000.00"))))
    for payee in (LANDLORD, PHONE_COMPANY):
        confirm(session, pending_id(propose(session, "pay_bill", pay_args(new_bill(session, payee, "8000.00")))))

    action = confirm(session, waiting)

    assert action.status == "refused"
    assert [item["code"] for item in action.reasons] == ["DAILY_LIMIT"]


# ---------------------------------------------------------------- daily limit with several payments


def test_daily_limit_adds_up_executed_payments(session: Session) -> None:
    fund(session, "CNY", cny("30000.00"))
    # Two payments of CNY 8,000.00 (about MYR 4,938.28 each) to different known payees: MYR 9,876.56 today.
    for payee in (LANDLORD, PHONE_COMPANY):
        assert confirm(session, pending_id(propose(session, "pay_bill", pay_args(new_bill(session, payee, "8000.00"))))).status == "executed"

    # MYR 123.44 is left. CNY 199.97 is MYR 123.44 (rounded up); CNY 199.98 is MYR 123.45.
    fits = propose(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "199.97")))
    too_much = propose(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "199.98")))

    assert fits.status == "pending"
    assert (too_much.status, [item.code for item in too_much.verdict.reasons]) == ("refused", ["DAILY_LIMIT"])


def test_conversions_and_unfinished_actions_do_not_count_towards_the_daily_limit(session: Session) -> None:
    fund(session, "CNY", cny("30000.00"))
    # A big conversion, a cancelled payment, a refused payment and an expired payment: none count.
    conversion = pending_id(propose(session, "convert_currency", convert_args(myr("9000.00"))))
    confirm(session, conversion)
    otp(session, conversion)
    cancelled = pending_id(propose(session, "pay_bill", pay_args(new_bill(session, LANDLORD, "8000.00"))))
    actions.cancel(session, the_user(session), cancelled, now=NOW)
    propose(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "99999.00")))
    propose(session, "pay_bill", pay_args(new_bill(session, PHONE_COMPANY, "8000.00")))
    actions.sweep(session, now=NOW + timedelta(minutes=16))

    full_day = propose(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "16200.00")))

    assert session.get_one(PendingAction, conversion).status == "executed"
    assert full_day.status == "pending"  # the whole MYR 10,000 is still available


# ---------------------------------------------------------------- splitting never lowers a tier


def test_splitting_a_conversion_does_not_avoid_the_code(session: Session) -> None:
    # MYR 6,000.00 in two halves. Each half alone is under the MYR 5,000.00 limit.
    first = propose(session, "convert_currency", convert_args(myr("3000.00")))
    second = propose(session, "convert_currency", convert_args(myr("3000.00")))

    assert first.verdict.tier == "T2"
    assert (second.verdict.tier, [item.code for item in second.verdict.reasons]) == ("T3", ["OVER_TXN_LIMIT"])

    # Confirming the first half is re-checked together with the waiting second half.
    before = audit_count(session)
    money = balances(session)
    action = confirm(session, pending_id(first))

    assert (action.tier, action.status) == ("T3", "awaiting_otp")
    assert balances(session) == money
    assert audit_events(session, before) == ["user.confirmed", "policy.verdict"]
    assert last_audit(session, "policy.verdict").payload["stage"] == "recheck"
    assert otp(session, action.id).action.status == "executed"


def test_a_second_conversion_after_an_executed_one_counts_the_first(session: Session) -> None:
    confirm(session, pending_id(propose(session, "convert_currency", convert_args(myr("3000.00")))))

    again = propose(session, "convert_currency", convert_args(myr("2000.01")))
    small = propose(session, "convert_currency", convert_args(myr("1000.00")))

    assert again.verdict.tier == "T3"
    assert small.verdict.tier == "T3"  # 3,000 executed + 2,000.01 waiting + 1,000


def test_cancelled_parts_stop_counting(session: Session) -> None:
    first = pending_id(propose(session, "convert_currency", convert_args(myr("3000.00"))))
    actions.cancel(session, the_user(session), first, now=NOW)

    assert propose(session, "convert_currency", convert_args(myr("3000.00"))).verdict.tier == "T2"


def test_two_payments_to_the_same_payee_are_measured_together(session: Session) -> None:
    fund(session, "CNY", cny("20000.00"))
    first = propose(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "5000.00")))  # about MYR 3,086
    second = propose(session, "pay_bill", pay_args(new_bill(session, UNIVERSITY, "5000.00")))
    other_payee = propose(session, "pay_bill", pay_args(new_bill(session, LANDLORD, "5000.00")))

    assert (first.verdict.tier, second.verdict.tier, other_payee.verdict.tier) == ("T2", "T3", "T2")


def test_a_new_payee_and_the_per_payment_limit_can_both_apply(session: Session) -> None:
    fund(session, "CNY", cny("20000.00"))
    payee = new_payee(session)
    propose(session, "pay_bill", pay_args(new_bill(session, payee.id, "4500.00")))

    second = propose(session, "pay_bill", pay_args(new_bill(session, payee.id, "4500.00")))

    assert second.verdict.tier == "T3"
    assert [item.code for item in second.verdict.reasons] == ["OVER_TXN_LIMIT", "NEW_PAYEE"]
    assert second.verdict.requires == ["confirm", "otp", "cooling_off"]


# ---------------------------------------------------------------- the whole trail


def test_every_step_of_a_tier_3_payment_is_in_the_audit_log(session: Session) -> None:
    before = audit_count(session)
    action_id, _ = first_payment(session)
    actions.sweep(session, now=NOW + timedelta(seconds=61))

    assert audit_events(session, before) == [
        "agent.proposed",
        "policy.verdict",
        "user.confirmed",
        "user.otp_verified",
        "policy.verdict",
        "action.executed",
    ]
    assert audit.verify(session) == {"ok": True, "entries": before + 6}
    assert session.get_one(PendingAction, action_id).status == "executed"


def test_wallets_other_than_the_source_are_untouched_by_a_payment(session: Session) -> None:
    confirm(session, pending_id(propose(session, "pay_bill", pay_args(PHONE_BILL))))

    assert balance(session, MYR_WALLET) == myr("9850.00")
