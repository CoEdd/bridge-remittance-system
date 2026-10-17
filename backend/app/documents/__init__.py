"""
The document pipeline, run on every upload or pasted message:

read -> detect injection -> extract fields -> verify them in plain code -> assess risk
-> create a payee and a bill if the document can be paid -> explain in three languages.

Document text is data, never instructions. Hidden or AI-addressed text is blanked out
before anything reads the document for meaning.
"""

import logging
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, sources
from app.clock import now_utc
from app.config import effective_agent_mode
from app.db import write_lock
from app.documents import explain, injection, risk
from app.documents.extract import Field, digits_of, extract_scripted
from app.documents.index import PassageIndex, index
from app.documents.languages import detect_languages
from app.documents.reader import ReadResult
from app.documents.verify import verify_fields
from app.models import Bill, Document, Institution, Payee, User
from app.money import to_minor
from app.policy.reasons import DOCUMENT_RISK_SIGNALS, reason

logger = logging.getLogger(__name__)

INJECTION_CODE = "INJECTION"
PAYMENT_FIELDS = ("amount", "currency", "payee_account")


def policy_signals(document: Document) -> list[dict[str, Any]]:
    """The risk signals the policy engine acts on."""
    return [item for item in document.risk_signals or [] if item.get("code") in DOCUMENT_RISK_SIGNALS]


def hidden_findings(document: Document) -> list[dict[str, Any]]:
    """Hidden or AI-addressed text found in the document."""
    return [item for item in document.risk_signals or [] if item.get("code") == INJECTION_CODE]


def claim_blocks(document: Document) -> list[str]:
    """The reason codes of the claim check's blocking conclusions. An extra layer beside the risk signals."""
    return list((document.claim_check or {}).get("blocks") or [])


def claim_warns(document: Document) -> list[str]:
    return list((document.claim_check or {}).get("warns") or [])


def claim_summary(document: Document) -> dict[str, Any] | None:
    """What a blocked payment shows of the claim check: the claims that count and the reasoning."""
    check = document.claim_check or {}
    blocking = [item for item in check.get("conclusions") or [] if item["severity"] == "block"]
    if not blocking:
        return None
    return {
        "origin": check.get("origin"),
        "claims": [item for item in check["claims"] if item["status"] in ("contradicted", "flagged")],
        "reasoning": [{"rule": item["rule"], "title": item["title"], "lines": item["reasoning"]} for item in blocking],
    }


def document_status(document: Document, has_bill: bool) -> str:
    if document.trust_flag == "untrusted":
        return "untrusted"
    if policy_signals(document) or claim_blocks(document):
        return "risk_found"
    return "verified" if has_bill else "needs_review"


def bill_is_flagged(bill: Bill) -> bool:
    """True when a bill comes from a document that is untrusted, carries a risk signal or fails the claim check."""
    document = bill.document
    return document is not None and (
        document.trust_flag == "untrusted" or bool(policy_signals(document)) or bool(claim_blocks(document))
    )


def _extract(
    visible: str, raw: str, kind: str, institutions: list[Institution], llm_client: Any, live: bool
) -> tuple[dict[str, Field], str]:
    names = [(item.name, item.name_local) for item in institutions]
    if live:
        from app.documents.live import extract_live
        from app.llm import LlmUnavailable

        try:
            return extract_live(visible, raw, kind, client=llm_client), "live"
        except LlmUnavailable as error:
            logger.warning("Live extraction failed (%s); using the scripted extractor.", error)
            return extract_scripted(visible, kind, names), "scripted (live unavailable)"
    return extract_scripted(visible, kind, names), "scripted"


def _account_status(fields: dict[str, Field], institutions: list[Institution], payees: list[Payee]) -> str:
    account = fields.get("payee_account")
    if not (account and account.verified):
        return "none"
    digits = digits_of(account.value)
    if any(digits == digits_of(item.official_account_ref) for item in institutions):
        return "official"
    if any(digits == digits_of(item.account_ref) and item.first_paid_at for item in payees):
        return "known"
    return "new"


