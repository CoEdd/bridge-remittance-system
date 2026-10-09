"""The two clocks: a fixed demo date for business logic, real UTC for audit timestamps."""

from datetime import date, datetime, timezone

from app.config import get_settings


def demo_today() -> date:
    """Business date for due dates, the planner and transaction history (DEMO_TODAY)."""
    return get_settings().demo_today


def now_utc() -> datetime:
    """Real wall-clock time in UTC, for audit-log timestamps."""
    return datetime.now(timezone.utc)
