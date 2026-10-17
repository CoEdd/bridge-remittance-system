"""The receipt of an executed payment, and the sender shown on a message card."""

from fastapi.testclient import TestClient

from tests.helpers import OTP, only, say

INVOICE_NUMBER = "SPIU-FIN-2026-104417"


def pay_the_tuition(client: TestClient) -> tuple[dict, dict]:
    client.post("/demo/documents/tuition_invoice")
    convert, pay = only(say(client, "Can I pay this fee before the deadline?"), "approval_required")[0]["actions"]
    for action in (convert, pay):
        assert client.post(f"/actions/{action['id']}/confirm").status_code == 200
        assert client.post(f"/actions/{action['id']}/otp", json={"code": OTP}).json()["accepted"] is True
    return convert, pay


def test_an_executed_payment_has_a_receipt_with_its_reference_and_audit_entry(client: TestClient) -> None:
    convert, pay = pay_the_tuition(client)

    receipt = client.get(f"/actions/{pay['id']}/receipt").json()
    action = next(item for item in client.get("/actions").json() if item["id"] == pay["id"])

    assert (receipt["amount_minor"], receipt["currency"], receipt["reference"]) == (1_200_000, "CNY", INVOICE_NUMBER)
    assert (receipt["payee_name"], receipt["payee_account"]) == ("Shenzhen Polytechnic International University", "4100 2026 0000 8815")
    assert (receipt["payee_verified"], receipt["status"]) == ("University registry", "Completed (sandbox)")
    assert receipt["from_account"] == "Ahmad Faris · CNY wallet"
    assert receipt["business_date"] == "2026-10-15"
    assert receipt["receipt_number"] == f"BRG-20261015-{action['executed_posting_id']:05d}"
    entry = client.get("/audit", params={"seq": receipt["audit_seq"]}).json()["entries"][0]
    assert entry["event_type"] == "action.executed" and entry["hash"].startswith(receipt["audit_hash"]) and len(receipt["audit_hash"]) == 12


def test_the_receipt_downloads_as_a_pdf(client: TestClient) -> None:
    _, pay = pay_the_tuition(client)

    response = client.get(f"/actions/{pay['id']}/receipt.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith('attachment; filename="BRG-20261015-')
    assert response.content.startswith(b"%PDF")


def test_only_an_executed_payment_has_a_receipt(client: TestClient) -> None:
    client.post("/demo/documents/tuition_invoice")
    convert, pay = only(say(client, "Can I pay this fee before the deadline?"), "approval_required")[0]["actions"]

    assert client.get(f"/actions/{pay['id']}/receipt").status_code == 409  # still waiting
    assert client.get(f"/actions/{convert['id']}/receipt").status_code == 409  # a conversion, not a payment
    assert client.get("/actions/999/receipt").status_code == 404


def test_a_pasted_message_keeps_its_sender(client: TestClient) -> None:
    named = client.post("/documents/message", json={"text": "Please pay CNY 100.00 to account 6217 9988 2041 5530.", "sender": "  Lim Wei Jie "}).json()
    unnamed = client.post("/documents/message", json={"text": "Please pay CNY 100.00 to account 6217 9988 2041 5530."}).json()

    assert (named["sender"], unnamed["sender"]) == ("Lim Wei Jie", None)
    assert client.get(f"/documents/{named['id']}").json()["sender"] == "Lim Wei Jie"


def test_the_demo_messages_carry_their_senders(client: TestClient) -> None:
    offer = client.post("/demo/documents/agent_offer", params={"pasted": True}).json()
    event = client.post("/demo/events/mule").json()

    assert offer["sender"] == "Lim Wei Jie"
    assert (event["sender"], event["document"]["sender"]) == ("Zhou Wei", "Zhou Wei")
    newest = client.get("/transactions", params={"limit": 1}).json()[0]
    assert (newest["counterparty"], newest["category_label"]) == ("Zhou Wei", "Money received")
    assert [(amount["currency"], amount["amount_minor"]) for amount in newest["amounts"]] == [("CNY", 300_000)]
