from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, select

from app import audit, demo_progress
from app.audit import EVENT_TYPES, AuditError, Record
from app.audit.describe import event_label, summarise
from app.clock import now_utc
from app.models import AuditLog
from app.routers.deps import SessionDep
from app.schemas import AuditEntryOut, AuditPageOut, AuditVerifyOut, EventTypeOut, TamperIn, TamperOut

router = APIRouter(prefix="/audit", tags=["audit"])

EXPORT_TYPES = {"json": "application/json", "csv": "text/csv; charset=utf-8"}


def entry_out(entry: AuditLog | Record) -> AuditEntryOut:
    return AuditEntryOut(
        seq=entry.seq,
        created_at=entry.created_at,
        event_type=entry.event_type,
        label=event_label(entry.event_type),
        actor=entry.actor,
        summary=summarise(entry.event_type, entry.payload),
        payload=entry.payload,
        prev_hash=entry.prev_hash,
        hash=entry.hash,
    )


@router.get("")
def list_entries(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    event_type: str | None = None,
    seq: Annotated[int | None, Query(ge=1)] = None,
) -> AuditPageOut:
    """Audit entries, newest first. `seq` asks for one entry by its number."""
    if event_type is not None and event_type not in EVENT_TYPES:
        raise HTTPException(status_code=422, detail="Unknown event type.")
    query = select(AuditLog)
    if event_type:
        query = query.where(AuditLog.event_type == event_type)
    if seq is not None:
        query = query.where(AuditLog.seq == seq)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    entries = session.scalars(
        query.order_by(AuditLog.seq.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return AuditPageOut(
        total=total,
        page=page,
        page_size=page_size,
        event_types=[EventTypeOut(code=code, label=event_label(code)) for code in EVENT_TYPES],
        entries=[entry_out(entry) for entry in entries],
    )


@router.get("/verify")
def verify_chain(session: SessionDep) -> AuditVerifyOut:
    """Recompute the whole hash chain."""
    demo_progress.mark("chain_verified")
    return AuditVerifyOut(**audit.verify(session))


@router.post("/simulate-tamper")
def simulate_tamper(session: SessionDep, body: TamperIn | None = None) -> TamperOut:
    """Change one field on an in-memory copy and show where the chain breaks. The real log is not changed."""
    try:
        result = audit.simulate_tamper(session, body.seq if body else None)
    except AuditError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    demo_progress.mark("tamper_simulated")
    return TamperOut(
        seq=result["seq"],
        event_type=result["event_type"],
        field=result["field"],
        original=result["original"],
        tampered=result["tampered"],
        verification=AuditVerifyOut(**result["verification"]),
        entries=[entry_out(record) for record in reversed(result["entries"])],
    )


@router.get("/export")
def export_log(session: SessionDep, format: Literal["json", "csv"] = "json") -> Response:
    """Download the whole log, oldest first."""
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    return Response(
        content=audit.export(session, format),
        media_type=EXPORT_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="bridge-audit-{stamp}.{format}"'},
    )
