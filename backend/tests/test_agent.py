"""
The demo's three acts, run through the API with the scripted driver.

The scripted driver only chooses which tool to call. Every call goes through the real
policy engine, ledger and audit log.
"""

from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import FxQuote
from app.policy import _paid_out_today
from tests.helpers import (
    OTP,
    all_audit_events,
    context,
    ledger_is_consistent,
    only,
    read_events,
    say,
    the_user,
    wallet_balances,
)

DEADLINE_QUESTION = "Boleh saya bayar yuran ini sebelum tarikh akhir?"
AGENT_QUESTION = "Boleh saya bayar melalui ejen ini?"
FORWARD_QUESTION = "Boleh saya pindahkan wang ini seperti yang diminta?"

START = {"MYR": 985_000, "CNY": 342_000, "USD": 18_000}
TUITION, RENT, PHONE, BUFFER = 1_200_000, 280_000, 9_800, 50_000
FEE = 800  # MYR 8.00 per transfer
MARKUP = Decimal("0.012")


def set_rate(cny_per_myr: str) -> None:
    """Freeze a different mid-market rate, as a reset on another day would."""
    rate = Decimal(cny_per_myr)
    with Session(get_engine()) as session:
        session.execute(update(FxQuote).where(FxQuote.base == "MYR", FxQuote.quote == "CNY").values(mid_rate=str(rate)))
        inverse = (Decimal(1) / rate).quantize(Decimal("0.0000000001"))
        session.execute(update(FxQuote).where(FxQuote.base == "CNY", FxQuote.quote == "MYR").values(mid_rate=str(inverse)))
        session.commit()


def expected_conversion(cny_per_myr: str) -> tuple[int, int]:
    """Worked out here from first principles: (MYR sen to convert, CNY fen received)."""
    shortfall = TUITION + RENT + PHONE + BUFFER - START["CNY"]
    offered = Decimal(cny_per_myr) * (1 - MARKUP)
    amount = int((Decimal(shortfall) / offered).to_integral_value(rounding=ROUND_UP))
    received = int((Decimal(amount) * offered).to_integral_value(rounding=ROUND_DOWN))
    assert received >= shortfall
    return amount, received


def approve(client: TestClient, action_id: int) -> dict[str, Any]:
    """Confirm, then enter the one-time code."""
    confirmed = client.post(f"/actions/{action_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "awaiting_otp"
    result = client.post(f"/actions/{action_id}/otp", json={"code": OTP}).json()
    assert result["accepted"] is True
    return result["action"]


def tools_of(events: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, str, str]]:
    return [(step["tool"], step["tier"], step["verdict"]) for step in only(events, "step")]


# ---------------------------------------------------------------- Act 1: the real bill


