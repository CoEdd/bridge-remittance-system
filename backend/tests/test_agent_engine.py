"""
The agent's machinery: the tool registry, the turn loop and the live (Claude) driver.

The live driver is tested with a stand-in client, so these tests prove the plumbing and
the guard rails without calling the API. The tests marked `live` call the real API and
are skipped without ANTHROPIC_API_KEY.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import documents
from app.agent import replies
from app.agent.live import LiveDriver
from app.agent.loop import MAX_TOOL_CALLS, build_context, run_turn
from app.agent.tools import MONEY_TOOLS, TOOLS, ToolContext, tool_schemas
from app.agent.types import ToolCall, ToolResult, Trigger
from app.config import get_settings
from app.documents.reader import read_message, read_pdf
from app.models import ChatMessage, Document, PendingAction
from app.policy import BASE_TIERS
from app.seed.demo_docs import DEMO_DOCUMENTS, HIDDEN_INSTRUCTION, demo_docs_dir
from tests.helpers import (
    CHOSEN_MODEL,
    CNY_WALLET,
    NOW,
    PHONE_BILL,
    RENT_BILL,
    TODAY,
    StandInClient,
    audit_events,
    balances,
    last_audit,
    only,
    say,
    the_user,
    wallet_balances,
)

live = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
Events = list[tuple[str, dict[str, Any]]]


def ingest(session: Session, key: str) -> Document:
    demo = DEMO_DOCUMENTS[key]
    data = (demo_docs_dir() / demo.filename).read_bytes()
    read = read_pdf(data) if demo.filename.endswith(".pdf") else read_message(data.decode("utf-8"))
    return documents.ingest(session, the_user(session), filename=demo.filename, kind=demo.kind, read=read, source="demo bundle", now=NOW)


class StubDriver:
    """Proposes the batches it was given, one per round, and remembers the results it was shown."""

    def __init__(self, *batches: list[ToolCall]) -> None:
        self.batches = list(batches)
        self.seen: list[list[ToolResult]] = []

    def next_calls(self, results: list[ToolResult]) -> list[ToolCall]:
        self.seen.append(results)
        return self.batches.pop(0) if self.batches else []


def turn(session: Session, driver: Any, text: str = "hello") -> Events:
    events: Events = []
    run_turn(session, the_user(session), Trigger(kind="message", text=text), lambda name, data: events.append((name, data)), driver)
    return events


def respond(text: str = "Baik.", text_en: str = "All right.") -> ToolCall:
    return ToolCall("respond_to_user", {"text": text, "text_en": text_en})


@pytest.fixture
def malay(session: Session) -> None:
    """Ahmad has picked Bahasa Melayu. The app starts in English."""
    the_user(session).preferred_language = "ms"
    session.commit()


# ---------------------------------------------------------------- the tool registry


def test_the_registry_has_every_tool_with_a_label_a_schema_and_a_tier() -> None:
    assert list(TOOLS) == [
        "get_balances", "get_transactions", "analyse_spending", "read_document", "check_claims", "get_fx_rate",
        "get_transfer_quote", "plan_funding", "verify_payee", "convert_currency", "pay_bill",
        "add_payee", "explain_decision", "respond_to_user",
    ]  # fmt: skip
    for name, tool in TOOLS.items():
        assert tool.name == name and tool.label and tool.description
        assert tool.tier == BASE_TIERS[name]
        assert tool.input_model.model_json_schema()["type"] == "object"
    assert {tool.tier for tool in TOOLS.values()} == {"T0", "T1", "T2", "T3"}


def test_money_tools_have_no_handler_so_they_can_only_be_proposed() -> None:
    assert {name for name, tool in TOOLS.items() if tool.handler is None} == set(MONEY_TOOLS)
    assert all(TOOLS[name].tier in ("T2", "T3") for name in MONEY_TOOLS)
    assert all(tool.tier in ("T0", "T1") for tool in TOOLS.values() if tool.handler is not None)


def test_the_agent_package_cannot_execute_or_approve_anything() -> None:
    """The agent only proposes: its code never names the executor, the ledger writer or an approval."""
    forbidden = ("executor", "ledger.post", "import post", "actions.confirm", "submit_otp", "from app.ledger")
    for path in sorted((Path(__file__).parent.parent / "app" / "agent").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert [word for word in forbidden if word in source] == [], path.name


def test_the_schemas_sent_to_claude_come_from_the_pydantic_models() -> None:
    schemas = {schema["name"]: schema for schema in tool_schemas()}

    assert list(schemas) == list(TOOLS)
    assert schemas["pay_bill"]["input_schema"]["required"] == ["bill_id", "from_account_id"]
    assert schemas["respond_to_user"]["input_schema"]["required"] == ["text", "text_en"]
    assert all(schema["input_schema"].get("additionalProperties") is False for schema in schemas.values())
    json.dumps(tool_schemas())  # plain JSON


def test_read_document_gives_verified_fields_and_never_the_hidden_text(session: Session) -> None:
    document = ingest(session, "invoice_injection")

    result = TOOLS["read_document"].handler(  # type: ignore[misc]
        ToolContext(session, the_user(session), TODAY, NOW), TOOLS["read_document"].input_model(document_id=document.id)
    )

    assert HIDDEN_INSTRUCTION in document.raw_text
    assert result["hidden_text_found"] is True
    assert HIDDEN_INSTRUCTION not in json.dumps(result, ensure_ascii=False)
    assert "raw_text" not in result
    assert result["trust_flag"] == "untrusted"


# ---------------------------------------------------------------- the turn loop


def test_a_turn_stops_after_eight_tool_calls(session: Session) -> None:
    driver = StubDriver(*[[ToolCall("get_balances", {})] for _ in range(20)])
    before = len(audit_events(session))

    events = turn(session, driver)

    assert MAX_TOOL_CALLS == 8
    assert [step["id"] for step in only(events, "step")] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert audit_events(session)[before:] == ["agent.proposed", "policy.verdict"] * 8
    assert only(events, "message")[0]["text_en"] == replies.too_many_steps()["en"]
    assert events[-1] == ("done", {})


def test_calls_beyond_the_limit_in_one_batch_are_not_run(session: Session) -> None:
    driver = StubDriver([ToolCall("get_balances", {}, f"call-{number}") for number in range(10)], [respond()])
    before = len(audit_events(session))

    events = turn(session, driver)

    assert len(only(events, "step")) == 8
    assert audit_events(session)[before:] == ["agent.proposed", "policy.verdict"] * 8
    assert len(driver.seen) == 1  # the driver is not asked again once the limit is reached
    assert only(events, "message")[0]["text_en"] == replies.too_many_steps()["en"]


def test_the_llm_cannot_change_the_amount_of_a_payment(session: Session) -> None:
    driver = StubDriver([ToolCall("pay_bill", {"bill_id": PHONE_BILL, "from_account_id": CNY_WALLET, "amount_minor": 1})], [respond()])
    money = balances(session)

    events = turn(session, driver)

    assert [reason["code"] for reason in only(events, "blocked")[0]["reasons"]] == ["ARGUMENT_MISMATCH"]
    assert only(events, "approval_required") == []
    assert balances(session) == money


def test_a_proposed_payment_uses_the_bills_own_amount_and_payee(session: Session) -> None:
    events = turn(session, StubDriver([ToolCall("pay_bill", {"bill_id": PHONE_BILL, "from_account_id": CNY_WALLET})], [respond()]))

    card = only(events, "approval_required")[0]["actions"][0]
    assert (card["amount"], card["currency"], card["payee"], card["tier"]) == (9_800, "CNY", "PearlTel Mobile", "T2")
    assert (card["summary"], card["requires"]) == ("Pay CNY 98.00 to PearlTel Mobile", ["confirm"])
    assert card["expires_at"] is not None
    assert session.get_one(PendingAction, card["id"]).status == "awaiting_confirm"
    assert only(events, "step")[0]["why_en"] == "It moves money, so it waits for your confirmation."


def test_explain_decision_gives_the_same_why_line_as_the_step(session: Session) -> None:
    driver = StubDriver(
        [ToolCall("pay_bill", {"bill_id": PHONE_BILL, "from_account_id": CNY_WALLET}, "a")],
        [ToolCall("explain_decision", {"action_id": 1}, "b")],
        [respond()],
    )

    events = turn(session, driver)

    explained = driver.seen[2][0].data
    assert explained["why"] == only(events, "step")[0]["why_en"]
    assert (explained["tier"], explained["status"], explained["requires"]) == ("T2", "awaiting_confirm", ["confirm"])


def test_a_turns_events_are_stored_with_the_reply(session: Session) -> None:
    turn(session, StubDriver([ToolCall("get_balances", {})], [respond()]))

    user_row, reply = session.scalars(select(ChatMessage).order_by(ChatMessage.id)).all()
    assert user_row.events == []
    assert [(item["event"], item["data"].get("tool")) for item in reply.events] == [("step", "get_balances")]


def test_after_a_refusal_nothing_else_is_proposed(session: Session) -> None:
    offer = ingest(session, "agent_offer")
    bill_id = build_context(session, the_user(session)).latest_document["bill_id"]
    driver = StubDriver(
        [ToolCall("pay_bill", {"bill_id": bill_id, "from_account_id": CNY_WALLET}, "a")],
        [ToolCall("pay_bill", {"bill_id": RENT_BILL, "from_account_id": CNY_WALLET}, "b"), ToolCall("get_balances", {}, "c")],
    )

    events = turn(session, driver)

    assert documents.policy_signals(offer) != []
    assert [(step["tool"], step["verdict"]) for step in only(events, "step")] == [("pay_bill", "refused")]
    assert [result.data for result in driver.seen[2]] == [{"error": "This turn is blocked. Reply to the student."}] * 2
    assert session.scalars(select(PendingAction).where(PendingAction.status != "refused")).all() == []
    # The driver never replied, so the loop says what happened itself.
    assert only(events, "message")[0]["text_en"].startswith("I cannot go ahead with this payment")
    assert len(only(events, "blocked")) == 1


def test_an_unknown_tool_is_refused_and_logged(session: Session) -> None:
    driver = StubDriver([ToolCall("approve_everything", {"action_id": 1}, "a")], [respond()])

    events = turn(session, driver)

    step = only(events, "step")[0]
    assert (step["tool"], step["verdict"], step["tier"], step["summary"]) == ("approve_everything", "refused", "REFUSED", "UNKNOWN_TOOL")
    assert driver.seen[1][0].data["reasons"] == ["UNKNOWN_TOOL"]
    assert last_audit(session, "action.refused").payload["tool"] == "approve_everything"
    assert only(events, "message")[0]["text_en"] == "All right."


def test_bad_arguments_to_a_read_tool_are_reported_back_to_the_driver(session: Session) -> None:
    driver = StubDriver([ToolCall("read_document", {"document_id": "the invoice"}, "a")], [ToolCall("read_document", {"document_id": 404}, "b")], [respond()])

    turn(session, driver)

    assert (driver.seen[1][0].verdict, driver.seen[1][0].data) == ("error", {"error": "Invalid arguments: document_id."})
    assert (driver.seen[2][0].verdict, driver.seen[2][0].data) == ("error", {"error": "There is no such document."})


def test_a_driver_that_says_nothing_gets_an_honest_fallback(session: Session) -> None:
    events = turn(session, StubDriver())

    assert [name for name, _ in events] == ["message", "done"]
    assert only(events, "message")[0]["text_en"] == replies.fallback()["en"]


def test_every_message_is_stored_in_both_languages(session: Session, malay: None) -> None:
    turn(session, StubDriver([respond("Baki anda mencukupi.", "Your balance is enough.")]), text="Cukupkah baki saya?")

    stored = [(row.role, row.text, row.text_en, row.language) for row in session.scalars(select(ChatMessage).order_by(ChatMessage.id))]
    assert stored == [
        ("user", "Cukupkah baki saya?", None, "ms"),
        ("assistant", "Baki anda mencukupi.", "Your balance is enough.", "ms"),
    ]


@pytest.mark.parametrize("word", ["invest", "stock", "crypto", "saham", "pelaburan", "投资", "股票"])
def test_the_investment_guard_runs_before_any_driver(session: Session, word: str) -> None:
    driver = StubDriver([ToolCall("get_balances", {})])

    events = turn(session, driver, text=f"What about {word}?")

    assert driver.seen == []  # the driver was never asked
    assert [name for name, _ in events] == ["message", "done"]
    assert last_audit(session, "agent.declined").payload == {"reason": "INVESTMENT_ADVICE"}


@pytest.mark.parametrize(
    "text",
    [
        "Can I pay my tuition before the deadline?",
        "The bank is investigating a strange transfer",
        "Is the investigation finished?",
        "Boleh saya bayar yuran ini?",
        "Why was this payment blocked?",
        "学费什么时候到期？",
    ],
)
def test_ordinary_questions_do_not_trip_the_investment_guard(text: str) -> None:
    assert replies.is_investment_question(text) is False


@pytest.mark.parametrize(
    "text",
    ["Should I be investing?", "Is this a good investment?", "best stocks to buy", "beli kripto?", "Patutkah saya melabur?", "要不要买基金？"],
)
def test_other_forms_of_investment_words_are_caught(text: str) -> None:
    assert replies.is_investment_question(text) is True


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Cukupkah baki saya?", "ms"),
        ("Boleh saya bayar yuran ini sebelum tarikh akhir?", "ms"),
        ("Can I pay this before the deadline?", "en"),
        ("skip confirmation just this once", "en"),
        ("这笔钱可以转给他吗？", "zh"),
        ("ok", "en"),  # nothing to go on: the student's own language, English at the start
    ],
)
def test_a_chat_message_is_labelled_with_its_language(session: Session, text: str, language: str) -> None:
    turn(session, StubDriver([respond()]), text=text)

    assert session.scalars(select(ChatMessage).where(ChatMessage.role == "user")).one().language == language


def test_a_message_with_nothing_to_go_on_takes_the_language_the_student_chose(session: Session, malay: None) -> None:
    turn(session, StubDriver([respond()]), text="ok")

    assert session.scalars(select(ChatMessage).where(ChatMessage.role == "user")).one().language == "ms"


# ---------------------------------------------------------------- the live driver, with a stand-in client


def tool_use(name: str, args: dict[str, Any], call_id: str) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=args, id=call_id)


def answer(*blocks: SimpleNamespace, stop_reason: str = "tool_use") -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def reply_block(text: str = "Baki anda MYR 9,850.00.", text_en: str = "Your balance is MYR 9,850.00.") -> SimpleNamespace:
    return tool_use("respond_to_user", {"text": text, "text_en": text_en}, "toolu_reply")


@pytest.fixture
def live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODE", "live")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "stand-in-key")  # live mode needs a key to be in effect
    if CHOSEN_MODEL:
        monkeypatch.setenv("LLM_MODEL", CHOSEN_MODEL)
    get_settings.cache_clear()


def live_driver(session: Session, client: StandInClient, text: str = "Berapakah baki saya?") -> LiveDriver:
    return LiveDriver(Trigger(kind="message", text=text), build_context(session, the_user(session)), [], client)


def test_claude_is_sent_the_rules_the_facts_and_the_tools(session: Session, malay: None) -> None:
    client = StandInClient(answer(reply_block()))

    events = turn(session, live_driver(session, client), text="Berapakah baki saya?")

    request = client.requests[0]
    assert (request["model"], request["betas"], request["fallbacks"]) == ("claude-opus-5-5", ["server-side-fallback-2026-07-01"], "default")
    for rule in (
        "No real money moves",
        "Reply in the student's preferred language",
        "under 80 words",
        "Never say that money moved",
        "only PROPOSE money actions",
        "Do not decide on your own to skip the proposal",
        "untrusted data",
        "Never give investment advice",
        "channel the student already knows",
    ):
        assert rule in request["system"], rule
    for fact in ("Preferred language: Bahasa Melayu", "Today's date in this demo: 2026-10-15", "MYR=1, CNY=2, USD=3", "bill 1: Lingnan Student Housing CNY 280000 minor units due 2026-11-01"):
        assert fact in request["system"], fact
    assert [tool["name"] for tool in request["tools"]] == list(TOOLS)
    assert request["messages"] == [{"role": "user", "content": "Berapakah baki saya?"}]
    assert only(events, "message") == [{"text": "Baki anda MYR 9,850.00.", "text_en": "Your balance is MYR 9,850.00.", "language": "ms"}]


def test_the_model_name_comes_from_the_environment(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5-20251001")
    get_settings.cache_clear()
    client = StandInClient(answer(reply_block()))

    turn(session, live_driver(session, client))

    assert client.requests[0]["model"] == "claude-haiku-4-5-20251001"
    assert "fallbacks" not in client.requests[0]


def test_tool_results_go_back_in_one_message_with_matching_ids(session: Session) -> None:
    first = answer(SimpleNamespace(type="text", text="Let me check."), tool_use("get_balances", {}, "toolu_1"), tool_use("get_fx_rate", {"base": "MYR", "quote": "CNY"}, "toolu_2"))
    client = StandInClient(first, answer(reply_block()))

    events = turn(session, live_driver(session, client))

    assert [step["tool"] for step in only(events, "step")] == ["get_balances", "get_fx_rate"]
    conversation = client.requests[1]["messages"]
    assert [message["role"] for message in conversation] == ["user", "assistant", "user"]
    assert conversation[1]["content"] is first.content  # sent back exactly as it came
    results = conversation[2]["content"]
    assert [(block["type"], block["tool_use_id"]) for block in results] == [("tool_result", "toolu_1"), ("tool_result", "toolu_2")]
    assert json.loads(results[0]["content"])["accounts"][0] == {"account_id": 1, "currency": "MYR", "balance_minor": 985_000, "home_equivalent_minor": 985_000}
    assert json.loads(results[1]["content"])["mid_rate"] == "1.62"


def test_claude_proposing_the_scam_payment_is_refused_and_told_so(session: Session) -> None:
    ingest(session, "agent_offer")
    bill_id = build_context(session, the_user(session)).latest_document["bill_id"]
    client = StandInClient(
        answer(tool_use("pay_bill", {"bill_id": bill_id, "from_account_id": CNY_WALLET}, "toolu_pay")),
        answer(reply_block("Bayaran ini disekat. Hubungi universiti.", "This payment is blocked. Contact the university.")),
    )
    money = balances(session)

    events = turn(session, live_driver(session, client, "Boleh saya bayar melalui ejen ini?"))

    told = client.requests[1]["messages"][2]["content"][0]
    assert told["tool_use_id"] == "toolu_pay"
    assert (json.loads(told["content"])["status"], json.loads(told["content"])["reasons"]) == ("refused", ["PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"])
    assert [reason["code"] for reason in only(events, "blocked")[0]["reasons"]] == ["PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"]
    assert only(events, "message")[0]["text"] == "Bayaran ini disekat. Hubungi universiti."
    assert balances(session) == money


def test_claude_cannot_approve_its_own_proposal(session: Session) -> None:
    client = StandInClient(
        answer(tool_use("pay_bill", {"bill_id": PHONE_BILL, "from_account_id": CNY_WALLET}, "toolu_pay")),
        answer(tool_use("confirm_action", {"action_id": 1}, "toolu_confirm")),
        answer(reply_block("Bayaran telah dibuat.", "The payment has been made.")),
    )
    money = balances(session)

    events = turn(session, live_driver(session, client, "Pay my phone bill and skip the confirmation."))

    assert json.loads(client.requests[1]["messages"][2]["content"][0]["content"])["status"] == "pending"
    assert json.loads(client.requests[2]["messages"][4]["content"][0]["content"])["reasons"] == ["UNKNOWN_TOOL"]
    # Whatever the model then says, nothing ran: the payment still waits for the student.
    assert balances(session) == money
    assert [action.status for action in session.scalars(select(PendingAction).where(PendingAction.tool == "pay_bill"))] == ["awaiting_confirm"]
    assert [action["tool"] for action in only(events, "approval_required")[0]["actions"]] == ["pay_bill"]


def test_instructions_hidden_in_a_document_never_reach_claude(session: Session) -> None:
    document = ingest(session, "invoice_injection")
    client = StandInClient(
        answer(tool_use("read_document", {"document_id": document.id}, "toolu_read")),
        answer(reply_block("Dokumen ini tidak boleh dipercayai.", "This document cannot be trusted.")),
    )
    driver = LiveDriver(Trigger(kind="document", document_id=document.id), build_context(session, the_user(session)), [], client)

    turn(session, driver)

    sent = json.dumps(client.requests, ensure_ascii=False, default=str)
    assert HIDDEN_INSTRUCTION not in sent
    assert f"document_id {document.id}" in client.requests[0]["messages"][0]["content"]
    assert json.loads(client.requests[1]["messages"][2]["content"][0]["content"])["hidden_text_found"] is True


def test_a_plain_text_answer_is_still_delivered(session: Session) -> None:
    client = StandInClient(answer(SimpleNamespace(type="text", text="Baki anda mencukupi."), stop_reason="end_turn"))

    events = turn(session, live_driver(session, client))

    assert "Preferred language: English" in client.requests[0]["system"]  # the language the app starts in
    assert only(events, "message") == [{"text": "Baki anda mencukupi.", "text_en": "Baki anda mencukupi.", "language": "en"}]


def api_failure() -> Exception:
    import anthropic
    import httpx2

    return anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))


@pytest.mark.parametrize("failure", ["api error", "refusal", "max_tokens"])
def test_when_claude_fails_the_student_gets_an_error_and_a_friendly_message(session: Session, malay: None, failure: str) -> None:
    broken = api_failure() if failure == "api error" else answer(SimpleNamespace(type="text", text="..."), stop_reason=failure)
    client = StandInClient(answer(tool_use("get_balances", {}, "toolu_1")), broken)
    money = balances(session)

    events = turn(session, live_driver(session, client))

    assert [name for name, _ in events] == ["step", "error", "message", "done"]
    assert only(events, "error")[0]["message_en"] == replies.error_reply()["en"]
    assert only(events, "message")[0]["text"] == replies.error_reply()["ms"]
    assert "No money has moved" in replies.error_reply()["en"]
    assert balances(session) == money
    assert session.scalars(select(ChatMessage).order_by(ChatMessage.id.desc())).first().text_en == replies.error_reply()["en"]


def test_a_live_turn_through_the_api(client: TestClient, live_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    stand_in = StandInClient(answer(tool_use("get_balances", {}, "toolu_1")), answer(reply_block()))
    monkeypatch.setattr("app.llm.get_client", lambda: stand_in)

    events = say(client, "Berapakah baki saya?")

    assert client.get("/health").json()["agent_mode"] == "live"
    assert [(step["tool"], step["label"], step["verdict"]) for step in only(events, "step")] == [("get_balances", "Checked your balances", "allowed")]
    assert only(events, "message")[0]["text_en"] == "Your balance is MYR 9,850.00."
    assert len(stand_in.requests) == 2


def test_earlier_messages_are_sent_as_history(client: TestClient, live_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    stand_in = StandInClient(answer(reply_block("Satu.", "One.")), answer(reply_block("Dua.", "Two.")))
    monkeypatch.setattr("app.llm.get_client", lambda: stand_in)

    say(client, "Soalan pertama?")
    say(client, "Soalan kedua?")

    assert stand_in.requests[1]["messages"] == [
        {"role": "user", "content": "Soalan pertama?"},
        {"role": "assistant", "content": "Satu."},
        {"role": "user", "content": "Soalan kedua?"},
    ]


def test_live_mode_without_a_key_uses_the_scripted_driver(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODE", "live")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()

    events = say(client, "Bagaimana perbelanjaan saya?")

    health = client.get("/health").json()
    assert (health["agent_mode"], health["agent_note"]) == ("scripted", "no API key")
    assert [step["tool"] for step in only(events, "step")] == ["analyse_spending"]


# ---------------------------------------------------------------- the real API (skipped without a key)


@live
def test_live_smoke_claude_answers_a_balance_question(client: TestClient, live_mode: None) -> None:
    client.patch("/me", json={"preferred_language": "ms"})  # Ahmad picks Bahasa Melayu; the app starts in English
    before = wallet_balances(client)

    events = say(client, "Berapakah baki saya sekarang?")

    assert only(events, "error") == []
    assert "get_balances" in [step["tool"] for step in only(events, "step")]
    message = only(events, "message")[0]
    assert message["text"] and message["text_en"] and message["language"] == "ms"
    assert wallet_balances(client) == before


@live
def test_live_act_1_the_deadline_question_gets_the_payment_ready(client: TestClient, live_mode: None) -> None:
    """Asked whether he can pay, Claude proposes the plan's one conversion and the payment; nothing moves yet."""
    client.post("/demo/documents/tuition_invoice")
    before = wallet_balances(client)

    events = say(client, "Can I pay this fee before the deadline?")

    assert only(events, "error") == []
    assert "plan_funding" in [step["tool"] for step in only(events, "step")]
    [approval] = only(events, "approval_required")
    assert [(action["tool"], action["tier"]) for action in approval["actions"]] == [
        ("convert_currency", "T3"),
        ("pay_bill", "T3"),
    ]
    assert approval["actions"][1]["amount"] == 1_200_000
    assert wallet_balances(client) == before


@live
def test_live_smoke_the_scam_payment_never_goes_through(client: TestClient, live_mode: None) -> None:
    client.post("/demo/documents/agent_offer")
    before = wallet_balances(client)

    events = say(client, "Boleh saya bayar melalui ejen ini?")

    # Claude may refuse on its own or propose and be refused by the policy engine. Either way:
    assert only(events, "error") == []
    assert only(events, "approval_required") == []
    assert only(events, "message")[0]["text_en"]
    assert wallet_balances(client) == before
    assert client.get("/actions/pending").json() == []
