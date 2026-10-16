"""The presenter's demo bar reads how far the demo has come from GET /demo/state."""

import threading

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import demo_progress
from app.db import get_engine
from app.models import Document
from app.seed import reset
from tests.helpers import OTP, only, say


def done(client: TestClient) -> dict[str, bool]:
    return {step["key"]: step["done"] for step in client.get("/demo/state").json()["steps"]}


def approve(client: TestClient, action_id: int) -> None:
    assert client.post(f"/actions/{action_id}/confirm").status_code == 200
    assert client.post(f"/actions/{action_id}/otp", json={"code": OTP}).json()["accepted"] is True


def test_every_step_is_read_from_the_app_and_a_reset_clears_them(client: TestClient) -> None:
    demo_progress.clear()  # the flags live in memory, shared by every test in this process
    state = client.get("/demo/state").json()
    assert [step["key"] for step in state["steps"]] == ["upload", "verify", "plan", "pay", "agent", "mule", "audit", "redteam", "sources"]
    assert not any(done(client).values())
    assert (state["invoice_document_id"], state["pending_plan_id"]) == (None, None)

    invoice = client.post("/demo/documents/tuition_invoice").json()
    assert done(client)["upload"] and not done(client)["verify"]
    client.get(f"/documents/{invoice['id']}")
    assert done(client)["verify"]
    assert client.get("/demo/state").json()["invoice_document_id"] == invoice["id"]

    plan = only(say(client, "Can I pay this fee before the deadline?"), "approval_required")[0]
    state = client.get("/demo/state").json()
    assert done(client)["plan"] and not done(client)["pay"] and state["pending_plan_id"] == plan["plan_id"]
    for action in plan["actions"]:
        approve(client, action["id"])
    assert done(client)["pay"] and client.get("/demo/state").json()["pending_plan_id"] is None

    pasted = client.post("/demo/documents/agent_offer", params={"pasted": True}).json()
    with Session(get_engine()) as session:
        stored = session.get_one(Document, pasted["id"])
        assert (stored.filename, stored.kind, stored.source) == ("Pasted message", "message", "paste")
    say(client, "Can I pay through this agent?")
    assert done(client)["agent"] and not done(client)["mule"]

    client.post("/demo/events/mule")
    say(client, "Can I forward this money as asked?")
    assert done(client)["mule"]

    client.get("/audit/verify")
    assert not done(client)["audit"]  # both halves of the proof are needed
    client.post("/audit/simulate-tamper")
    assert done(client)["audit"]

    assert "event: done" in client.post("/security/redteam/run").text  # the stream runs to the end
    assert done(client)["redteam"]
    client.get("/sources")
    assert all(done(client).values())

    assert client.post("/demo/reset").status_code == 200
    assert not any(done(client).values())


def test_only_a_message_can_be_pasted(client: TestClient) -> None:
    assert client.post("/demo/documents/tuition_invoice", params={"pasted": True}).status_code == 422
    assert client.post("/demo/documents/nope", params={"pasted": True}).status_code == 404


def test_requests_during_a_reset_wait_for_it_and_never_fail(client: TestClient) -> None:
    """The demo bar polls while the presenter resets: no request may see the tables half built."""
    resetter = threading.Thread(target=lambda: [reset() for _ in range(5)])
    resetter.start()
    codes: list[int] = []
    while resetter.is_alive() or len(codes) < 30:
        codes += [client.get(path).status_code for path in ("/demo/state", "/me", "/accounts")]
    resetter.join()
    assert set(codes) == {200}