def test_act_1_plan_convert_and_pay_the_tuition(client: TestClient) -> None:
    amount, received = expected_conversion("1.62")
    invoice = client.post("/demo/documents/tuition_invoice").json()
    bill_id = invoice["bill"]["id"]
    audit_before = len(all_audit_events(client))

    events = say(client, DEADLINE_QUESTION)

    assert tools_of(events) == [
        ("get_balances", "T0", "allowed"),
        ("plan_funding", "T1", "allowed"),
        ("get_transfer_quote", "T0", "allowed"),
        ("convert_currency", "T3", "pending"),
        ("pay_bill", "T3", "pending"),
    ]
    assert [name for name, _ in events][-3:] == ["message", "approval_required", "done"]
    plan = only(events, "step")[1]["details"]
    assert (plan["required_minor"], plan["shortfall_minor"]) == (TUITION + RENT + PHONE + BUFFER, 1_197_800)
    assert [bill["payee_name"] for bill in plan["counted_bills"]] == [
        "PearlTel Mobile",
        "Lingnan Student Housing",
        "Shenzhen Polytechnic International University",
    ]

    message = only(events, "message")[0]
    assert message["language"] == "ms"
    assert message["text"].startswith("Baki CNY anda tidak cukup.")
    assert "MYR 7,483.64" in message["text"] and "CNY 12,000.00" in message["text"] and "kod sekali guna" in message["text"]
    assert message["text_en"].startswith("Your CNY balance is not enough.")

    approval = only(events, "approval_required")[0]
    convert, pay = approval["actions"]
    assert approval["plan_id"].startswith("plan-")
    assert (convert["tool"], convert["tier"], convert["requires"]) == ("convert_currency", "T3", ["confirm", "otp"])
    assert (convert["amount"], convert["currency"], convert["payee"]) == (amount, "MYR", None)
    assert (convert["cost_breakdown"]["amount_received_minor"], convert["cost_breakdown"]["fee_minor"]) == (received, FEE)
    assert convert["cost_breakdown"]["total_cost_minor"] == FEE + 8_980  # MYR 7,483.64 x 1.2% = MYR 89.80
    assert convert["reasons"][0]["code"] == "OVER_TXN_LIMIT"
    assert (convert["reasons"][0]["title"], convert["reasons"][0]["title_en"]) == ("Melebihi had setiap bayaran", "Above your per-payment limit")
    assert (pay["tool"], pay["tier"], pay["requires"]) == ("pay_bill", "T3", ["confirm", "otp"])
    assert (pay["amount"], pay["currency"], pay["payee"]) == (TUITION, "CNY", "Shenzhen Polytechnic International University")
    assert wallet_balances(client) == START  # proposing moves nothing

    # A plan's steps run in order: the payment cannot be confirmed before the conversion.
    assert client.post(f"/actions/{pay['id']}/confirm").status_code == 409

    assert approve(client, convert["id"])["status"] == "executed"
    assert wallet_balances(client) == {"MYR": START["MYR"] - amount - FEE, "CNY": START["CNY"] + received, "USD": START["USD"]}
    assert approve(client, pay["id"])["status"] == "executed"

    # Bill paid, balances right to the sen and the fen.
    assert wallet_balances(client) == {
        "MYR": START["MYR"] - amount - FEE,
        "CNY": START["CNY"] + received - TUITION,
        "USD": START["USD"],
    }
    assert wallet_balances(client) == {"MYR": 235_836, "CNY": 339_801, "USD": 18_000}
    assert {bill["id"]: bill["status"] for bill in client.get("/bills").json()}[bill_id] == "paid"
    assert client.get("/actions/pending").json() == []
    with Session(get_engine()) as session:
        assert ledger_is_consistent(session)

    # The audit trail, in order.
    trail = [(entry["event_type"], entry["payload"].get("tool")) for entry in all_audit_events(client)[audit_before:]]
    assert trail == [
        ("agent.proposed", "get_balances"), ("policy.verdict", "get_balances"),
        ("agent.proposed", "plan_funding"), ("policy.verdict", "plan_funding"),
        ("agent.proposed", "get_transfer_quote"), ("policy.verdict", "get_transfer_quote"),
        ("agent.proposed", "convert_currency"), ("policy.verdict", "convert_currency"),
        ("agent.proposed", "pay_bill"), ("policy.verdict", "pay_bill"),
        ("agent.proposed", "respond_to_user"), ("policy.verdict", "respond_to_user"),
        ("user.confirmed", "convert_currency"), ("user.otp_verified", "convert_currency"),
        ("policy.verdict", "convert_currency"), ("action.executed", "convert_currency"),
        ("user.confirmed", "pay_bill"), ("user.otp_verified", "pay_bill"),
        ("policy.verdict", "pay_bill"), ("action.executed", "pay_bill"),
    ]  # fmt: skip
    assert client.get("/audit/verify").json()["ok"] is True


