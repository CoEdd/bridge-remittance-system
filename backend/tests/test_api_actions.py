"""The action and audit endpoints, and the real background task."""

import csv
import io
import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import actions
from app.config import get_settings
from app.db import get_engine
from tests.helpers import OTP, PHONE_BILL, UNIVERSITY, cny, fund, new_bill, pay_args, the_user


def propose(tool: str, args: dict[str, Any]) -> int:
    """Propose as the agent will in step 6. Returns the pending action's id."""
    with Session(get_engine()) as session:
        proposal = actions.propose(session, the_user(session), tool, args)
        assert proposal.action is not None
        return proposal.action.id


def propose_tuition() -> int:
    with Session(get_engine()) as session:
        fund(session, "CNY", cny("20000.00"))
        bill_id = new_bill(session, UNIVERSITY, "12000.00").id
    return propose("pay_bill", pay_args(bill_id))


# ---------------------------------------------------------------- actions


def test_pending_actions_are_listed_with_what_they_need(client: TestClient) -> None:
    assert client.get("/actions/pending").json() == []
    action_id = propose_tuition()

    pending = client.get("/actions/pending").json()

    assert len(pending) == 1
    action = pending[0]
    assert (action["id"], action["tool"], action["tier"], action["status"]) == (action_id, "pay_bill", "T3", "awaiting_confirm")
    assert action["requires"] == ["confirm", "otp"]
    assert action["reasons"][0]["code"] == "OVER_TXN_LIMIT"
    assert set(action["reasons"][0]["text"]) == {"en", "ms", "zh"}
    assert action["cost_breakdown"]["amount_minor"] == cny("12000.00")
    assert action["otp_attempts_left"] == 3
    assert action["expires_at"] is not None and action["cooling_off_until"] is None


def test_confirm_then_code_executes_a_tier_3_payment(client: TestClient) -> None:
    action_id = propose_tuition()

    confirmed = client.post(f"/actions/{action_id}/confirm").json()
    wrong = client.post(f"/actions/{action_id}/otp", json={"code": "000000"}).json()
    right = client.post(f"/actions/{action_id}/otp", json={"code": OTP}).json()

    assert confirmed["status"] == "awaiting_otp"
    assert (wrong["accepted"], wrong["attempts_left"], wrong["action"]["status"]) == (False, 2, "awaiting_otp")
    assert (right["accepted"], right["action"]["status"]) == (True, "executed")
    assert right["action"]["executed_posting_id"] is not None
    assert client.get("/actions/pending").json() == []
    cny_wallet = client.get("/accounts").json()["accounts"][1]
    assert cny_wallet["balance_minor"] == cny("3420.00") + cny("20000.00") - cny("12000.00")
    newest = client.get("/transactions", params={"limit": 1}).json()[0]
    assert (newest["kind"], newest["amounts"]) == ("payment", [{"currency": "CNY", "amount_minor": -cny("12000.00")}])


def test_confirm_executes_a_tier_2_payment_and_cancel_stops_one(client: TestClient) -> None:
    paid = client.post(f"/actions/{propose('pay_bill', pay_args(PHONE_BILL))}/confirm").json()
    assert paid["status"] == "executed"

    with Session(get_engine()) as session:
        bill_id = new_bill(session, UNIVERSITY, "50.00").id
    cancelled = client.post(f"/actions/{propose('pay_bill', pay_args(bill_id))}/cancel").json()

    assert cancelled["status"] == "cancelled"
    assert [bill["status"] for bill in client.get("/bills").json() if bill["id"] in (PHONE_BILL, bill_id)] == ["paid", "open"]


def test_action_endpoints_answer_404_and_409(client: TestClient) -> None:
    action_id = propose("pay_bill", pay_args(PHONE_BILL))

    assert client.post("/actions/9999/confirm").status_code == 404
    assert client.post("/actions/9999/cancel").status_code == 404
    assert client.post(f"/actions/{action_id}/otp", json={"code": OTP}).status_code == 409  # not confirmed yet
    assert client.post(f"/actions/{action_id}/confirm").status_code == 200
    assert client.post(f"/actions/{action_id}/confirm").status_code == 409  # already executed
    assert client.post(f"/actions/{action_id}/cancel").status_code == 409
    assert client.post(f"/actions/{action_id}/otp", json={}).status_code == 422


