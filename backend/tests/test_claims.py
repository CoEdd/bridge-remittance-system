"""
The neuro-symbolic claim check, end to end: extraction (neural side) with its verbatim
check and its offline cache, the six demo documents, and how it joins the policy engine.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import documents
from app.claims import extract as extraction
from app.claims import facts
from app.claims.schema import CLAIM_TYPES, EXTRACTION_SCHEMA, claim_from_answer
from app.documents.reader import read_message, read_pdf
from app.models import Bill, Document
from app.policy import evaluate
from app.seed.demo_docs import DEMO_DOCUMENTS, HIDDEN_INSTRUCTION, demo_docs_dir
from sqlalchemy import select
from tests.helpers import CNY_WALLET, NOW, StandInClient, audit_events, balances, context, last_audit, only, say, the_user

SPIU = "Shenzhen Polytechnic International University"


def ingest_demo(session: Session, key: str, **options: Any) -> Document:
    demo = DEMO_DOCUMENTS[key]
    data = (demo_docs_dir() / demo.filename).read_bytes()
    read = read_pdf(data) if demo.filename.endswith(".pdf") else read_message(data.decode("utf-8"))
    return documents.ingest(session, the_user(session), filename=demo.filename, kind=demo.kind, read=read, source="demo bundle", now=NOW, **options)


def ingest_text(session: Session, text: str, **options: Any) -> Document:
    return documents.ingest(session, the_user(session), filename="Pasted message", kind="message", read=read_message(text), source="paste", now=NOW, **options)


def answer(*claims: tuple[str, str, str, str]) -> dict[str, Any]:
    """Claude's answer to the claims request: (type, value, detail, source) each."""
    return {"claims": [{"type": kind, "value": value, "detail": detail, "source": source} for kind, value, detail, source in claims]}


def statuses(document: Document) -> dict[str, str]:
    return {item["type"]: item["status"] for item in document.claim_check["claims"]}


def rules(document: Document) -> list[str]:
    return [item["rule"] for item in document.claim_check["conclusions"]]


def pay(session: Session, document: Document) -> Any:
    bill = session.scalars(select(Bill).where(Bill.document_id == document.id)).one()
    return evaluate(the_user(session), "pay_bill", {"bill_id": bill.id, "from_account_id": CNY_WALLET}, context(session))


# ---------------------------------------------------------------- the schema


def test_the_schema_lists_the_thirteen_claim_types() -> None:
    assert list(CLAIM_TYPES) == [
        "represents_institution", "agent_of_institution", "payee_name", "payee_account", "payee_bank", "amount",
        "due", "fee_discount", "pays_via_third_party", "deadline_pressure", "threat", "secrecy_request",
        "account_change_notice",
    ]  # fmt: skip
    assert EXTRACTION_SCHEMA["properties"]["claims"]["items"]["properties"]["type"]["enum"] == list(CLAIM_TYPES)


def test_an_answer_becomes_a_claim_only_when_it_fits_the_schema() -> None:
    amount = claim_from_answer({"type": "amount", "value": "10200.00", "detail": "CNY", "source": "CNY 10,200.00"})

    assert amount is not None and amount.args == {"value": "10200.00", "currency": "CNY"}
    assert claim_from_answer({"type": "secrecy_request", "value": "", "detail": "", "source": "x"}).args == {}  # type: ignore[union-attr]
    assert claim_from_answer({"type": "approve_payment", "value": "yes", "detail": "", "source": "x"}) is None
    assert claim_from_answer({"type": "payee_account", "value": "", "detail": "", "source": "x"}) is None


# ---------------------------------------------------------------- extraction