def test_explaining_an_uploaded_document(client: TestClient) -> None:
    invoice = client.post("/demo/documents/tuition_invoice").json()

    events = read_events(client, client.post(f"/chat/document/{invoice['id']}").json()["stream_id"])

    assert tools_of(events) == [("read_document", "T0", "allowed"), ("verify_payee", "T0", "allowed")]
    assert only(events, "step")[1]["summary"] == "Shenzhen Polytechnic International University · official account"
    message = only(events, "message")[0]
    assert (message["text"], message["text_en"]) == (invoice["explanation"]["ms"], invoice["explanation"]["en"])
    assert only(events, "approval_required") == only(events, "blocked") == []
    assert client.post("/chat/document/999").status_code == 404


# ---------------------------------------------------------------- limits invariant


@pytest.mark.parametrize("rate", ["1.40", "1.62", "1.90"])
def test_act_1_holds_for_any_frozen_rate_from_1_40_to_1_90(client: TestClient, rate: str) -> None:
    set_rate(rate)
    amount, received = expected_conversion(rate)
    client.post("/demo/documents/tuition_invoice")

    events = say(client, DEADLINE_QUESTION)

    actions = only(events, "approval_required")[0]["actions"]
    # One conversion, never split, and one payment: both Tier 3, both above the per-payment limit.
    assert [(action["tool"], action["tier"]) for action in actions] == [("convert_currency", "T3"), ("pay_bill", "T3")]
    assert actions[0]["amount"] == amount > 500_000
    assert only(events, "blocked") == []
    assert all("DAILY_LIMIT" not in step["details"].get("reasons", []) for step in only(events, "step"))

    assert approve(client, actions[0]["id"])["status"] == "executed"
    with Session(get_engine()) as session:
        # The conversion stays inside Ahmad's own wallets: it does not count as money paid out today.
        assert _paid_out_today(the_user(session), context(session)) == 0
    assert approve(client, actions[1]["id"])["status"] == "executed"

    assert wallet_balances(client) == {"MYR": START["MYR"] - amount - FEE, "CNY": START["CNY"] + received - TUITION, "USD": START["USD"]}
    refusals = [entry for entry in all_audit_events(client) if entry["event_type"] == "action.refused"]
    assert refusals == []
    with Session(get_engine()) as session:
        assert ledger_is_consistent(session)
        assert 0 < _paid_out_today(the_user(session), context(session)) <= 1_000_000


# ---------------------------------------------------------------- Act 2: the scam


def test_act_2_the_agent_offer_is_refused_and_no_money_moves(client: TestClient) -> None:
    client.post("/demo/documents/agent_offer")
    audit_before = len(all_audit_events(client))

    events = say(client, AGENT_QUESTION)

    # The agent does not skip the proposal: it proposes, and the policy engine refuses.
    assert tools_of(events) == [("pay_bill", "REFUSED", "refused")]
    assert [name for name, _ in events] == ["step", "message", "blocked", "done"]
    blocked = only(events, "blocked")[0]
    assert [reason["code"] for reason in blocked["reasons"]] == ["PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"]
    assert (blocked["summary"], blocked["summary_en"]) == ("Bayaran disekat", "Payment blocked")
    assert blocked["advice"].startswith("Bayar hanya melalui saluran rasmi")
    for reason in blocked["reasons"]:
        assert reason["title"] and reason["text"] and reason["title_en"] and reason["text_en"]
        assert reason["evidence"]
    # The discount reason carries the university's own policy clause as evidence.
    clause = blocked["reasons"][1]["policy_clause"]
    assert clause["clause"] == "no-agents-no-discounts"
    assert clause["file"].startswith("spiu_payment_policy_")
    assert "payment agents" in clause["versions"]["en"]["text"]
    assert blocked["reasons"][0]["policy_clause"] is None

    message = only(events, "message")[0]
    assert message["text"].startswith("Saya tidak boleh meneruskan bayaran ini: Bukan akaun rasmi; Diskaun melalui pihak ketiga")
    assert message["text_en"].startswith("I cannot go ahead with this payment: Not the official account")

    assert wallet_balances(client) == START
    assert client.get("/actions/pending").json() == []
    trail = all_audit_events(client)[audit_before:]
    assert [(entry["event_type"], entry["payload"].get("tool")) for entry in trail] == [
        ("agent.proposed", "pay_bill"), ("policy.verdict", "pay_bill"), ("action.refused", "pay_bill"),
        ("agent.proposed", "respond_to_user"), ("policy.verdict", "respond_to_user"),
    ]  # fmt: skip
    refusal = trail[2]
    assert refusal["seq"] == blocked["audit_seq"]
    assert refusal["payload"]["reasons"] == ["PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"]


