"""The document endpoints. They need the embedding model, so they run in the backend image."""

from fastapi.testclient import TestClient

from app.seed.demo_docs import AGENT_OFFER_MS, DEMO_DOCUMENTS, HIDDEN_INSTRUCTION, demo_docs_dir
from tests.helpers import cny


def test_the_demo_menu_lists_the_six_bundled_documents(client: TestClient) -> None:
    menu = client.get("/demo/documents").json()

    assert [item["key"] for item in menu] == list(DEMO_DOCUMENTS)
    assert menu[0] == {"key": "tuition_invoice", "filename": "tuition_invoice.pdf", "kind": "invoice", "label": "Tuition invoice"}
    assert {item["kind"] for item in menu} == {"invoice", "message"}
    assert all((demo_docs_dir() / item["filename"]).is_file() for item in menu)


def test_loading_the_genuine_invoice_returns_everything_the_page_needs(client: TestClient) -> None:
    document = client.post("/demo/documents/tuition_invoice").json()
    by_name = {field["name"]: field for field in document["fields"]}

    assert (document["filename"], document["kind"], document["languages"]) == ("tuition_invoice.pdf", "invoice", ["en", "zh"])
    assert (document["status"], document["trust_flag"]) == ("verified", "trusted")
    assert document["raw_text"].startswith("Shenzhen Polytechnic International University · Finance Office\n深圳国际理工大学 财务处")
    assert [field["name"] for field in document["fields"]] == [
        "issuer", "issuer_local_name", "payee_name", "payee_account", "bank_name", "amount", "currency", "due_date", "late_fee_terms",
    ]  # fmt: skip
    assert all(field["verified"] and field["note"] is None for field in document["fields"])
    # Every field's offsets point at its source text, which is what the page highlights.
    assert all(document["raw_text"][field["start"] : field["end"]] == field["source"] for field in document["fields"])
    assert (by_name["amount"]["value"], by_name["amount"]["source"]) == ("12000.00", "CNY 12,000.00")
    assert (document["hidden_text"], document["risk_signals"]) == ([], [])
    assert document["explanation"]["ms"].startswith("Ini invois yuran pengajian daripada Shenzhen Polytechnic International University.")
    assert set(document["explanation"]) == {"ms", "en", "zh"}
    bill = document["bill"]
    assert (bill["amount_minor"], bill["currency"], bill["due_date"], bill["due_in_days"]) == (cny("12000.00"), "CNY", "2026-11-15", 31)
    assert (bill["payee_name"], bill["flagged"], bill["document_id"]) == ("Shenzhen Polytechnic International University", False, document["id"])


def test_the_agent_message_shows_three_signals_with_the_policy_clause(client: TestClient) -> None:
    document = client.post("/demo/documents/agent_offer").json()
    signals = {signal["code"]: signal for signal in document["risk_signals"]}

    assert (document["kind"], document["languages"], document["status"]) == ("message", ["ms"], "risk_found")
    assert list(signals) == ["PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"]
    for signal in signals.values():
        assert set(signal["title"]) == set(signal["text"]) == {"en", "ms", "zh"}
        assert signal["evidence"]
    clause = signals["THIRD_PARTY_DISCOUNT"]["policy_clause"]
    assert clause["file"] in ("spiu_payment_policy_en.md", "spiu_payment_policy_zh.md")
    assert clause["language"] in ("en", "zh")
    assert clause["title"] and clause["text"]
    assert clause["institution"] == "Shenzhen Polytechnic International University"
    assert set(clause["versions"]) == {"en", "zh"}
    assert signals["PAYEE_NOT_OFFICIAL"]["policy_clause"] is None
    assert signals["SCAM_PATTERN"]["title"]["ms"] == "Sepadan dengan corak penipuan"
    assert (document["bill"]["due_date"], document["bill"]["due_in_days"], document["bill"]["flagged"]) == (None, None, True)


def test_the_rent_invoice_reports_the_hidden_text(client: TestClient) -> None:
    document = client.post("/demo/documents/invoice_injection").json()

    assert (document["status"], document["trust_flag"]) == ("untrusted", "untrusted")
    assert document["hidden_text"] == [{"kind": "hidden_text", "text": HIDDEN_INSTRUCTION}]
    assert document["risk_signals"] == []
    assert "hidden text" in document["explanation"]["en"]
    # The hidden instruction named another account; the extracted one is the visible landlord account.
    assert {field["name"]: field["value"] for field in document["fields"]}["payee_account"] == "3300 1188 2026 0042"


def test_pasting_a_message_runs_the_same_pipeline(client: TestClient) -> None:
    pasted = client.post("/documents/message", json={"text": AGENT_OFFER_MS}).json()
    demo = client.post("/demo/documents/agent_offer").json()

    assert (pasted["filename"], pasted["kind"]) == ("Pasted message", "message")
    assert [signal["code"] for signal in pasted["risk_signals"]] == [signal["code"] for signal in demo["risk_signals"]]
    assert pasted["fields"] == demo["fields"]
    assert client.post("/documents/message", json={"text": ""}).status_code == 422
    assert client.post("/documents/message", json={"text": " \n "}).status_code == 422


