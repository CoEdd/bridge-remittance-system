from fastapi import APIRouter

from app.clock import demo_today
from app.schemas import ResetOut
from app.seed import reset

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset_demo() -> ResetOut:
    """Rebuild the database: same seed data every time, FX rates fetched again and frozen."""
    source = reset()
    return ResetOut(status="reset", demo_today=demo_today(), fx_source=source)
