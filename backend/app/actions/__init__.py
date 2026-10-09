"""
Pending actions: propose, confirm, one-time code, cancel, and the background sweep.

The LLM proposes, the policy engine decides, the student approves. Every step is
written to the audit log in the same transaction as the change it describes.
"""

import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.actions import executor
from app.clock import demo_today, now_utc
from app.config import get_settings
from app.db import write_lock
from app.models import PendingAction, User
from app.policy import Context, Verdict, evaluate

APPROVAL_WINDOW = timedelta(minutes=15)
MAX_OTP_ATTEMPTS = 3
OPEN_STATUSES = ("awaiting_confirm", "awaiting_otp", "cooling_off")


class ActionError(Exception):
    """The request cannot be applied to this action."""

    def __init__(self, message: str, *, not_found: bool = False) -> None:
        super().__init__(message)
        self.not_found = not_found


@dataclass(frozen=True)
class Proposal:
    status: str  # allowed | pending | refused
    verdict: Verdict
    action: PendingAction | None = None


@dataclass(frozen=True)
class OtpResult:
    accepted: bool
    attempts_left: int
    action: PendingAction


def _verdict_payload(tool: str, verdict: Verdict, action_id: int | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool": tool,
        "tier": verdict.tier,
        "requires": verdict.requires,
        "reasons": [item.code for item in verdict.reasons],
        "stage": "proposal",
    }
    if action_id is not None:
        payload["action_id"] = action_id
    if verdict.cost_breakdown is not None:
        payload["cost_breakdown"] = verdict.cost_breakdown
    return payload


def propose(
    session: Session,
    user: User,
    tool: str,
    args: dict[str, Any],
    plan_id: str | None = None,
    *,
    now: datetime | None = None,
) -> Proposal:
    """
    Ask the policy engine about one tool call.

    T0 and T1 get the go-ahead. T2 and T3 become a pending action that waits for the
    student. A refusal is recorded and never runs.
    """
    now = now or now_utc()
    with write_lock:
        verdict = evaluate(user, tool, args, Context(session, demo_today(), now, plan_id=plan_id))
        audit.append(session, "agent.proposed", "agent", {"tool": tool, "args": args, "plan_id": plan_id}, now=now)

        if verdict.tier in ("T0", "T1"):
            audit.append(session, "policy.verdict", "policy", _verdict_payload(tool, verdict, None), now=now)
            session.commit()
            return Proposal("allowed", verdict)

        refused = verdict.tier == "REFUSED"
        action = PendingAction(
            user_id=user.id,
            plan_id=plan_id,
            tool=tool,
            args=args,
            tier=verdict.tier,
            status="refused" if refused else "awaiting_confirm",
            reasons=executor.reasons_as_json(verdict.reasons),
            cost_breakdown=verdict.cost_breakdown,
            created_at=now,
            expires_at=None if refused else now + APPROVAL_WINDOW,
        )
        session.add(action)
        session.flush()
        audit.append(session, "policy.verdict", "policy", _verdict_payload(tool, verdict, action.id), now=now)
        if refused:
            audit.append(
                session,
                "action.refused",
                "policy",
                {
                    "action_id": action.id,
                    "tool": tool,
                    "reasons": [item.code for item in verdict.reasons],
                    "stage": "proposal",
                },
                now=now,
            )
        session.commit()
        return Proposal("refused" if refused else "pending", verdict, action)


def _load(session: Session, user: User, action_id: int, expected: tuple[str, ...], now: datetime) -> PendingAction:
    """Fetch an action that must be in one of the `expected` states and not past its deadline."""
    action = session.get(PendingAction, action_id)
    if action is None or action.user_id != user.id:
        raise ActionError("There is no such action.", not_found=True)
    if action.status in ("awaiting_confirm", "awaiting_otp") and action.expires_at and action.expires_at <= now:
        _expire(session, action, now)
        session.commit()
        raise ActionError("This action has expired.")
    if action.status not in expected:
        raise ActionError(f"This action is {action.status.replace('_', ' ')}.")
    return action


def _expire(session: Session, action: PendingAction, now: datetime) -> None:
    action.status = "expired"
    action.expires_at = None
    audit.append(session, "action.expired", "system", {"action_id": action.id, "tool": action.tool}, now=now)