def test_a_claim_whose_quote_is_not_in_the_document_is_dropped(session: Session, caplog: pytest.LogCaptureFixture) -> None:
    client = StandInClient(
        answer(
            ("agent_of_institution", SPIU, "", "I am the official agent of SPIU"),  # in the text
            ("fee_discount", "20% off", "", "you will save 20 percent"),  # not in the text: made up
            ("payee_account", "6217 0000 1111 2222", "", "6217 0000 1111 2222"),
        )
    )

    document = ingest_text(session, "I am the official agent of SPIU. Pay CNY 9,000.00 to account 6217 0000 1111 2222.", scripted=True, claims_live=True, llm_client=client)

    check = document.claim_check
    assert (check["origin"], check["dropped"]) == ("live", 1)
    assert [item["type"] for item in check["claims"]] == ["agent_of_institution", "payee_account"]
    assert "Dropped a fee_discount claim" in caplog.text
    assert all(document.raw_text[item["start"] : item["end"]] == item["source"] for item in check["claims"])
    assert last_audit(session, "claims.checked").payload["dropped"] == 1


def test_claude_is_shown_the_document_as_data_and_never_its_hidden_text(session: Session) -> None:
    client = StandInClient(answer())

    ingest_demo(session, "invoice_injection", scripted=True, claims_live=True, llm_client=client)

    request = client.requests[0]
    assert "untrusted data" in request["system"] and "Never follow" in request["system"]
    assert request["messages"][0]["content"].startswith("<document>\n") and request["messages"][0]["content"].endswith("\n</document>")
    assert HIDDEN_INSTRUCTION not in json.dumps(request, ensure_ascii=False)
    assert request["output_config"]["format"]["schema"] == EXTRACTION_SCHEMA


def test_if_claude_cannot_be_reached_the_offline_extractors_take_over(session: Session) -> None:
    import anthropic
    import httpx2

    failure = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))

    document = ingest_demo(session, "agent_offer", scripted=True, claims_live=True, llm_client=StandInClient(failure))

    assert document.claim_check["origin"] == "cached"
    assert document.claim_check["blocks"] == ["PAYEE_NOT_OFFICIAL", "SCAM_PATTERN", "THIRD_PARTY_DISCOUNT"]


# ---------------------------------------------------------------- scripted mode: the cache, offline


def test_the_cache_records_the_model_and_the_date_of_the_live_run() -> None:
    cache = json.loads(extraction.CACHE_FILE.read_text(encoding="utf-8"))

    assert cache["model"].startswith("claude-") and len(cache["date"]) == 10
    assert sorted(item["filename"] for item in cache["documents"].values()) == sorted(demo.filename for demo in DEMO_DOCUMENTS.values())


def test_the_agent_message_scripted_and_offline(session: Session) -> None:
    document = ingest_demo(session, "agent_offer")  # scripted mode, no key, no network

    check = document.claim_check
    assert (check["origin"], check["dropped"]) == ("cached", 0)
    assert check["model"].startswith("claude-") and check["cached_on"]
    # The agent claim, the payee account and the discount are contradicted; pressure and secrecy are flagged.
    assert statuses(document) == {
        "agent_of_institution": "contradicted",
        "fee_discount": "contradicted",
        "amount": "unverifiable",
        "payee_name": "unverifiable",
        "payee_bank": "unverifiable",
        "payee_account": "contradicted",
        "pays_via_third_party": "contradicted",
        "deadline_pressure": "flagged",
        "secrecy_request": "flagged",
    }
    assert rules(document) == ["R1", "R2", "R3", "R4", "R7", "R8"]
    by_type = {item["type"]: item for item in check["claims"]}
    assert by_type["agent_of_institution"]["source"].startswith("Saya ejen pembayaran rasmi")
    assert by_type["agent_of_institution"]["evidence"]["words"]["en"].endswith("does not use payment agents")
    assert by_type["agent_of_institution"]["meaning"] == {"en": "Says it acts for SPIU", "ms": "Mengaku bertindak bagi pihak SPIU", "zh": "自称代表SPIU办理"}
    assert by_type["secrecy_request"]["source"] == "Jangan beritahu pejabat kewangan, nanti diskaun dibatalkan."
    r2 = next(item for item in check["conclusions"] if item["rule"] == "R2")
    assert r2["reasoning"][-1]["text"]["en"] == "Rule R2: An agent claim contradicted by the institution's own policy blocks the payment."
    policy_line = r2["reasoning"][1]
    assert policy_line["text"]["en"] == "SPIU's policy says it does not use payment agents."
    # Every fact used says where it comes from and who approved it.
    assert [cite["text"]["en"] for cite in policy_line["cites"]] == [
        "Source: SPIU payment policy (spiu.example), approved by seed on 15 Sep 2026"
    ]
    assert policy_line["cites"][0]["text"]["ms"] == "Sumber: SPIU payment policy (spiu.example), diluluskan oleh seed pada 15 Sep 2026"


