from pathlib import PurePath

from fastapi import APIRouter, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import documents
from app.clock import demo_today
from app.documents.extract import FIELD_NAMES
from app.documents.reader import ReadResult, UnreadableDocument, read_image, read_message, read_pdf
from app.models import Bill, Document, User
from app.policy.reasons import reason
from app.routers.deps import SessionDep, UserDep
from app.schemas import (
    BillOut,
    DemoDocumentOut,
    DocumentOut,
    DocumentSummaryOut,
    FieldOut,
    HiddenTextOut,
    MessageIn,
    PolicyClauseOut,
    RiskSignalOut,
)
from app.seed.demo_docs import DEMO_DOCUMENTS, demo_docs_dir

router = APIRouter(tags=["documents"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
IMAGE_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"II*\x00", b"MM\x00*")


def bill_out(bill: Bill) -> BillOut:
    return BillOut(
        id=bill.id,
        payee_id=bill.payee_id,
        payee_name=bill.payee.name,
        amount_minor=bill.amount_minor,
        currency=bill.currency,
        due_date=bill.due_date,
        due_in_days=(bill.due_date - demo_today()).days if bill.due_date else None,
        late_fee_terms=bill.late_fee_terms,
        status=bill.status,
        document_id=bill.document_id,
        flagged=documents.bill_is_flagged(bill),
    )


def _bill_of(session: Session, document: Document) -> Bill | None:
    return session.scalars(select(Bill).where(Bill.document_id == document.id).order_by(Bill.id)).first()


def _summary(document: Document, has_bill: bool) -> dict:
    return {
        "id": document.id,
        "filename": document.filename,
        "kind": document.kind,
        "languages": document.source_language.split(","),
        "created_at": document.created_at,
        "status": documents.document_status(document, has_bill),
    }


def document_out(session: Session, document: Document) -> DocumentOut:
    bill = _bill_of(session, document)
    stored = document.extracted_fields or {}
    signals = []
    for signal in documents.policy_signals(document):
        texts = reason(signal["code"])
        clause = signal.get("policy_clause")
        signals.append(
            RiskSignalOut(
                code=signal["code"],
                title=texts.title,
                text=texts.text,
                evidence=signal.get("evidence", []),
                policy_clause=PolicyClauseOut(**clause) if clause else None,
            )
        )
    return DocumentOut(
        **_summary(document, bill is not None),
        raw_text=document.raw_text,
        trust_flag=document.trust_flag,
        fields=[FieldOut(**stored[name]) for name in FIELD_NAMES if name in stored],
        hidden_text=[HiddenTextOut(kind=item["kind"], text=item["text"]) for item in documents.hidden_findings(document)],
        risk_signals=signals,
        explanation=document.explanation or {},
        bill=bill_out(bill) if bill else None,
    )


def _read_upload(filename: str, data: bytes) -> tuple[str, ReadResult]:
    """Decide what an uploaded file is from its first bytes, then read it."""
    if data.startswith(b"%PDF"):
        return "invoice", read_pdf(data)
    if data.startswith(IMAGE_MAGIC):
        return "invoice", read_image(data)
    try:
        return "message", read_message(data.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise UnreadableDocument("Upload a PDF, an image or a plain text file.") from error


def _ingest(session: Session, user: User, filename: str, kind: str, read: ReadResult, source: str) -> DocumentOut:
    document = documents.ingest(session, user, filename=filename, kind=kind, read=read, source=source)
    return document_out(session, document)


@router.post("/documents")
async def upload_document(file: UploadFile, session: SessionDep, user: UserDep) -> DocumentOut:
    """Upload an invoice (PDF or image) or a text file, and run the pipeline on it."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 5 MB.")
    filename = PurePath(file.filename or "document").name[:120] or "document"
    try:
        kind, read = _read_upload(filename, data)
    except UnreadableDocument as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _ingest(session, user, filename, kind, read, "upload")


@router.post("/documents/message")
def paste_message(body: MessageIn, session: SessionDep, user: UserDep) -> DocumentOut:
    """Paste a payment message as plain text."""
    try:
        read = read_message(body.text)
    except UnreadableDocument as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _ingest(session, user, "Pasted message", "message", read, "paste")


@router.get("/demo/documents")
def list_demo_documents() -> list[DemoDocumentOut]:
    """The bundled demo documents, for the "Use a demo document" menu."""
    return [DemoDocumentOut(key=doc.key, filename=doc.filename, kind=doc.kind, label=doc.label) for doc in DEMO_DOCUMENTS.values()]


@router.post("/demo/documents/{key}")
def ingest_demo_document(key: str, session: SessionDep, user: UserDep) -> DocumentOut:
    """Ingest a bundled demo document exactly as if it had been uploaded or pasted."""
    demo = DEMO_DOCUMENTS.get(key)
    if demo is None:
        raise HTTPException(status_code=404, detail="There is no such demo document.")
    data = (demo_docs_dir() / demo.filename).read_bytes()
    read = read_pdf(data) if demo.filename.endswith(".pdf") else read_message(data.decode("utf-8"))
    return _ingest(session, user, demo.filename, demo.kind, read, "demo bundle")


@router.get("/documents")
def list_documents(session: SessionDep, user: UserDep) -> list[DocumentSummaryOut]:
    """Every document, newest first."""
    with_bill = set(session.scalars(select(Bill.document_id).where(Bill.document_id.is_not(None))))
    rows = session.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.id.desc()))
    return [DocumentSummaryOut(**_summary(document, document.id in with_bill)) for document in rows]


@router.get("/documents/{document_id}")
def get_document(document_id: int, session: SessionDep, user: UserDep) -> DocumentOut:
    document = session.get(Document, document_id)
    if document is None or document.user_id != user.id:
        raise HTTPException(status_code=404, detail="There is no such document.")
    return document_out(session, document)
