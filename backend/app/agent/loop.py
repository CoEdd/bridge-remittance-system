"""
The agent loop: one turn of the conversation.

The driver (scripted or Claude) proposes one tool call at a time. Every proposal goes
through actions.propose, so the policy engine judges it and the audit log records it.
Read and suggest tools then run and their result goes back to the driver. Money actions
become pending actions under one plan and wait for the student. A refusal ends the turn
as blocked. Nothing in this module can execute a payment.
"""

import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import actions, audit, documents
from app.agent import replies
from app.agent.tools import MONEY_TOOLS, TOOLS, ToolContext, action_summary, result_summary
from app.agent.types import Driver, ToolCall, ToolResult, Trigger, TurnContext
from app.clock import demo_today, now_utc
from app.config import effective_agent_mode
from app.db import write_lock
from app.documents.languages import main_language
from app.llm import LlmUnavailable
from app.models import Account, AuditLog, Bill, ChatMessage, Document, PendingAction, User
from app.policy import requires_for

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 8
HISTORY_MESSAGES = 10

Emit = Callable[[str, dict[str, Any]], None]


def build_context(session: Session, user: User) -> TurnContext:
    """Facts for the driver, read from the database by plain code."""
    wallets = session.scalars(select(Account).where(Account.user_id == user.id).order_by(Account.id))
    open_bills = list(
        session.scalars(select(Bill).where(Bill.user_id == user.id, Bill.status == "open").order_by(Bill.id))
    )

    def summary(bill: Bill) -> dict[str, Any]:
        return {
            "bill_id": bill.id,
            "payee_id": bill.payee_id,
            "payee_name": bill.payee.name,
            "amount_minor": bill.amount_minor,
            "currency": bill.currency,
            "due_date": bill.due_date.isoformat() if bill.due_date else None,
            "flagged": documents.bill_is_flagged(bill),
        }

    latest = session.scalars(
        select(Document).where(Document.user_id == user.id).order_by(Document.id.desc()).limit(1)
    ).first()
    latest_summary = None
    if latest is not None:
        bill = next((item for item in open_bills if item.document_id == latest.id), None)
        latest_summary = {
            "document_id": latest.id,
            "filename": latest.filename,
            "kind": latest.kind,
            "status": documents.document_status(latest, bill is not None),
            "bill_id": bill.id if bill else None,
            "bill": summary(bill) if bill else None,
        }
    payable = [
        bill
        for bill in open_bills
        if bill.document is not None and bill.document.kind == "invoice" and not documents.bill_is_flagged(bill)
    ]
    return TurnContext(
        language=user.preferred_language,
        student_name=user.name,
        demo_today=demo_today(),
        accounts={wallet.currency: wallet.id for wallet in wallets},
        latest_document=latest_summary,
        payable_invoice_bill_id=payable[-1].id if payable else None,
        open_bills=[summary(bill) for bill in open_bills],
    )


def _history(session: Session, before_id: int) -> list[dict[str, str]]:
    """Earlier chat messages for the live driver, oldest first, alternating and starting with the user."""
    rows = list(
        session.scalars(
            select(ChatMessage).where(ChatMessage.id < before_id).order_by(ChatMessage.id.desc()).limit(HISTORY_MESSAGES)
        )
    )[::-1]
    history: list[dict[str, str]] = []
    for row in rows:
        if history and history[-1]["role"] == row.role:
            history[-1]["content"] += "\n" + row.text
        elif history or row.role == "user":
            history.append({"role": row.role, "content": row.text})
    if history and history[-1]["role"] == "user":
        history.pop()  # the next entry must be the new user message
    return history


def make_driver(session: Session, trigger: Trigger, context: TurnContext, user_message_id: int) -> Driver:
    if effective_agent_mode() == "live":
        from app.agent.live import LiveDriver

        return LiveDriver(trigger, context, _history(session, user_message_id))
    from app.agent.scripted import ScriptedDriver

    return ScriptedDriver(trigger, context)


def _store(session: Session, role: str, text: str, text_en: str | None, language: str, now: datetime) -> ChatMessage:
    message = ChatMessage(role=role, text=text, text_en=text_en, language=language, created_at=now)
    session.add(message)
    session.commit()
    return message