def test_the_background_task_runs_a_cooling_off_action_by_itself(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COOLING_OFF_SECONDS", "1")
    get_settings.cache_clear()
    details = {"name": "Chen Li", "account_ref": "6222 0000 1111 2222", "bank_name": "Example Bank"}
    action_id = propose("add_payee", details)

    client.post(f"/actions/{action_id}/confirm")
    waiting = client.post(f"/actions/{action_id}/otp", json={"code": OTP}).json()["action"]
    assert waiting["status"] == "cooling_off"
    assert waiting["cooling_off_until"] is not None and waiting["expires_at"] is None
    assert len(client.get("/payees").json()) == 3

    deadline = time.monotonic() + 10
    while len(client.get("/payees").json()) == 3 and time.monotonic() < deadline:
        time.sleep(0.2)

    payees = client.get("/payees").json()
    assert [payee["name"] for payee in payees][-1] == "Chen Li"
    assert client.get("/actions/pending").json() == []
    events = [entry["event_type"] for entry in client.get("/audit").json()["entries"]]
    assert events[0] == "action.executed"


# ---------------------------------------------------------------- audit


def test_a_fresh_audit_log_shows_genesis_and_reset_newest_first(client: TestClient) -> None:
    page = client.get("/audit").json()

    assert (page["total"], page["page"], page["page_size"]) == (2, 1, 50)
    assert len(page["event_types"]) == 15
    assert page["event_types"][0] == {"code": "system.genesis", "label": "Log started"}
    newest, oldest = page["entries"]
    assert (newest["seq"], newest["event_type"], newest["label"], newest["actor"]) == (2, "system.reset", "Demo reset", "system")
    assert newest["summary"] == "Demo date 2026-10-15 · FX offline_snapshot"
    assert (oldest["seq"], oldest["event_type"], oldest["summary"]) == (1, "system.genesis", "Start of the chain")
    assert oldest["prev_hash"] == "0" * 64
    assert newest["prev_hash"] == oldest["hash"]
    assert newest["created_at"].endswith("Z")


def test_audit_pages_and_filters(client: TestClient) -> None:
    client.post(f"/actions/{propose('pay_bill', pay_args(PHONE_BILL))}/confirm")

    everything = client.get("/audit").json()
    first_page = client.get("/audit", params={"page_size": 3}).json()
    second_page = client.get("/audit", params={"page_size": 3, "page": 2}).json()
    verdicts = client.get("/audit", params={"event_type": "policy.verdict"}).json()

    assert everything["total"] == 7  # genesis, reset, proposed, verdict, confirmed, verdict, executed
    assert [entry["seq"] for entry in first_page["entries"]] == [7, 6, 5]
    assert [entry["seq"] for entry in second_page["entries"]] == [4, 3, 2]
    assert (verdicts["total"], {entry["event_type"] for entry in verdicts["entries"]}) == (2, {"policy.verdict"})
    assert everything["entries"][0]["summary"] == "Action #1 · Pay bill · CNY 98.00"
    assert verdicts["entries"][1]["summary"] == "Action #1 · Pay bill · CNY 98.00 · Tier 2"
    assert client.get("/audit", params={"event_type": "nonsense"}).status_code == 422
    assert client.get("/audit", params={"page": 0}).status_code == 422


def test_verify_endpoint(client: TestClient) -> None:
    assert client.get("/audit/verify").json() == {
        "ok": True,
        "entries": 2,
        "broken_at": None,
        "expected_hash": None,
        "stored_hash": None,
    }


def test_simulate_tamper_endpoint_never_changes_the_real_log(client: TestClient) -> None:
    client.post(f"/actions/{propose('pay_bill', pay_args(PHONE_BILL))}/confirm")
    before = client.get("/audit/export", params={"format": "json"}).text

    result = client.post("/audit/simulate-tamper").json()
    chosen = client.post("/audit/simulate-tamper", json={"seq": 2}).json()

    assert result["verification"]["ok"] is False
    assert result["verification"]["broken_at"] == result["seq"] == 4
    assert result["field"] == "cost_breakdown.amount_minor"
    assert (result["original"], result["tampered"]) == (cny("98.00"), cny("98.00") + 100_000)
    assert [entry["seq"] for entry in result["entries"]] == [6, 5, 4, 3, 2]
    assert (chosen["seq"], chosen["verification"]["broken_at"]) == (2, 2)
    assert client.post("/audit/simulate-tamper", json={"seq": 999}).status_code == 404
    assert client.get("/audit/export", params={"format": "json"}).text == before
    assert client.get("/audit/verify").json()["ok"] is True
    assert client.get("/audit").json()["total"] == 7


def test_export_endpoint_downloads_json_and_csv(client: TestClient) -> None:
    as_json = client.get("/audit/export", params={"format": "json"})
    as_csv = client.get("/audit/export", params={"format": "csv"})

    assert as_json.headers["content-type"].startswith("application/json")
    assert as_json.headers["content-disposition"].startswith('attachment; filename="bridge-audit-')
    assert as_json.headers["content-disposition"].endswith('.json"')
    assert [row["event_type"] for row in json.loads(as_json.text)] == ["system.genesis", "system.reset"]
    assert as_csv.headers["content-type"].startswith("text/csv")
    assert as_csv.headers["content-disposition"].endswith('.csv"')
    assert [row["seq"] for row in csv.DictReader(io.StringIO(as_csv.text))] == ["1", "2"]
    assert client.get("/audit/export", params={"format": "xml"}).status_code == 422
    assert client.get("/audit/export").headers["content-type"].startswith("application/json")


def test_reset_starts_a_new_chain(client: TestClient) -> None:
    client.post(f"/actions/{propose('pay_bill', pay_args(PHONE_BILL))}/confirm")
    old_genesis = client.get("/audit", params={"event_type": "system.genesis"}).json()["entries"][0]["hash"]

    client.post("/demo/reset")

    page = client.get("/audit").json()
    assert page["total"] == 2
    assert page["entries"][1]["hash"] != old_genesis  # a new chain, with its own time
    assert client.get("/actions/pending").json() == []
    assert client.get("/audit/verify").json()["ok"] is True
