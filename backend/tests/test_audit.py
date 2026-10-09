import copy
import csv
import hashlib
import io
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from app import audit
from app.audit import GENESIS_PREV_HASH, AuditError, canonical_json, compute_hash
from app.models import AuditLog
from tests.helpers import NOW, audit_count


def add_sample_entries(session: Session) -> None:
    """A few entries like the ones a payment produces, with amounts in the middle."""
    audit.append(session, "agent.proposed", "agent", {"tool": "pay_bill", "args": {"bill_id": 2}}, now=NOW)
    audit.append(
        session,
        "policy.verdict",
        "policy",
        {"action_id": 1, "tool": "pay_bill", "tier": "T2", "cost_breakdown": {"amount_minor": 9800, "currency": "CNY"}},
        now=NOW,
    )
    audit.append(session, "user.confirmed", "user", {"action_id": 1, "note": "已确认 / disahkan"}, now=NOW)
    audit.append(
        session,
        "action.executed",
        "system",
        {"action_id": 1, "posting_id": 83, "receipt": {"amount_minor": 9800, "currency": "CNY"}},
        now=NOW,
    )
    session.commit()


def rows(session: Session) -> list[tuple]:
    return [
        (row.seq, row.created_at, row.event_type, row.actor, row.payload, row.prev_hash, row.hash)
        for row in session.query(AuditLog).order_by(AuditLog.seq)
    ]


def test_reset_starts_the_chain_with_genesis_and_reset(session: Session) -> None:
    genesis, reset_entry = audit.read_all(session)

    assert (genesis.seq, genesis.event_type, genesis.actor) == (1, "system.genesis", "system")
    assert genesis.prev_hash == "0" * 64 == GENESIS_PREV_HASH
    assert (reset_entry.seq, reset_entry.event_type) == (2, "system.reset")
    assert reset_entry.payload == {"demo_today": "2026-10-15", "fx_source": "offline_snapshot"}
    assert reset_entry.prev_hash == genesis.hash