def _run(session: Session, user: User, action: PendingAction, satisfied: set[str], now: datetime) -> None:
    """Try to execute; if the policy needs another step first, move the action to that step."""
    outcome = executor.execute(session, user, action, satisfied, demo_today(), now)
    if outcome.kind == "needs_otp":
        action.status = "awaiting_otp"
        action.expires_at = now + APPROVAL_WINDOW
    elif outcome.kind == "needs_cooling_off":
        action.status = "cooling_off"
        action.expires_at = now + timedelta(seconds=get_settings().cooling_off_seconds)


def confirm(session: Session, user: User, action_id: int, *, now: datetime | None = None) -> PendingAction:
    """The student confirms the exact amount, currency and payee. T2 runs; T3 asks for a code."""
    now = now or now_utc()
    with write_lock:
        action = _load(session, user, action_id, ("awaiting_confirm",), now)
        if action.plan_id is not None:
            # A plan's steps run in order: the conversion must finish before its payment.
            earlier = session.scalars(
                select(PendingAction.id).where(
                    PendingAction.plan_id == action.plan_id,
                    PendingAction.id < action.id,
                    PendingAction.status.in_(OPEN_STATUSES),
                )
            ).first()
            if earlier is not None:
                raise ActionError("Finish the earlier step of this plan first.")
        audit.append(session, "user.confirmed", "user", {"action_id": action.id, "tool": action.tool}, now=now)
        _run(session, user, action, {"confirm"}, now)
        session.commit()
        return action


def submit_otp(
    session: Session, user: User, action_id: int, code: str, *, now: datetime | None = None
) -> OtpResult:
    """Check the one-time code. Three wrong codes cancel the action. Every attempt is logged."""
    now = now or now_utc()
    with write_lock:
        action = _load(session, user, action_id, ("awaiting_otp",), now)
        if not hmac.compare_digest(code.encode("utf-8"), get_settings().demo_otp.encode("utf-8")):
            action.otp_attempts += 1
            audit.append(
                session,
                "user.otp_failed",
                "user",
                {"action_id": action.id, "attempt": action.otp_attempts, "max_attempts": MAX_OTP_ATTEMPTS},
                now=now,
            )
            if action.otp_attempts >= MAX_OTP_ATTEMPTS:
                action.status = "cancelled"
                action.expires_at = None
                audit.append(
                    session,
                    "user.cancelled",
                    "policy",
                    {"action_id": action.id, "tool": action.tool, "cause": "otp_attempts_exhausted"},
                    now=now,
                )
            session.commit()
            return OtpResult(False, MAX_OTP_ATTEMPTS - action.otp_attempts, action)

        audit.append(session, "user.otp_verified", "user", {"action_id": action.id, "tool": action.tool}, now=now)
        _run(session, user, action, {"confirm", "otp"}, now)
        session.commit()
        return OtpResult(True, MAX_OTP_ATTEMPTS - action.otp_attempts, action)


def cancel(session: Session, user: User, action_id: int, *, now: datetime | None = None) -> PendingAction:
    """Allowed until the action has executed, including during the cooling-off wait."""
    now = now or now_utc()
    with write_lock:
        action = _load(session, user, action_id, OPEN_STATUSES, now)
        action.status = "cancelled"
        action.expires_at = None
        audit.append(
            session, "user.cancelled", "user", {"action_id": action.id, "tool": action.tool, "cause": "user"}, now=now
        )
        session.commit()
        return action


def sweep(session: Session, *, now: datetime | None = None) -> None:
    """Run cooling-off actions whose wait is over, and expire approvals that were left too long."""
    now = now or now_utc()
    with write_lock:
        due = session.scalars(
            select(PendingAction)
            .where(PendingAction.status.in_(OPEN_STATUSES), PendingAction.expires_at <= now)
            .order_by(PendingAction.id)
        ).all()
        for action in due:
            if action.status == "cooling_off":
                user = session.get_one(User, action.user_id)
                executor.execute(
                    session, user, action, {"confirm", "otp", "cooling_off"}, demo_today(), now
                )
            else:
                _expire(session, action, now)
        session.commit()


def pending(session: Session, user: User) -> list[PendingAction]:
    return list(
        session.scalars(
            select(PendingAction)
            .where(PendingAction.user_id == user.id, PendingAction.status.in_(OPEN_STATUSES))
            .order_by(PendingAction.id)
        )
    )
