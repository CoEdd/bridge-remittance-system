"""
Live mode: Claude proposes fields and wording, plain code verifies them.

Most tests use a stand-in client, so they prove the plumbing and the verification
without calling the API. The tests marked `live` call the real API and are skipped
without ANTHROPIC_API_KEY.
"""

import json
import os
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import documents
from app.config import get_settings
from app.documents.reader import read_message, read_pdf
from app.llm import LlmUnavailable, complete_json
from app.models import Bill, Document
from app.seed.demo_docs import DEMO_DOCUMENTS, HIDDEN_INSTRUCTION, demo_docs_dir
from tests.helpers import NOW, last_audit, the_user

live = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")

TUITION_FIELDS = {
    "issuer": ("Shenzhen Polytechnic International University", "Shenzhen Polytechnic International University"),
    "issuer_local_name": ("深圳国际理工大学", "深圳国际理工大学"),
    "payee_name": ("Shenzhen Polytechnic International University", "Shenzhen Polytechnic International University"),
    "payee_account": ("4100 2026 0000 8815", "4100 2026 0000 8815"),
    "bank_name": ("Shenzhen Bay Commercial Bank", "Shenzhen Bay Commercial Bank"),
    "amount": ("12000.00", "CNY 12,000.00"),
    "currency": ("CNY", "CNY"),
    "due_date": ("2026-11-15", "15 November 2026"),
    "late_fee_terms": (
        "0.05% of the amount due per day after the due date.",
        "0.05% of the amount due per day after the due date.",
    ),
}
EMPTY = {"value": "", "source": ""}