def test_uploading_files(client: TestClient) -> None:
    pdf = (demo_docs_dir() / "tuition_invoice.pdf").read_bytes()
    text = (demo_docs_dir() / "mule_message_en.txt").read_bytes()

    uploaded_pdf = client.post("/documents", files={"file": ("../../my invoice.pdf", pdf, "application/pdf")})
    uploaded_text = client.post("/documents", files={"file": ("note.txt", text, "text/plain")})

    assert uploaded_pdf.status_code == 200
    assert uploaded_pdf.json()["filename"] == "my invoice.pdf"  # only the file name is kept, never a path
    assert (uploaded_pdf.json()["kind"], uploaded_pdf.json()["status"]) == ("invoice", "verified")
    assert uploaded_pdf.json()["fields"] == client.post("/demo/documents/tuition_invoice").json()["fields"]
    assert (uploaded_text.json()["kind"], uploaded_text.json()["bill"]["amount_minor"]) == ("message", cny("2900.00"))


def test_bad_uploads_are_refused(client: TestClient) -> None:
    too_big = client.post("/documents", files={"file": ("big.pdf", b"%PDF" + b"0" * (5 * 1024 * 1024 + 1), "application/pdf")})
    broken_pdf = client.post("/documents", files={"file": ("broken.pdf", b"%PDF-1.7 nothing here", "application/pdf")})
    binary = client.post("/documents", files={"file": ("data.bin", bytes(range(256)), "application/octet-stream")})

    assert too_big.status_code == 413
    assert (broken_pdf.status_code, broken_pdf.json()["detail"]) == (422, "This PDF could not be read.")
    assert binary.status_code == 422
    assert client.post("/documents").status_code == 422
    assert client.get("/documents").json() == []  # nothing was stored


def test_documents_are_listed_newest_first_with_a_status(client: TestClient) -> None:
    assert client.get("/documents").json() == []
    for key in DEMO_DOCUMENTS:
        client.post(f"/demo/documents/{key}")

    listed = client.get("/documents").json()

    assert [(item["filename"], item["kind"], item["status"]) for item in listed] == [
        ("mule_message_en.txt", "message", "verified"),
        ("invoice_injection_en.pdf", "invoice", "untrusted"),
        ("urgent_notice_message_zh.txt", "message", "risk_found"),
        ("changed_details_invoice.pdf", "invoice", "risk_found"),
        ("agent_offer_message_ms.txt", "message", "risk_found"),
        ("tuition_invoice.pdf", "invoice", "verified"),
    ]
    assert listed[0]["languages"] == ["en"] and listed[-1]["languages"] == ["en", "zh"]
    assert client.get(f"/documents/{listed[-1]['id']}").json()["filename"] == "tuition_invoice.pdf"


def test_unknown_documents_are_not_found(client: TestClient) -> None:
    assert client.get("/documents/999").status_code == 404
    assert client.post("/demo/documents/secret_plans").status_code == 404


def test_bills_from_risky_documents_are_marked_and_do_not_count_in_the_forecast(client: TestClient) -> None:
    forecast_before = client.get("/insights/spending").json()["forecast"]
    for key in DEMO_DOCUMENTS:
        client.post(f"/demo/documents/{key}")

    bills = client.get("/bills").json()
    safe = [(bill["payee_name"], bill["amount_minor"], bill["due_date"]) for bill in bills if not bill["flagged"] and bill["due_date"]]

    assert len(bills) == 8  # two seeded bills and one per document
    assert safe == [
        ("PearlTel Mobile", cny("98.00"), "2026-10-28"),
        ("Lingnan Student Housing", cny("2800.00"), "2026-11-01"),
        ("Shenzhen Polytechnic International University", cny("12000.00"), "2026-11-15"),
    ]
    assert sum(1 for bill in bills if bill["flagged"]) == 4
    assert [bill["due_date"] for bill in bills][-3:] == [None, None, None]  # undated requests come last
    # The untrusted rent invoice is due before month end elsewhere; none of the risky bills move the forecast.
    assert client.get("/insights/spending").json()["forecast"] == forecast_before


def test_ingestion_shows_up_in_the_audit_log(client: TestClient) -> None:
    client.post("/demo/documents/invoice_injection")

    entries = client.get("/audit").json()["entries"]

    assert [(entry["event_type"], entry["label"]) for entry in entries[:3]] == [
        ("document.flagged", "Document flagged"),
        ("claims.checked", "Claims checked"),
        ("document.uploaded", "Document uploaded"),
    ]
    assert entries[0]["summary"] == "invoice_injection_en.pdf · untrusted"
    assert entries[1]["summary"] == "6 claims · no rule fired"
    assert entries[2]["summary"] == "invoice_injection_en.pdf · demo bundle"
    assert entries[2]["payload"]["source"] == "demo bundle"
    assert client.get("/audit/verify").json()["ok"] is True


def test_reset_removes_documents(client: TestClient) -> None:
    client.post("/demo/documents/tuition_invoice")

    client.post("/demo/reset")

    assert client.get("/documents").json() == []
    assert len(client.get("/bills").json()) == 2
    assert len(client.get("/payees").json()) == 3