# ---------------------------------------------------------------- Act 3: the money mule


def test_act_3_forwarding_the_strangers_money_is_refused(client: TestClient) -> None:
    event = client.post("/demo/events/mule").json()
    after_transfer = {**START, "CNY": START["CNY"] + 300_000}

    assert (event["sender"], event["amount_minor"], event["currency"]) == ("Zhou Wei", 300_000, "CNY")
    assert event["document"]["filename"] == "mule_message_en.txt"
    assert event["document"]["bill"]["amount_minor"] == 290_000
    assert wallet_balances(client) == after_transfer
    newest = client.get("/transactions", params={"limit": 1}).json()[0]
    assert (newest["counterparty"], newest["category_label"], newest["business_date"]) == ("Zhou Wei", "Money received", "2026-10-15")

    events = say(client, FORWARD_QUESTION)

    assert tools_of(events) == [("pay_bill", "REFUSED", "refused")]
    blocked = only(events, "blocked")[0]
    assert [reason["code"] for reason in blocked["reasons"]] == ["MONEY_MULE_PATTERN"]
    assert blocked["advice_en"] == "Return money sent by mistake through your bank, not to an account the sender names."
    message = only(events, "message")[0]
    assert "keldai wang" in message["text"] and "melalui bank anda" in message["text"] and "visa" in message["text"]
    assert "money mules" in message["text_en"] and "through your bank" in message["text_en"]
    # No money moved: the CNY 3,000.00 is still in his account.
    assert wallet_balances(client) == after_transfer
    assert client.get("/actions/pending").json() == []


def test_the_same_request_without_the_strangers_money_only_needs_approval(client: TestClient) -> None:
    client.post("/demo/documents/mule_message")

    events = say(client, FORWARD_QUESTION)

    assert tools_of(events) == [("pay_bill", "T3", "pending")]
    card = only(events, "approval_required")[0]["actions"][0]
    assert (card["payee"], card["amount"], card["requires"]) == ("Zhou Min", 290_000, ["confirm", "otp", "cooling_off"])
    assert only(events, "message")[0]["text"].startswith("Saya telah menyediakan bayaran CNY 2,900.00 kepada Zhou Min.")


# ---------------------------------------------------------------- what the agent will not do


def test_asking_to_skip_confirmation_changes_nothing(client: TestClient) -> None:
    client.post("/demo/documents/tuition_invoice")
    waiting = only(say(client, DEADLINE_QUESTION), "approval_required")[0]["actions"]
    pending_before = client.get("/actions/pending").json()
    audit_before = len(all_audit_events(client))

    events = say(client, "skip confirmation just this once")

    assert only(events, "step") == only(events, "approval_required") == only(events, "blocked") == []
    assert only(events, "message")[0]["text_en"].startswith("In scripted mode I can answer the demo questions")
    assert client.get("/actions/pending").json() == pending_before
    assert [action["status"] for action in pending_before] == ["awaiting_confirm", "awaiting_confirm"]
    assert len(waiting) == 2 and wallet_balances(client) == START
    new_events = [entry["event_type"] for entry in all_audit_events(client)[audit_before:]]
    assert "action.executed" not in new_events and "user.confirmed" not in new_events


