from fastapi import APIRouter, HTTPException

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import actions, audit
from app.actions import MAX_OTP_ATTEMPTS, ActionError
from app.agent import replies
from app.models import PendingAction
from app.policy import requires_for
from app.routers.deps import SessionDep, UserDep
from app.schemas import ActionOut, OtpIn, OtpOut

router = APIRouter(prefix="/actions", tags=["actions"])


# The audit entry that closed an action, by its final status.
CLOSING_EVENTS = {
    "executed": "action.executed",
    "refused": "action.refused",
    "cancelled": "user.cancelled",
    "expired": "action.expired",
}


def action_out(session: Session, action: PendingAction) -> ActionOut:
    cooling_off = action.status == "cooling_off"
    closing = CLOSING_EVENTS.get(action.status)
    closed = audit.last_for_action(session, action.id, (closing,)) if closing else None
    return ActionOut(
        id=action.id,
        plan_id=action.plan_id,
        tool=action.tool,
        args=action.args,
        tier=action.tier,
        status=action.status,
        requires=requires_for(action.tier, [item["code"] for item in action.reasons]),
        reasons=action.reasons,
        why=replies.why(action.tier, [item["code"] for item in action.reasons]),
        cost_breakdown=action.cost_breakdown,
        otp_attempts=action.otp_attempts,
        otp_attempts_left=MAX_OTP_ATTEMPTS - action.otp_attempts,
        created_at=action.created_at,
        expires_at=None if cooling_off else action.expires_at,
        cooling_off_until=action.expires_at if cooling_off else None,
        executed_posting_id=action.executed_posting_id,
        closed_at=closed.created_at if closed else None,
        audit_seq=closed.seq if closed else None,
    )


def _http_error(error: ActionError) -> HTTPException:
    return HTTPException(status_code=404 if error.not_found else 409, detail=str(error))


@router.get("")
def list_actions(session: SessionDep, user: UserDep) -> list[ActionOut]:
    """Every action the agent proposed that needed the student or was refused, oldest first."""
    rows = session.scalars(select(PendingAction).where(PendingAction.user_id == user.id).order_by(PendingAction.id))
    return [action_out(session, action) for action in rows]


@router.get("/pending")
def list_pending(session: SessionDep, user: UserDep) -> list[ActionOut]:
    """Actions waiting for the student: to confirm, to enter a code, or cooling off."""
    return [action_out(session, action) for action in actions.pending(session, user)]


@router.post("/{action_id}/confirm")
def confirm_action(action_id: int, session: SessionDep, user: UserDep) -> ActionOut:
    try:
        return action_out(session, actions.confirm(session, user, action_id))
    except ActionError as error:
        raise _http_error(error) from error


@router.post("/{action_id}/otp")
def submit_otp(action_id: int, body: OtpIn, session: SessionDep, user: UserDep) -> OtpOut:
    try:
        result = actions.submit_otp(session, user, action_id, body.code)
    except ActionError as error:
        raise _http_error(error) from error
    return OtpOut(accepted=result.accepted, attempts_left=result.attempts_left, action=action_out(session, result.action))


@router.post("/{action_id}/cancel")
def cancel_action(action_id: int, session: SessionDep, user: UserDep) -> ActionOut:
    try:
        return action_out(session, actions.cancel(session, user, action_id))
    except ActionError as error:
        raise _http_error(error) from error
