"""
The receipt of an executed sandbox payment, read from the ledger, the bill, the verified
payee and the audit log. Nothing here writes; it only describes what already happened.
"""

import io
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app import audit
from app.models import Account, Bill, PendingAction, Posting, User

SAMPLE_FOOTER = "Sample document · fictional institution · created for a sandbox demo"
VERIFIED_SOURCES = {"institution_registry": "University registry", "past_payment": "Paid before", "manual": "Saved by you"}
FONT_FILE = Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")


class NoReceipt(ValueError):
    """The action is not an executed payment."""


@dataclass(frozen=True)
class Receipt:
    receipt_number: str
    business_date: date  # the demo date the payment was booked on
    executed_at: datetime  # real time, UTC
    from_account: str
    payee_name: str
    payee_account: str
    payee_verified: str | None
    amount_minor: int
    currency: str
    reference: str | None
    status: str
    audit_seq: int
    audit_hash: str  # the first 12 characters of that entry's hash

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def build(session: Session, action: PendingAction) -> Receipt:
    if action.tool != "pay_bill" or action.status != "executed" or action.executed_posting_id is None:
        raise NoReceipt("There is a receipt only for an executed payment.")
    posting = session.get_one(Posting, action.executed_posting_id)
    bill = session.get_one(Bill, int(action.args["bill_id"]))
    wallet = session.get_one(Account, int(action.args["from_account_id"]))
    user = session.get_one(User, action.user_id)
    entry = audit.last_for_action(session, action.id, ("action.executed",))
    if entry is None:
        raise NoReceipt("The payment has no audit entry.")
    return Receipt(
        receipt_number=f"BRG-{posting.business_date:%Y%m%d}-{posting.id:05d}",
        business_date=posting.business_date,
        executed_at=posting.created_at,
        from_account=f"{user.name} · {wallet.currency} wallet",
        payee_name=bill.payee.name,
        payee_account=bill.payee.account_ref,
        payee_verified=VERIFIED_SOURCES.get(bill.payee.verified_source or ""),
        amount_minor=bill.amount_minor,
        currency=bill.currency,
        reference=bill.reference,
        status="Completed (sandbox)",
        audit_seq=entry.seq,
        audit_hash=entry.hash[:12],
    )


def to_pdf(receipt: Receipt) -> bytes:
    """The receipt as a one-page A4 PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    from app.money import format_amount

    font = "Helvetica"
    if FONT_FILE.exists():
        if "WenQuanYiZenHei" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("WenQuanYiZenHei", str(FONT_FILE), subfontIndex=0))
        font = "WenQuanYiZenHei"
    ink, grey, rule, teal = (15 / 255, 30 / 255, 46 / 255), (74 / 255, 85 / 255, 104 / 255), (0.80, 0.82, 0.85), (18 / 255, 128 / 255, 111 / 255)
    left, right = 60, A4[0] - 60

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4, invariant=1)
    page.setTitle(f"Payment receipt {receipt.receipt_number}")
    page.setAuthor("Bridge sandbox")
    y = A4[1] - 70
    page.setFillColorRGB(*ink)
    page.setFont(font, 20)
    page.drawString(left, y, "Payment receipt")
    page.setFont(font, 10)
    page.setFillColorRGB(*grey)
    page.drawRightString(right, y + 4, "Bridge")
    page.drawRightString(right, y - 10, receipt.receipt_number)
    y -= 26
    page.setStrokeColorRGB(*ink)
    page.setLineWidth(1.6)
    page.line(left, y, right, y)

    y -= 46
    page.setFillColorRGB(*grey)
    page.setFont(font, 10)
    page.drawString(left, y + 22, "Amount paid")
    page.setFillColorRGB(*ink)
    page.setFont(font, 26)
    page.drawString(left, y - 6, format_amount(receipt.amount_minor, receipt.currency))
    page.setFillColorRGB(0.89, 0.95, 0.94)
    page.setStrokeColorRGB(*teal)
    page.setLineWidth(0.8)
    page.roundRect(right - 150, y - 8, 150, 26, 6, stroke=1, fill=1)
    page.setFillColorRGB(*ink)
    page.setFont(font, 10.5)
    page.drawCentredString(right - 75, y + 1, receipt.status)

    rows = [
        ("Date", f"{receipt.business_date.day} {receipt.business_date:%b %Y}"),
        ("Time", f"{receipt.executed_at:%H:%M:%S} UTC"),
        ("From", receipt.from_account),
        ("Payee", receipt.payee_name),
        ("Payee account", receipt.payee_account + (f"  ·  Verified: {receipt.payee_verified}" if receipt.payee_verified else "")),
        ("Reference", receipt.reference or "None"),
        ("Audit entry", f"#{receipt.audit_seq}  ·  hash {receipt.audit_hash}"),
    ]
    y -= 44
    page.setLineWidth(0.6)
    for label, value in rows:
        page.setStrokeColorRGB(*rule)
        page.line(left, y - 9, right, y - 9)
        page.setFillColorRGB(*grey)
        page.setFont(font, 10)
        page.drawString(left, y, label)
        page.setFillColorRGB(*ink)
        page.setFont(font, 10.5)
        page.drawString(left + 130, y, value)
        y -= 28

    page.setFillColorRGB(*grey)
    page.setFont(font, 9)
    page.drawString(left, y - 6, "No real money moved: this payment ran in the Bridge sandbox ledger.")
    page.setFont(font, 7)
    page.drawString(left, 46, SAMPLE_FOOTER)
    page.showPage()
    page.save()
    return buffer.getvalue()