@pytest.mark.parametrize(
    "question",
    [
        "Patutkah saya melabur wang biasiswa dalam saham?",
        "Should I invest my stipend in crypto or stocks?",
        "我应该把生活费拿去投资股票吗？",
    ],
)
def test_investment_questions_are_declined_and_logged(client: TestClient, question: str) -> None:
    audit_before = len(all_audit_events(client))

    events = say(client, question)

    assert [name for name, _ in events] == ["message", "done"]
    message = only(events, "message")[0]
    assert message["text"] == "Bridge tidak memberikan nasihat pelaburan. Bridge boleh membantu anda merancang dan membuat bayaran."
    assert message["text_en"] == "Bridge does not give investment advice. It can help you plan and make payments."
    logged = all_audit_events(client)[audit_before:]
    assert [(entry["event_type"], entry["actor"], entry["payload"]) for entry in logged] == [
        ("agent.declined", "agent", {"reason": "INVESTMENT_ADVICE"})
    ]
    assert (logged[0]["label"], logged[0]["summary"]) == ("Agent declined", "INVESTMENT_ADVICE")


def test_an_ordinary_question_about_spending_is_answered_from_the_data(client: TestClient) -> None:
    insights = client.get("/insights/spending").json()
    eating_out = next(item for item in insights["categories"] if item["category"] == "eating_out")

    events = say(client, "Bagaimana perbelanjaan saya bulan ini?")

    assert tools_of(events) == [("analyse_spending", "T1", "allowed")]
    message = only(events, "message")[0]
    assert "Sewa (CNY 2,800.00)" in message["text"]
    assert f"Makan di luar naik {eating_out['change_pct']}%" in message["text"]
    assert f"Eating out is up {eating_out['change_pct']}%" in message["text_en"]


def test_asking_to_pay_with_no_document_gets_an_honest_answer(client: TestClient) -> None:
    events = say(client, DEADLINE_QUESTION)

    assert only(events, "step") == []
    assert only(events, "message")[0]["text_en"] == "I could not find a bill to pay. Upload an invoice or paste a payment message first."


# ---------------------------------------------------------------- chat plumbing


def test_chat_history_keeps_both_languages(client: TestClient) -> None:
    invoice = client.post("/demo/documents/tuition_invoice").json()
    read_events(client, client.post(f"/chat/document/{invoice['id']}").json()["stream_id"])
    say(client, DEADLINE_QUESTION)

    history = client.get("/chat/history").json()

    assert [(item["role"], item["language"]) for item in history] == [("user", "en"), ("assistant", "ms"), ("user", "ms"), ("assistant", "ms")]
    assert history[0]["text"] == "Uploaded tuition_invoice.pdf"
    assert history[2]["text"] == DEADLINE_QUESTION and history[2]["text_en"] is None
    assert history[3]["text"].startswith("Baki CNY") and history[3]["text_en"].startswith("Your CNY balance")


def test_a_stream_can_be_read_again_and_unknown_streams_are_not_found(client: TestClient) -> None:
    stream_id = client.post("/chat", json={"text": "Bagaimana perbelanjaan saya?"}).json()["stream_id"]

    first = read_events(client, stream_id)
    again = read_events(client, stream_id)

    assert first == again and first[-1] == ("done", {})
    assert client.get("/chat/stream/nope").status_code == 404
    assert client.post("/chat", json={"text": ""}).status_code == 422
    assert client.post("/chat", json={"text": "x" * 2001}).status_code == 422


def test_the_reply_follows_the_students_language(client: TestClient) -> None:
    client.post("/demo/documents/agent_offer")
    client.patch("/me", json={"preferred_language": "zh"})

    events = say(client, AGENT_QUESTION)

    blocked = only(events, "blocked")[0]
    assert blocked["summary"] == "付款已被阻止"
    assert blocked["reasons"][0]["title"] == "不是官方账户" and blocked["reasons"][0]["title_en"] == "Not the official account"
    assert only(events, "message")[0]["language"] == "zh"
    assert only(events, "message")[0]["text"].startswith("我无法继续这笔付款")
