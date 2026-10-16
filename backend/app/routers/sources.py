"""Rule sources: list, add (live mode), check again, and review the proposed items."""

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile
from sqlalchemy import select

from app import demo_progress, sources
from app.claims.words import item_words
from app.config import effective_agent_mode
from app.models import Institution, Source, SourceItem
from app.routers.deps import SessionDep
from app.schemas import (
    Choice,
    SourceCounts,
    SourceDetailOut,
    SourceIn,
    SourceItemEdit,
    SourceItemOut,
    SourceOut,
    SourcesOut,
    VocabularyOut,
)
from app.sources import SourceError, vocabulary
from app.sources.fetch import MAX_BYTES

router = APIRouter(tags=["sources"])


def _fragment(text: str) -> str:
    return quote(text, safe="").replace("-", "%2D")


def _link(item: SourceItem) -> str | None:
    """The page with a text fragment, so the browser scrolls to and highlights the sentence."""
    url = item.source.url
    if not url:
        return None
    words = item.sentence.split()
    target = (
        _fragment(item.sentence)
        if len(words) <= 12
        else f"{_fragment(' '.join(words[:6]))},{_fragment(' '.join(words[-4:]))}"
    )
    return f"{url.split('#')[0]}#:~:text={target}"


def _item_out(item: SourceItem) -> SourceItemOut:
    return SourceItemOut(
        id=item.id,
        source_id=item.source_id,
        predicate=item.predicate,  # type: ignore[arg-type]
        label=vocabulary.LABELS[item.predicate],
        institution=item.institution,
        value=item.value,
        words=item_words(item.predicate, item.institution, item.value),
        description=item.description,
        examples=list(item.examples),
        sentence=item.sentence,
        link=_link(item),
        confidence=item.confidence,
        model=item.model,
        status=item.status,  # type: ignore[arg-type]
        edited=item.edited,
        reviewer=item.reviewer,
        reviewed_at=item.reviewed_at,
    )


def _source_out(source: Source) -> SourceOut:
    counts = SourceCounts()
    for item in source.items:
        setattr(counts, item.status, getattr(counts, item.status) + 1)
    return SourceOut(
        id=source.id,
        kind=source.kind,  # type: ignore[arg-type]
        title=source.title,
        url=source.url,
        domain=source.domain,
        fetched_at=source.fetched_at,
        dropped=source.dropped,
        counts=counts,
    )


def _detail(source: Source) -> SourceDetailOut:
    return SourceDetailOut(**_source_out(source).model_dump(), items=[_item_out(item) for item in source.items])


def _fail(error: SourceError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=str(error))


@router.get("/sources")
def list_sources(session: SessionDep) -> SourcesOut:
    demo_progress.mark("sources_viewed")
    live = effective_agent_mode() == "live"
    return SourcesOut(
        can_add=live,
        note=None if live else "Adding a source needs live mode.",
        sources=[_source_out(source) for source in session.scalars(select(Source).order_by(Source.id))],
    )


@router.get("/sources/vocabulary")
def get_vocabulary(session: SessionDep) -> VocabularyOut:
    """What an item may say: the edit form offers only these."""
    return VocabularyOut(
        predicates=[Choice(name=name, label=vocabulary.LABELS[name]) for name in vocabulary.PREDICATES],
        policies=[Choice(name=name, label=vocabulary.POLICY_LABELS[name]) for name in vocabulary.POLICIES],
        patterns=[Choice(name=name, label=vocabulary.PATTERN_LABELS[name]) for name in vocabulary.PATTERNS],
        institutions=list(session.scalars(select(Institution.name).order_by(Institution.id))),
    )


@router.get("/sources/{source_id}")
def get_source(source_id: int, session: SessionDep) -> SourceDetailOut:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="There is no such source.")
    return _detail(source)


@router.post("/sources", status_code=201)
def add_source(body: SourceIn, session: SessionDep) -> SourceDetailOut:
    """Fetch the page and let Claude propose items. Live mode only; nothing is active until approved."""
    try:
        return _detail(sources.add_url(session, body.url))
    except SourceError as error:
        raise _fail(error) from error


@router.post("/sources/upload", status_code=201)
async def upload_source(file: UploadFile, session: SessionDep) -> SourceDetailOut:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 2 MB.")
    try:
        return _detail(sources.add_upload(session, file.filename or "upload.pdf", data))
    except SourceError as error:
        raise _fail(error) from error


@router.post("/sources/{source_id}/refetch")
def refetch_source(source_id: int, session: SessionDep) -> SourceDetailOut:
    """Fetch the page again; if its text changed, its items wait for review again."""
    try:
        return _detail(sources.refetch(session, source_id))
    except SourceError as error:
        raise _fail(error) from error


@router.post("/source-items/{item_id}/approve")
def approve_item(item_id: int, session: SessionDep) -> SourceItemOut:
    try:
        return _item_out(sources.approve(session, item_id))
    except SourceError as error:
        raise _fail(error) from error


@router.post("/source-items/{item_id}/reject")
def reject_item(item_id: int, session: SessionDep) -> SourceItemOut:
    try:
        return _item_out(sources.reject(session, item_id))
    except SourceError as error:
        raise _fail(error) from error


@router.patch("/source-items/{item_id}")
def edit_item(item_id: int, body: SourceItemEdit, session: SessionDep) -> SourceItemOut:
    """Change an item within the fixed vocabulary. It then waits for approval again."""
    changes = body.model_dump(exclude_none=True)
    try:
        return _item_out(sources.edit(session, item_id, changes))
    except SourceError as error:
        raise _fail(error) from error