def _create_bill(
    session: Session, user: User, document: Document, fields: dict[str, Field], payees: list[Payee], now: datetime
) -> Bill | None:
    """A bill for a document whose amount, currency and account are verified (and due date, for an invoice)."""
    needed = [*PAYMENT_FIELDS, "due_date"] if document.kind == "invoice" else list(PAYMENT_FIELDS)
    if not all(name in fields and fields[name].verified for name in needed):
        return None

    account = fields["payee_account"].value
    payee = next((item for item in payees if digits_of(item.account_ref) == digits_of(account)), None)
    if payee is None:
        name, bank = fields.get("payee_name"), fields.get("bank_name")
        payee = Payee(
            user_id=user.id,
            name=name.value if name and name.verified else "Unnamed payee",
            account_ref=account,
            bank_name=bank.value if bank and bank.verified else "",
            verified_source=None,  # not saved or checked by the student: it counts as a new payee
            created_at=now,
        )
        session.add(payee)
        session.flush()

    due, late_fee, number = fields.get("due_date"), fields.get("late_fee_terms"), fields.get("invoice_number")
    bill = Bill(
        user_id=user.id,
        document_id=document.id,
        payee_id=payee.id,
        amount_minor=to_minor(fields["amount"].value, fields["currency"].value),
        currency=fields["currency"].value,
        due_date=date.fromisoformat(due.value) if due and due.verified else None,
        late_fee_terms=late_fee.value if late_fee and late_fee.verified else None,
        reference=number.value if number and number.verified else None,
        status="open",
    )
    session.add(bill)
    session.flush()
    return bill


def _explain(
    document: Document,
    visible: str,
    fields: dict[str, Field],
    signals: list[dict[str, Any]],
    account_status: str,
    payable: bool,
    institutions: list[Institution],
    llm_client: Any,
    live: bool,
) -> dict[str, str]:
    untrusted = document.trust_flag == "untrusted"
    named = next((item for item in institutions if item.name in visible or item.name_local in visible), None)
    templates = explain.build(
        kind=document.kind,
        visible_text=visible,
        fields=fields,
        signals=signals,
        untrusted=untrusted,
        account_status=account_status,
        payable=payable,
        institution_names=(named.name, named.name_local) if named else None,
    )
    if not live:
        return templates

    from app.documents.live import explain_live
    from app.llm import LlmUnavailable

    warnings = [reason(signal["code"]).text["en"] for signal in signals]
    if untrusted:
        warnings.append(reason("UNTRUSTED_DOCUMENT").text["en"])
    passages = [signal["policy_clause"]["text"] for signal in signals if signal.get("policy_clause")]
    try:
        written = explain_live(
            kind=document.kind,
            verified={name: field.value for name, field in fields.items() if field.verified},
            warnings=warnings,
            passages=passages,
            client=llm_client,
        )
    except LlmUnavailable as error:
        logger.warning("Live explanation failed (%s); using the templates.", error)
        return templates
    # Plain code has the last word: Claude's text is kept only if it states the verified amount.
    amount = explain.amount_text(fields)
    return {
        language: text if text and (amount is None or amount in text) else templates[language]
        for language, text in written.items()
    }