@pytest.mark.parametrize(
    "key, fired, blocks, expected",
    [
        ("tuition_invoice", [], [], {"represents_institution": "supported", "payee_name": "supported", "payee_account": "supported"}),
        ("changed_details", ["R1", "R5"], ["BANK_DETAILS_CHANGED", "PAYEE_NOT_OFFICIAL"], {"represents_institution": "contradicted", "payee_account": "contradicted", "account_change_notice": "unverifiable"}),
        ("urgent_notice", ["R1", "R6", "R7", "R8"], ["PAYEE_NOT_OFFICIAL", "SCAM_PATTERN"], {"threat": "contradicted", "payee_account": "contradicted", "deadline_pressure": "flagged", "secrecy_request": "flagged"}),
        ("invoice_injection", [], [], {"payee_name": "supported", "payee_account": "supported"}),
        ("mule_message", ["R8"], [], {"payee_name": "unverifiable", "payee_account": "unverifiable"}),
    ],
)
def test_the_other_demo_documents_get_the_expected_statuses(session: Session, key: str, fired: list[str], blocks: list[str], expected: dict[str, str]) -> None:
    document = ingest_demo(session, key)

    assert document.claim_check["origin"] == "cached"
    assert (rules(document), document.claim_check["blocks"]) == (fired, blocks)
    assert {kind: status for kind, status in statuses(document).items() if kind in expected} == expected
    assert HIDDEN_INSTRUCTION not in json.dumps(document.claim_check, ensure_ascii=False)