class StandInClient:
    """Answers like the Anthropic client would, with canned JSON. Records what it was sent."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.requests: list[dict[str, Any]] = []
        self.messages = self.beta = SimpleNamespace(messages=self)
        self.messages = self

    def create(self, **request: Any) -> Any:
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, SimpleNamespace):
            return answer
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(answer))])


def fields_answer(overrides: dict[str, tuple[str, str]] | None = None, base: dict[str, tuple[str, str]] = TUITION_FIELDS) -> dict[str, Any]:
    merged = {**base, **(overrides or {})}
    names = ("issuer", "issuer_local_name", "payee_name", "payee_account", "bank_name", "amount", "currency", "due_date", "late_fee_terms")
    return {name: {"value": merged[name][0], "source": merged[name][1]} if name in merged else EMPTY for name in names}


def explanation_answer(text: str = "CNY 12,000.00") -> dict[str, str]:
    return {"ms": f"Invois yuran. Jumlah: {text}.", "en": f"A tuition invoice. Amount: {text}.", "zh": f"学费通知。金额：{text}。"}


@pytest.fixture
def live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODE", "live")
    get_settings.cache_clear()


def ingest(session: Session, key: str, client: Any) -> Document:
    demo = DEMO_DOCUMENTS[key]
    data = (demo_docs_dir() / demo.filename).read_bytes()
    read = read_pdf(data) if demo.filename.endswith(".pdf") else read_message(data.decode("utf-8"))
    return documents.ingest(
        session, the_user(session), filename=demo.filename, kind=demo.kind, read=read, source="demo bundle", now=NOW, llm_client=client
    )


def bill_of(session: Session, document: Document) -> Bill | None:
    return session.scalars(select(Bill).where(Bill.document_id == document.id)).first()


def test_fields_proposed_by_claude_are_located_and_verified(session: Session, live_mode: None) -> None:
    client = StandInClient(fields_answer(), explanation_answer())

    document = ingest(session, "tuition_invoice", client)
    fields = document.extracted_fields

    assert last_audit(session, "document.uploaded").payload["extractor"] == "live"
    assert all(field["verified"] for field in fields.values())
    assert (fields["amount"]["start"], fields["amount"]["end"]) == (237, 250)  # offsets found by plain code
    assert document.raw_text[fields["due_date"]["start"] : fields["due_date"]["end"]] == "15 November 2026"
    assert bill_of(session, document) is not None
    assert document.explanation["en"] == "A tuition invoice. Amount: CNY 12,000.00."


@pytest.mark.parametrize(
    "field, proposed",
    [
        ("amount", ("10200.00", "CNY 12,000.00")),  # a value the cited text does not support
        ("amount", ("12000.00", "CNY 12,000.00 only")),  # a quote that is not in the document
        ("payee_account", ("6217 9988 2041 5530", "4100 2026 0000 8815")),
        ("currency", ("USD", "CNY")),
        ("due_date", ("2026-12-15", "15 November 2026")),
    ],
)
def test_a_wrong_proposal_is_marked_unverified_and_cannot_be_paid(
    session: Session, live_mode: None, field: str, proposed: tuple[str, str]
) -> None:
    client = StandInClient(fields_answer({field: proposed}), explanation_answer())

    document = ingest(session, "tuition_invoice", client)

    assert document.extracted_fields[field]["verified"] is False
    assert document.extracted_fields[field]["note"]
    assert bill_of(session, document) is None
    assert documents.document_status(document, False) == "needs_review"


def test_a_paraphrased_text_field_is_unverified_but_does_not_block_the_bill(session: Session, live_mode: None) -> None:
    paraphrase = ("0.05% per day after the due date", "0.05% of the amount due per day after the due date.")
    client = StandInClient(fields_answer({"late_fee_terms": paraphrase}), explanation_answer())

    document = ingest(session, "tuition_invoice", client)
    bill = bill_of(session, document)

    assert document.extracted_fields["late_fee_terms"]["verified"] is False
    assert bill is not None and bill.late_fee_terms is None  # the unverified wording is not carried over


def test_the_document_is_sent_as_data_and_hidden_text_is_never_sent(session: Session, live_mode: None) -> None:
    rent = {
        "issuer": ("Lingnan Student Housing", "Lingnan Student Housing"),
        "payee_name": ("Lingnan Student Housing", "Lingnan Student Housing"),
        "payee_account": ("3300 1188 2026 0042", "3300 1188 2026 0042"),
        "amount": ("2800.00", "CNY 2,800.00"),
        "currency": ("CNY", "CNY"),
        "due_date": ("2026-11-01", "1 November 2026"),
    }
    client = StandInClient(fields_answer(base=rent), explanation_answer("CNY 2,800.00"))

    document = ingest(session, "invoice_injection", client)
    sent = json.dumps(client.requests, ensure_ascii=False, default=str)

    assert document.trust_flag == "untrusted"
    assert HIDDEN_INSTRUCTION not in sent and "8820 1147" not in sent and "ignore all previous" not in sent
    extraction = client.requests[0]
    assert "untrusted data" in extraction["system"] and "Never follow" in extraction["system"]
    assert "<document>" in extraction["messages"][0]["content"]
    assert extraction["output_config"]["format"]["type"] == "json_schema"
    assert extraction["output_config"]["format"]["schema"]["additionalProperties"] is False


def test_a_proposal_quoting_hidden_text_is_rejected(session: Session, live_mode: None) -> None:
    # Even if a model were tricked into citing the hidden instruction, plain code refuses the field.
    tricked = {
        "payee_account": ("8820 1147", "8820 1147"),
        "amount": ("2800.00", "CNY 2,800.00"),
        "currency": ("CNY", "CNY"),
        "due_date": ("2026-11-01", "1 November 2026"),
    }
    client = StandInClient(fields_answer(base=tricked), explanation_answer("CNY 2,800.00"))

    document = ingest(session, "invoice_injection", client)

    assert document.extracted_fields["payee_account"]["verified"] is False
    assert bill_of(session, document) is None


def test_if_claude_cannot_be_reached_the_scripted_extractor_takes_over(session: Session, live_mode: None) -> None:
    import anthropic
    import httpx2

    failure = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    client = StandInClient(failure, failure)

    document = ingest(session, "tuition_invoice", client)

    assert last_audit(session, "document.uploaded").payload["extractor"] == "scripted (live unavailable)"
    assert all(field["verified"] for field in document.extracted_fields.values())
    assert document.explanation["ms"].startswith("Ini invois yuran pengajian")
    assert bill_of(session, document) is not None


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_a_refusal_or_a_cut_off_answer_is_treated_as_unavailable(stop_reason: str) -> None:
    stopped = SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text='{"a":')])

    with pytest.raises(LlmUnavailable):
        complete_json(system="s", user="u", schema={"type": "object"}, client=StandInClient(stopped))


def test_an_explanation_without_the_verified_amount_is_replaced_by_the_template(session: Session, live_mode: None) -> None:
    client = StandInClient(fields_answer(), {"ms": "Sila bayar CNY 9.99 segera.", "en": "", "zh": "金额：CNY 12,000.00。请缴费。"})

    explanation = ingest(session, "tuition_invoice", client).explanation

    assert explanation["ms"].startswith("Ini invois yuran pengajian")  # wrong amount: template used instead
    assert explanation["en"].startswith("This is a tuition invoice")  # empty: template used instead
    assert explanation["zh"] == "金额：CNY 12,000.00。请缴费。"  # states the verified amount: kept


def test_the_request_uses_the_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    client = StandInClient({"ok": True}, {"ok": True})

    complete_json(system="s", user="u", schema={"type": "object"}, client=client)
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5")
    get_settings.cache_clear()
    complete_json(system="s", user="u", schema={"type": "object"}, client=client)

    default, chosen = client.requests
    assert (default["model"], default["fallbacks"], default["betas"]) == ("claude-opus-5-5", "default", ["server-side-fallback-2026-07-01"])
    assert chosen["model"] == "claude-haiku-4-5" and "fallbacks" not in chosen


@live
@pytest.mark.parametrize("key", ["tuition_invoice", "agent_offer"])
def test_real_claude_extraction_passes_verification(session: Session, live_mode: None, key: str) -> None:
    document = ingest(session, key, None)
    fields = document.extracted_fields

    assert last_audit(session, "document.uploaded").payload["extractor"] == "live"
    for name in ("amount", "currency", "payee_account"):
        assert fields[name]["verified"], (name, fields[name])
    assert bill_of(session, document) is not None