def ingest(
    session: Session,
    user: User,
    *,
    filename: str,
    kind: str,
    read: ReadResult,
    source: str,
    now: datetime | None = None,
    llm_client: Any = None,
    passages: PassageIndex = index,
    scripted: bool = False,
    claims_live: bool | None = None,
    sender: str | None = None,
) -> Document:
    """
    Run the whole pipeline on one document and store the result. `source` says how it arrived.

    `passages` is the index the document joins: the live one unless the session belongs to
    an isolated copy of the database. `scripted` keeps Claude out of it whatever the agent mode.
    `claims_live` chooses who extracts the claims, when that should differ from the rest.
    """
    # Imported here: the claim check reads this package's word lists, so it loads after it.
    from app.claims.check import run_check

    now = now or now_utc()
    live = not scripted and effective_agent_mode() == "live"
    with write_lock:
        findings = injection.detect(read.text, read.runs)
        hidden = injection.hidden_ranges(findings)
        visible = injection.blank_out(read.text, hidden)

        institutions = list(session.scalars(select(Institution).order_by(Institution.id)))
        payees = list(session.scalars(select(Payee).where(Payee.user_id == user.id).order_by(Payee.id)))

        fields, extractor = _extract(visible, read.text, kind, institutions, llm_client, live)
        verify_fields(fields, read.text, hidden)

        document = Document(
            user_id=user.id,
            filename=filename,
            kind=kind,
            source=source,
            sender=sender,
            source_language=",".join(detect_languages(visible)),
            raw_text=read.text,
            chars_meta=read.runs,
            extracted_fields={name: asdict(field) for name, field in fields.items()},
            trust_flag="untrusted" if findings else "trusted",
            risk_signals=[],
            explanation={},
            created_at=now,
        )
        session.add(document)
        session.flush()
        passages.add_document(document.id, filename, visible)

        # Risk rules read verified fields only: an unverified value proves nothing either way.
        verified = {name: field for name, field in fields.items() if field.verified}
        patterns = sources.approved_patterns(session)  # approved in Rule sources; none in the seed
        signals = risk.assess(visible, verified, institutions, payees, passages.search, patterns)
        account_status = _account_status(fields, institutions, payees)
        bill = _create_bill(session, user, document, fields, payees, now)
        document.risk_signals = [
            *({"code": INJECTION_CODE, **asdict(finding)} for finding in findings),
            *signals,
        ]
        # The neuro-symbolic claim check: an extra layer beside the risk signals above. Its
        # facts are read before this document's own payee is counted (it was never paid).
        check = run_check(
            session,
            user,
            visible,
            verified,
            live=live if claims_live is None else claims_live,
            client=llm_client,
            hints=sources.pattern_hints(patterns),
        )
        document.claim_check = check
        explanation = _explain(
            document, visible, fields, signals, account_status, bill is not None, institutions, llm_client, live
        )
        # Something only the claim check caught must not read as "all clear".
        only_claims = [item for item in check["conclusions"] if item["severity"] == "block" and item["raises"] not in {signal["code"] for signal in signals}]
        if only_claims:
            for language, text in explain.CLAIM_CHECK_NOTE.items():
                titles = "; ".join(dict.fromkeys(item["title"][language] for item in only_claims))
                explanation[language] = f"{explanation[language]}{'' if language == 'zh' else ' '}{text.format(titles=titles)}"
        document.explanation = explanation

        audit.append(
            session,
            "document.uploaded",
            "user",
            {
                "document_id": document.id,
                "filename": filename,
                "kind": kind,
                "languages": document.source_language.split(","),
                "source": source,
                "extractor": extractor,
                "verified_fields": sorted(name for name, field in fields.items() if field.verified),
                "unverified_fields": sorted(name for name, field in fields.items() if not field.verified),
                "bill_id": bill.id if bill else None,
            },
            now=now,
        )
        audit.append(
            session,
            "claims.checked",
            "policy",
            {
                "document_id": document.id,
                "origin": check["origin"],
                "model": check["model"],
                "claims": len(check["claims"]),
                "dropped": check["dropped"],
                "conclusions": [
                    {"rule": item["rule"], "severity": item["severity"], "raises": item["raises"]}
                    for item in check["conclusions"]
                ],
            },
            now=now,
        )
        if findings or signals:
            audit.append(
                session,
                "document.flagged",
                "policy",
                {
                    "document_id": document.id,
                    "filename": filename,
                    "trust_flag": document.trust_flag,
                    "signals": [signal["code"] for signal in signals],
                    "hidden_text": [finding.text for finding in findings],
                },
                now=now,
            )
        session.commit()
        return document


def reindex(session: Session) -> None:
    """Put every stored document back into the in-memory index (after a restart)."""
    for document in session.scalars(select(Document).order_by(Document.id)):
        if not index.has_document(document.id):
            findings = [(item["start"], item["end"]) for item in hidden_findings(document) if item["kind"] != "invisible_characters"]
            index.add_document(document.id, document.filename, injection.blank_out(document.raw_text, findings))