def test_hash_is_sha256_of_the_documented_concatenation(session: Session) -> None:
    add_sample_entries(session)

    for record in audit.read_all(session):
        text_form = (
            record.prev_hash
            + record.created_at.isoformat(timespec="microseconds")
            + record.event_type
            + record.actor
            + json.dumps(record.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )
        assert record.hash == hashlib.sha256(text_form.encode("utf-8")).hexdigest()
        assert len(record.hash) == 64


def test_canonical_json_is_sorted_compact_and_keeps_unicode() -> None:
    assert canonical_json({"b": 1, "a": {"z": [1, 2], "y": "深圳"}}) == '{"a":{"y":"深圳","z":[1,2]},"b":1}'
    assert canonical_json({"x": 1, "y": 2}) == canonical_json({"y": 2, "x": 1})


def test_each_entry_links_to_the_one_before(session: Session) -> None:
    add_sample_entries(session)
    records = audit.read_all(session)

    assert [record.seq for record in records] == [1, 2, 3, 4, 5, 6]
    for previous, current in zip(records, records[1:]):
        assert current.prev_hash == previous.hash


def test_append_refuses_unknown_event_types_and_actors(session: Session) -> None:
    with pytest.raises(AuditError):
        audit.append(session, "user.did_something", "user", {})
    with pytest.raises(AuditError):
        audit.append(session, "user.confirmed", "hacker", {})
    with pytest.raises(AuditError):
        audit.append(session, "system.genesis", "system", {})  # only the first entry may be the genesis


def test_all_fourteen_event_types_are_accepted(session: Session) -> None:
    assert len(audit.EVENT_TYPES) == 14
    for event_type in audit.EVENT_TYPES[1:]:
        audit.append(session, event_type, "system", {"event": event_type}, now=NOW)
    session.commit()

    assert audit.verify(session) == {"ok": True, "entries": 15}


def test_verify_reports_an_intact_chain(session: Session) -> None:
    add_sample_entries(session)

    assert audit.verify(session) == {"ok": True, "entries": 6}


@pytest.mark.parametrize("field", ["payload", "event_type", "actor", "created_at", "hash", "prev_hash"])
def test_verify_finds_a_change_to_any_field(session: Session, field: str) -> None:
    add_sample_entries(session)
    records = copy.deepcopy(audit.read_all(session))
    target = records[3]
    changes = {
        "payload": {**target.payload, "tier": "T0"},
        "event_type": "user.cancelled",
        "actor": "user",
        "created_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "hash": "f" * 64,
        "prev_hash": "e" * 64,
    }
    setattr(target, field, changes[field])

    result = audit.verify_records(records)

    assert result["ok"] is False
    assert result["broken_at"] == target.seq
    assert result["stored_hash"] == target.hash
    assert result["expected_hash"] != "" and len(result["expected_hash"]) == 64


def test_verify_finds_a_removed_entry_and_a_swapped_pair(session: Session) -> None:
    add_sample_entries(session)
    records = audit.read_all(session)

    without_fourth = records[:3] + records[4:]
    swapped = records[:2] + [records[3], records[2]] + records[4:]

    assert audit.verify_records(without_fourth)["broken_at"] == 5
    assert audit.verify_records(swapped)["broken_at"] == 4


def test_the_database_refuses_to_change_or_delete_audit_entries(session: Session) -> None:
    add_sample_entries(session)

    with pytest.raises(DatabaseError, match="append-only"):
        session.execute(text("UPDATE audit_log SET payload = '{}' WHERE seq = 4"))
    session.rollback()
    with pytest.raises(DatabaseError, match="append-only"):
        session.execute(text("DELETE FROM audit_log WHERE seq = 4"))
    session.rollback()

    assert audit.verify(session) == {"ok": True, "entries": 6}


def test_verify_detects_tampering_done_directly_in_the_database(session: Session) -> None:
    # An attacker with database access removes the protection and edits an amount.
    add_sample_entries(session)
    session.execute(text("DROP TRIGGER audit_log_no_update"))
    session.execute(
        text("UPDATE audit_log SET payload = json_set(payload, '$.receipt.amount_minor', 1) WHERE seq = 6")
    )
    session.commit()

    result = audit.verify(session)

    assert result["ok"] is False
    assert result["broken_at"] == 6
    assert result["expected_hash"] != result["stored_hash"]


def test_the_audit_module_has_no_way_to_edit_or_remove_entries() -> None:
    public = [name for name in dir(audit) if not name.startswith("_")]

    assert not [name for name in public if any(word in name.lower() for word in ("update", "delete", "remove", "edit"))]


def test_simulate_tamper_breaks_a_copy_and_leaves_the_real_log_intact(session: Session) -> None:
    add_sample_entries(session)
    before = rows(session)

    result = audit.simulate_tamper(session)

    assert result["seq"] == 4  # the entry nearest the middle that contains an amount
    assert result["field"] == "cost_breakdown.amount_minor"
    assert (result["original"], result["tampered"]) == (9800, 109800)
    assert result["verification"]["ok"] is False
    assert result["verification"]["broken_at"] == 4
    assert [record.seq for record in result["entries"]] == [2, 3, 4, 5, 6]
    assert next(record for record in result["entries"] if record.seq == 4).payload["cost_breakdown"]["amount_minor"] == 109800
    # The real log: same rows, still verifies.
    assert rows(session) == before
    assert audit.verify(session) == {"ok": True, "entries": 6}


def test_simulate_tamper_on_a_chosen_entry(session: Session) -> None:
    add_sample_entries(session)

    result = audit.simulate_tamper(session, seq=5)

    assert (result["seq"], result["event_type"]) == (5, "user.confirmed")
    assert result["verification"]["broken_at"] == 5
    assert audit.verify(session)["ok"] is True


def test_simulate_tamper_works_on_a_fresh_log(session: Session) -> None:
    result = audit.simulate_tamper(session)

    assert result["seq"] == 2
    assert result["field"] == "demo_today"
    assert result["verification"] == {
        "ok": False,
        "broken_at": 2,
        "expected_hash": result["verification"]["expected_hash"],
        "stored_hash": audit.read_all(session)[1].hash,
    }
    assert audit.verify(session) == {"ok": True, "entries": 2}


def test_simulate_tamper_refuses_an_unknown_entry(session: Session) -> None:
    with pytest.raises(AuditError):
        audit.simulate_tamper(session, seq=999)


def test_export_json_and_csv_contain_the_whole_log(session: Session) -> None:
    add_sample_entries(session)

    as_json = json.loads(audit.export(session, "json"))
    as_csv = list(csv.DictReader(io.StringIO(audit.export(session, "csv"))))

    assert [row["seq"] for row in as_json] == [1, 2, 3, 4, 5, 6]
    assert set(as_json[0]) == {"seq", "created_at", "event_type", "actor", "payload", "prev_hash", "hash"}
    assert as_json[4]["payload"]["note"] == "已确认 / disahkan"
    assert [row["event_type"] for row in as_csv] == [row["event_type"] for row in as_json]
    assert json.loads(as_csv[3]["payload"]) == as_json[3]["payload"]
    # An exported log can be verified again from the file alone.
    previous = GENESIS_PREV_HASH
    for row in as_json:
        created_at = datetime.fromisoformat(row["created_at"])
        assert row["hash"] == compute_hash(previous, created_at, row["event_type"], row["actor"], row["payload"])
        previous = row["hash"]
    with pytest.raises(AuditError):
        audit.export(session, "xml")


def test_export_does_not_change_the_log(session: Session) -> None:
    add_sample_entries(session)
    count = audit_count(session)

    audit.export(session, "json")
    audit.export(session, "csv")

    assert audit_count(session) == count


def test_every_event_type_and_tool_has_a_readable_label() -> None:
    from app.audit.describe import EVENT_LABELS, TOOL_LABELS
    from app.policy import BASE_TIERS

    assert set(EVENT_LABELS) == set(audit.EVENT_TYPES)
    assert set(TOOL_LABELS) == set(BASE_TIERS)