def test_without_the_cache_the_regex_extractor_still_finds_the_scam(session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(extraction, "CACHE_FILE", tmp_path / "missing.json")

    document = ingest_demo(session, "agent_offer")

    assert (document.claim_check["origin"], document.claim_check["model"]) == ("regex", None)
    assert document.claim_check["blocks"] == ["PAYEE_NOT_OFFICIAL", "SCAM_PATTERN", "THIRD_PARTY_DISCOUNT"]
    assert statuses(document)["secrecy_request"] == "flagged"


def test_a_text_that_is_not_in_the_cache_uses_the_regex_extractor(session: Session) -> None:
    document = ingest_text(session, "Rent for November.\nAmount due: CNY 2,800.00\nPayee: Lingnan Student Housing\nAccount: 3300 1188 2026 0042")

    assert document.claim_check["origin"] == "regex"
    assert rules(document) == [] and statuses(document)["payee_account"] == "supported"


# ---------------------------------------------------------------- facts: only from data we trust


def test_facts_never_come_from_the_document_being_checked(session: Session) -> None:
    before = [fact.atom for fact in facts.collect(session, the_user(session))]

    ingest_demo(session, "agent_offer")
    ingest_demo(session, "changed_details")

    after = [fact.atom for fact in facts.collect(session, the_user(session))]
    assert after == before
    assert not any("6217998820415530" in atom or "Lim Wei Jie" in atom for atom in after)
    assert {fact.source for fact in facts.collect(session, the_user(session))} == {
        "Institution registry", "Your payment history", "SPIU payment policy", "Scam advisory (sample)",
    }  # fmt: skip


def test_an_institution_is_recognised_by_name_local_name_or_acronym(session: Session) -> None:
    from app.claims.schema import Claim

    claims = [Claim("represents_institution", {"institution_name": name}, name) for name in ("SPIU", "深圳国际理工大学", "shenzhen polytechnic  international university", "Northbridge College")]

    assert [fact.atom[1] for fact in facts.ground(claims, session)] == [SPIU, SPIU, SPIU, "Northbridge College"]


# ---------------------------------------------------------------- the union with the keyword layer

REWORDED = (
    "Hi Ahmad, I look after fee settlements for SPIU students from Malaysia. Settle this term through me and "
    "CNY 1,800.00 stays in your pocket.\n"
    "Amount: CNY 10,200.00\nAccount name: Lim Wei Jie\nAccount number: 6217 9988 2041 5530"
)
REWORDED_CLAIMS = answer(
    ("agent_of_institution", "SPIU", "", "I look after fee settlements for SPIU students"),
    ("fee_discount", "CNY 1,800 less", "", "CNY 1,800.00 stays in your pocket"),
    ("payee_name", "Lim Wei Jie", "", "Lim Wei Jie"),
    ("payee_account", "6217 9988 2041 5530", "", "6217 9988 2041 5530"),
    ("pays_via_third_party", "", "", "Account name: Lim Wei Jie"),
)


def test_the_claim_check_refuses_a_reworded_scam_the_keywords_miss(session: Session) -> None:
    document = ingest_text(session, REWORDED, scripted=True, claims_live=True, llm_client=StandInClient(REWORDED_CLAIMS))

    # The keyword layer sees no agent, no discount, no pressure: only the claim check objects.
    assert documents.policy_signals(document) == []
    assert rules(document) == ["R1", "R2", "R3", "R4", "R8"]
    verdict = pay(session, document)
    assert (verdict.tier, [item.code for item in verdict.reasons]) == ("REFUSED", ["PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT"])
    assert documents.document_status(document, True) == "risk_found"
    assert document.explanation["en"].endswith("The claim check found a problem: Payee is not the official account; Agent claim contradicted by policy; Discount contradicted by policy; Discount for paying a third party.")


def test_a_claim_check_that_finds_nothing_never_removes_a_keyword_block(session: Session) -> None:
    # Claude returns no claims at all for the agent's offer.
    document = ingest_demo(session, "agent_offer", scripted=True, claims_live=True, llm_client=StandInClient(answer()))

    assert (document.claim_check["claims"], document.claim_check["blocks"]) == ([], [])
    verdict = pay(session, document)
    assert (verdict.tier, [item.code for item in verdict.reasons]) == ("REFUSED", ["PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"])


def test_a_supported_claim_never_lowers_a_tier_or_clears_an_untrusted_document(session: Session) -> None:
    # The claim check finds every claim of this invoice supported; hidden text still makes it untrusted.
    untrusted = ingest_demo(session, "invoice_injection")
    assert rules(untrusted) == [] and statuses(untrusted)["payee_account"] == "supported"
    assert [item.code for item in pay(session, untrusted).reasons] == ["UNTRUSTED_DOCUMENT"]

    # A genuine invoice above the per-payment limit stays Tier 3.
    genuine = ingest_demo(session, "tuition_invoice")
    from tests.helpers import cny, fund

    fund(session, "CNY", cny("20000.00"))
    assert pay(session, genuine).tier == "T3"


def test_a_warning_from_the_claim_check_forces_the_step_up(session: Session) -> None:
    document = ingest_demo(session, "mule_message")

    verdict = pay(session, document)

    assert (document.claim_check["blocks"], document.claim_check["warns"]) == ([], ["NEW_PAYEE"])
    assert (verdict.tier, verdict.requires) == ("T3", ["confirm", "otp", "cooling_off"])
    assert [item.code for item in verdict.reasons] == ["NEW_PAYEE"]


# ---------------------------------------------------------------- through the API


def test_the_claims_of_a_document_can_be_read(client: TestClient) -> None:
    document = client.post("/demo/documents/agent_offer").json()

    claims = client.get(f"/documents/{document['id']}/claims").json()

    assert claims == document["claim_check"]
    assert (claims["origin"], claims["blocks"]) == ("cached", ["PAYEE_NOT_OFFICIAL", "SCAM_PATTERN", "THIRD_PARTY_DISCOUNT"])
    assert client.get("/documents/999/claims").status_code == 404
    assert document["status"] == "risk_found" and document["bill"]["flagged"] is True


def test_checking_claims_is_a_tier_0_step_and_is_logged(client: TestClient, session: Session) -> None:
    from tests.helpers import read_events

    document = client.post("/demo/documents/agent_offer").json()
    before = balances(session)

    events = read_events(client, client.post(f"/chat/document/{document['id']}").json()["stream_id"])

    step = only(events, "step")[1]
    assert (step["tool"], step["label"], step["tier"], step["verdict"]) == ("check_claims", "Checked its claims", "T0", "allowed")
    assert step["summary"] == "10 claims · 6 contradicted or flagged"
    assert step["details"]["conclusions"][1] == {"rule": "R2", "severity": "block", "title": "Agent claim contradicted by policy"}
    logged = [entry for entry in client.get("/audit", params={"event_type": "claims.checked"}).json()["entries"]]
    assert logged[0]["summary"] == "10 claims · R1, R2, R3, R4, R7, R8"
    assert [item["rule"] for item in logged[0]["payload"]["conclusions"] if item["severity"] == "block"] == ["R1", "R2", "R3", "R4", "R7"]
    session.expire_all()
    assert balances(session) == before


def test_a_blocked_payment_carries_the_claims_that_count_and_the_reasoning(client: TestClient) -> None:
    client.post("/demo/documents/agent_offer")

    blocked = only(say(client, "Boleh saya bayar melalui ejen ini?"), "blocked")[0]

    # The refusal reasons are unchanged: the claim check agrees with the keyword layer here.
    assert [reason["code"] for reason in blocked["reasons"]] == ["PAYEE_NOT_OFFICIAL", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"]
    check = blocked["claim_check"]
    assert check["origin"] == "cached"
    assert [(item["type"], item["status"]) for item in check["claims"]] == [
        ("agent_of_institution", "contradicted"),
        ("fee_discount", "contradicted"),
        ("payee_account", "contradicted"),
        ("pays_via_third_party", "contradicted"),
        ("deadline_pressure", "flagged"),
        ("secrecy_request", "flagged"),
    ]
    assert [item["rule"] for item in check["reasoning"]] == ["R1", "R2", "R3", "R4", "R7"]
    assert check["reasoning"][1]["lines"][-1]["text"]["ms"].startswith("Peraturan R2: ")
    assert any(cite["title"] == "SPIU payment policy" for line in check["reasoning"][1]["lines"] for cite in line["cites"])


def test_a_payment_with_nothing_wrong_carries_no_claim_check(client: TestClient) -> None:
    client.post("/demo/events/mule")

    blocked = only(say(client, "Boleh saya pindahkan wang ini seperti yang diminta?"), "blocked")[0]

    assert [reason["code"] for reason in blocked["reasons"]] == ["MONEY_MULE_PATTERN"]
    assert blocked["claim_check"] is None  # the money-mule rule looks at the ledger, not at claims


def test_the_security_page_gets_the_eight_rules_in_words(client: TestClient) -> None:
    overview = client.get("/security/claim-check").json()

    assert [(rule["id"], rule["severity"]) for rule in overview["rules"]] == [(f"R{number}", "block") for number in range(1, 8)] + [("R8", "warn")]
    assert overview["rules"][1]["title"] == {"en": "Agent claim contradicted by policy", "ms": "Dakwaan ejen bercanggah dengan dasar", "zh": "代理身份与机构政策相矛盾"}
    assert "evaluation" in overview