def _reasons_for_user(action: PendingAction, language: str, bill: Bill | None) -> list[dict[str, Any]]:
    """The policy's reasons in the student's language and English, each with its evidence."""
    signals = {}
    if bill is not None and bill.document is not None:
        signals = {signal["code"]: signal for signal in documents.policy_signals(bill.document)}
    return [
        {
            "code": item["code"],
            "severity": item["severity"],
            "title": item["title"][language],
            "text": item["text"][language],
            "title_en": item["title"]["en"],
            "text_en": item["text"]["en"],
            "evidence": signals.get(item["code"], {}).get("evidence", []),
            "policy_clause": signals.get(item["code"], {}).get("policy_clause"),
        }
        for item in action.reasons
    ]


def _bill_of(session: Session, action: PendingAction) -> Bill | None:
    bill_id = (action.args or {}).get("bill_id") if action.tool == "pay_bill" else None
    return session.get(Bill, bill_id) if isinstance(bill_id, int) else None


def _action_card(session: Session, action: PendingAction, language: str) -> dict[str, Any]:
    """One pending action as the approval sheet needs it."""
    breakdown = action.cost_breakdown or {}
    codes = [item["code"] for item in action.reasons]
    return {
        "id": action.id,
        "tool": action.tool,
        "tier": action.tier,
        "summary": action_summary(action.tool, breakdown),
        "amount": breakdown.get("amount_minor"),
        "currency": breakdown.get("currency") or breakdown.get("from_currency"),
        "payee": breakdown.get("payee_name") or breakdown.get("name"),
        "cost_breakdown": breakdown,
        "reasons": _reasons_for_user(action, language, _bill_of(session, action)),
        "requires": requires_for(action.tier, codes),
        "expires_at": action.expires_at.isoformat() if action.expires_at else None,
    }


def shared_line(document: Document | None) -> str:
    """The student's side of a turn that starts with a document instead of a typed message."""
    if document is None:
        return "Shared a document"
    if document.source == "paste":
        return "Pasted a message"
    if document.source == "demo event":
        return f"Received a message: {document.filename}"
    return f"Uploaded {document.filename}"


def run_turn(session: Session, user: User, trigger: Trigger, emit: Emit, driver: Driver | None = None) -> None:
    """Run one turn and emit its events: step, message, approval_required or blocked, then done."""
    language = user.preferred_language
    recorded: list[dict[str, Any]] = []

    def record(name: str, payload: dict[str, Any]) -> None:
        if name != "message":  # the message is the stored row itself
            recorded.append({"event": name, "data": payload})
        emit(name, payload)

    try:
        answer = _run(session, user, trigger, record, driver, language)
    except LlmUnavailable as error:
        logger.warning("The live agent failed: %s", error)
        session.rollback()
        text, text_en = replies.both(replies.error_reply(), language)
        answer = _store(session, "assistant", text, text_en, language, now_utc())
        record("error", {"message": text, "message_en": text_en})
        emit("message", {"text": text, "text_en": text_en, "language": language})
    # Keep the turn's events with the reply, as plain JSON, so the chat can be shown again later.
    answer.events = json.loads(json.dumps(recorded, ensure_ascii=False, default=str))
    session.commit()
    emit("done", {})


