"""
Tamper-evident audit log. Each entry's hash covers the previous entry's hash, so
changing any earlier entry breaks the chain from that point on.

Append-only: this module has no update or delete function, and the database
refuses UPDATE and DELETE on the table (see models.AuditLog).
"""

import copy
import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import now_utc
from app.models import AUDIT_ACTORS, AuditLog

GENESIS_PREV_HASH = "0" * 64

EVENT_TYPES = (
    "system.genesis",
    "system.reset",
    "document.uploaded",
    "document.flagged",
    "agent.proposed",
    "agent.declined",
    "policy.verdict",
    "user.confirmed",
    "user.otp_failed",
    "user.otp_verified",
    "user.cancelled",
    "action.executed",
    "action.refused",
    "action.expired",
)


class AuditError(ValueError):
    pass


@dataclass
class Record:
    """A plain copy of one audit entry, detached from the database."""

    seq: int
    created_at: datetime
    event_type: str
    actor: str
    payload: Any
    prev_hash: str
    hash: str


def canonical_json(payload: Any) -> str:
    """One fixed text form per payload: sorted keys, no spaces, real Unicode characters."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _timestamp_text(created_at: datetime) -> str:
    return created_at.astimezone(timezone.utc).isoformat(timespec="microseconds")


def compute_hash(prev_hash: str, created_at: datetime, event_type: str, actor: str, payload: Any) -> str:
    """sha256(prev_hash + created_at + event_type + actor + canonical_json(payload))."""
    text = prev_hash + _timestamp_text(created_at) + event_type + actor + canonical_json(payload)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    """Turn Decimal and date values into text so the payload is plain JSON."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot store {type(value).__name__} in the audit log.")


def append(
    session: Session, event_type: str, actor: str, payload: dict[str, Any], *, now: datetime | None = None
) -> AuditLog:
    """Add one entry to the end of the chain, inside the caller's transaction."""
    if event_type not in EVENT_TYPES:
        raise AuditError(f"Unknown audit event type: {event_type}.")
    if actor not in AUDIT_ACTORS:
        raise AuditError(f"Unknown audit actor: {actor}.")

    last = session.scalars(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)).first()
    if (last is None) != (event_type == "system.genesis"):
        raise AuditError("The genesis entry must be the first entry, and only the first.")

    prev_hash = last.hash if last else GENESIS_PREV_HASH
    created_at = now or now_utc()
    stored = json.loads(json.dumps(payload, default=_plain))  # exactly what the database returns
    entry = AuditLog(
        created_at=created_at,
        event_type=event_type,
        actor=actor,
        payload=stored,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, created_at, event_type, actor, stored),
    )
    session.add(entry)
    session.flush()
    return entry


def read_all(session: Session) -> list[Record]:
    return [
        Record(row.seq, row.created_at, row.event_type, row.actor, row.payload, row.prev_hash, row.hash)
        for row in session.scalars(select(AuditLog).order_by(AuditLog.seq))
    ]


def verify_records(records: list[Record]) -> dict[str, Any]:
    """Recompute every hash in order. Reports the first entry that does not match."""
    previous_hash = GENESIS_PREV_HASH
    for record in records:
        expected = compute_hash(
            previous_hash, record.created_at, record.event_type, record.actor, record.payload
        )
        if record.prev_hash != previous_hash or record.hash != expected:
            return {
                "ok": False,
                "broken_at": record.seq,
                "expected_hash": expected,
                "stored_hash": record.hash,
            }
        previous_hash = record.hash
    return {"ok": True, "entries": len(records)}


def verify(session: Session) -> dict[str, Any]:
    return verify_records(read_all(session))


def _amount_paths(value: Any, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Paths to every whole-number field whose name mentions an amount."""
    paths = []
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            if "amount" in key and isinstance(item, int) and not isinstance(item, bool):
                paths.append((*path, key))
            paths += _amount_paths(item, (*path, key))
    return paths


def _change_field(payload: Any) -> tuple[str, Any, Any]:
    """Change one field of a copied payload in place. Returns (field, original, tampered)."""
    amounts = _amount_paths(payload)
    if amounts:
        path = amounts[0]
        holder = payload
        for key in path[:-1]:
            holder = holder[key]
        original = holder[path[-1]]
        holder[path[-1]] = original + 100_000
        return ".".join(path), original, holder[path[-1]]
    if isinstance(payload, dict) and payload:
        key = sorted(payload)[0]
        original = payload[key]
        payload[key] = f"{original} (edited)"
        return key, original, payload[key]
    payload["edited"] = True
    return "edited", None, True


def simulate_tamper(session: Session, seq: int | None = None) -> dict[str, Any]:
    """
    Show what tampering does, on an in-memory copy. The real log is never touched.

    One field in one entry's payload is changed (by default an entry near the middle
    that contains an amount) and the copy is verified again.
    """
    records = copy.deepcopy(read_all(session))
    if not records:
        raise AuditError("The audit log is empty.")

    if seq is None:
        middle = records[len(records) // 2].seq
        with_amount = [record for record in records if _amount_paths(record.payload)]
        target = min(with_amount or records, key=lambda record: abs(record.seq - middle))
    else:
        found = [record for record in records if record.seq == seq]
        if not found:
            raise AuditError(f"There is no audit entry #{seq}.")
        target = found[0]

    field, original, tampered = _change_field(target.payload)
    return {
        "seq": target.seq,
        "event_type": target.event_type,
        "field": field,
        "original": original,
        "tampered": tampered,
        "verification": verify_records(records),
        "entries": [record for record in records if abs(record.seq - target.seq) <= 2],
    }


def export(session: Session, format: str) -> str:
    """The whole log as JSON or CSV text, oldest first."""
    rows = [
        {**asdict(record), "created_at": _timestamp_text(record.created_at)}
        for record in read_all(session)
    ]
    if format == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2)
    if format == "csv":
        buffer = io.StringIO()
        columns = ["seq", "created_at", "event_type", "actor", "payload", "prev_hash", "hash"]
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "payload": canonical_json(row["payload"])})
        return buffer.getvalue()
    raise AuditError(f"Unknown export format: {format}.")