def _run(
    session: Session, user: User, trigger: Trigger, emit: Emit, driver: Driver | None, language: str
) -> ChatMessage:
    """The turn itself. Returns the stored reply."""
    if trigger.kind == "document":
        shown = shared_line(session.get(Document, trigger.document_id))
        user_message = _store(session, "user", shown, shown, "en", now_utc())
    else:
        user_message = _store(session, "user", trigger.text, None, main_language(trigger.text, language), now_utc())

    def finish(texts: tuple[str, str]) -> ChatMessage:
        answer = _store(session, "assistant", texts[0], texts[1], language, now_utc())
        emit("message", {"text": texts[0], "text_en": texts[1], "language": language})
        return answer

    # Content guard, before any driver runs: Bridge never gives investment advice.
    if trigger.kind == "message" and replies.is_investment_question(trigger.text):
        with write_lock:
            audit.append(session, "agent.declined", "agent", {"reason": "INVESTMENT_ADVICE"})
            session.commit()
        return finish(replies.both(replies.investment_declined(), language))

    context = build_context(session, user)
    driver = driver or make_driver(session, trigger, context, user_message.id)
    plan_id = f"plan-{uuid.uuid4().hex[:10]}"
    reply: tuple[str, str] | None = None
    refused: PendingAction | None = None
    pending_ids: list[int] = []
    results: list[ToolResult] = []
    calls = 0

    while reply is None and calls < MAX_TOOL_CALLS:
        batch = driver.next_calls(results)
        if not batch:
            break
        results = []
        for call in batch:
            if calls >= MAX_TOOL_CALLS:
                results.append(ToolResult(call, "error", {"error": "Too many tool calls in one turn."}))
                continue
            calls += 1
            if refused is not None and call.name != "respond_to_user":
                # After a refusal the only thing left to do is to tell the student.
                results.append(ToolResult(call, "error", {"error": "This turn is blocked. Reply to the student."}))
                continue
            result, action = _execute(session, user, call, plan_id, calls, emit)
            results.append(result)
            if result.verdict == "pending" and action is not None:
                pending_ids.append(action.id)
            elif result.verdict == "refused" and action is not None and call.name in MONEY_TOOLS:
                refused = refused or action
            elif call.name == "respond_to_user" and result.verdict == "allowed":
                reply = (str(call.args["text"]), str(call.args["text_en"]))

    if reply is None:
        # The driver never replied: say something true rather than nothing.
        if refused is not None:
            reply = replies.both(replies.blocked([item["code"] for item in refused.reasons]), language)
        elif calls >= MAX_TOOL_CALLS:
            reply = replies.both(replies.too_many_steps(), language)
        else:
            reply = replies.both(replies.fallback(), language)
    answer = finish(reply)

    if refused is not None:
        codes = [item["code"] for item in refused.reasons]
        advice = replies.advice_for(codes)
        refusal_entry = session.scalars(
            select(AuditLog).where(AuditLog.event_type == "action.refused").order_by(AuditLog.seq.desc())
        ).first()
        emit(
            "blocked",
            {
                "action_id": refused.id,
                "tool": refused.tool,
                "summary": replies.BLOCKED_TITLE[language],
                "summary_en": replies.BLOCKED_TITLE["en"],
                "reasons": _reasons_for_user(refused, language, _bill_of(session, refused)),
                "advice": advice[language],
                "advice_en": advice["en"],
                "audit_seq": refusal_entry.seq if refusal_entry else None,
            },
        )
    elif pending_ids:
        waiting = [session.get_one(PendingAction, action_id) for action_id in pending_ids]
        emit(
            "approval_required",
            {"plan_id": plan_id, "actions": [_action_card(session, action, language) for action in waiting]},
        )
    return answer


def _execute(
    session: Session, user: User, call: ToolCall, plan_id: str, step_id: int, emit: Emit
) -> tuple[ToolResult, PendingAction | None]:
    """Propose one tool call (policy verdict and audit entries), then run it if it is a read or suggest tool."""
    tool = TOOLS.get(call.name)
    is_money = call.name in MONEY_TOOLS
    proposal = actions.propose(session, user, call.name, call.args, plan_id if is_money else None)
    verdict = proposal.verdict
    action = proposal.action

    if proposal.status == "allowed" and tool is not None and tool.handler is not None:
        try:
            parsed = tool.input_model.model_validate(call.args)
            data = tool.handler(ToolContext(session, user, demo_today(), now_utc()), parsed)
            outcome = "error" if "error" in data else "allowed"
        except ValidationError as error:
            fields = ", ".join(str(item["loc"][0]) for item in error.errors() if item["loc"]) or "input"
            data, outcome = {"error": f"Invalid arguments: {fields}."}, "error"
        summary = result_summary(call.name, data)
    else:
        codes = [item.code for item in verdict.reasons]
        outcome = "pending" if proposal.status == "pending" else "refused"
        data = {
            "status": outcome,
            "action_id": action.id if action else None,
            "tier": verdict.tier,
            "requires": verdict.requires,
            "reasons": codes,
            "cost_breakdown": verdict.cost_breakdown,
        }
        summary = action_summary(call.name, verdict.cost_breakdown) if is_money else ", ".join(codes)
        if outcome == "refused" and codes:
            summary = f"{summary} · {codes[0]}{f' +{len(codes) - 1} more' if len(codes) > 1 else ''}" if is_money else summary

    if call.name != "respond_to_user":
        why = replies.why(verdict.tier, [item.code for item in verdict.reasons])
        emit(
            "step",
            {
                "id": step_id,
                "tool": call.name,
                "label": tool.label if tool else call.name,
                "tier": verdict.tier,
                "verdict": "refused" if outcome == "refused" else "pending" if outcome == "pending" else "allowed",
                "summary": summary,
                "why": why[user.preferred_language],
                "why_en": why["en"],
                "input": call.args,
                "details": data,
            },
        )
    return ToolResult(call, outcome, data), action
