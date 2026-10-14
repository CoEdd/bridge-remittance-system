"""
Rule sources: the published pages and files that institution facts and scam patterns come from.

Who sets the rules: the eight core rules are written by people and tested. The facts they
work on come from here. Claude proposes items from a source (live mode only), plain code
checks each against the fixed vocabulary and the source text, and a person approves or
rejects it. Only approved items reach the claim check and the keyword layer.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.clock import now_utc
from app.config import effective_agent_mode
from app.db import write_lock
from app.llm import LlmUnavailable
from app.models import Institution, Source, SourceItem
from app.sources import vocabulary
from app.sources.extract import propose
from app.sources.fetch import FetchError, Page, domain_of, fetch, read_pdf_text, text_hash
from app.sources.vocabulary import Candidate, Citation, Invalid

logger = logging.getLogger(__name__)

# The demo has no login, so approvals are recorded under this name. A real deployment
# records the signed-in reviewer.
REVIEWER = "Demo reviewer"
WAITING = ("proposed", "needs_review")


class SourceError(ValueError):
    """A request the sources cannot carry out. The message is shown on the page."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ApprovedPattern:
    """An approved scam pattern with example phrases: what the keyword layer and Claude's prompt get."""

    name: str
    description: str
    examples: tuple[str, ...]
    title: str  # of its source


def citation(item: SourceItem) -> Citation:
    source = item.source
    return Citation(source.title, source.domain, source.url, item.reviewer, item.reviewed_at)


def approved_items(session: Session) -> list[SourceItem]:
    return list(session.scalars(select(SourceItem).where(SourceItem.status == "approved").order_by(SourceItem.id)))


def approved_patterns(session: Session) -> list[ApprovedPattern]:
    return [
        ApprovedPattern(item.value, item.description, tuple(item.examples), item.source.title)
        for item in approved_items(session)
        if item.predicate == "known_scam_pattern" and item.examples
    ]


def pattern_hints(patterns: list[ApprovedPattern]) -> str:
    """The approved scam patterns as a short block for Claude's claims prompt ("" when none)."""
    if not patterns:
        return ""
    lines = [
        f"- {pattern.name}: {pattern.description} Examples: " + "; ".join(f'"{example}"' for example in pattern.examples)
        for pattern in patterns
    ]
    return (
        "Scam patterns a person approved from published warnings. Use them only to recognise the claim "
        "types above; they add no new types:\n" + "\n".join(lines)
    )


def store(
    session: Session,
    source: Source,
    candidates: list[Candidate] | tuple[Candidate, ...],
    *,
    text: str,
    model: str | None,
    now: datetime,
    approve_as: str | None = None,
) -> tuple[list[SourceItem], list[str]]:
    """
    Check each candidate and keep the ones that pass, as items waiting for review (or, for
    the seed, approved by `approve_as`). Returns the items and the reasons for every drop.
    """
    institutions = list(session.scalars(select(Institution).order_by(Institution.id)))
    items: list[SourceItem] = []
    dropped: list[str] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        try:
            checked = vocabulary.check(
                candidate, institutions, text=text, source_domain=source.domain, fetched=source.kind == "url"
            )
        except Invalid as error:
            logger.warning("Dropped a proposed %s item from source %s: %s", candidate.predicate, source.title, error)
            dropped.append(str(error))
            continue
        atom = vocabulary.atom_of(checked.predicate, checked.institution, checked.value)
        if atom in seen:
            continue
        seen.add(atom)
        item = SourceItem(
            source=source,
            predicate=checked.predicate,
            institution=checked.institution,
            value=checked.value,
            description=checked.description,
            examples=list(checked.examples),
            sentence=checked.sentence,
            confidence=checked.confidence,
            model=model,
            status="approved" if approve_as else "proposed",
            reviewer=approve_as,
            reviewed_at=now if approve_as else None,
            created_at=now,
        )
        session.add(item)
        items.append(item)
    source.dropped = (source.dropped or 0) + len(dropped)
    session.flush()
    if approve_as is None:
        for item in items:
            audit.append(session, "fact.proposed", "agent", _describe(item) | {"confidence": item.confidence, "model": model}, now=now)
    return items, dropped


def _describe(item: SourceItem) -> dict[str, Any]:
    return {
        "item_id": item.id,
        "source_id": item.source_id,
        "predicate": item.predicate,
        "institution": item.institution,
        "value": item.value,
        "sentence": item.sentence,
    }


def _require_live() -> None:
    if effective_agent_mode() != "live":
        raise SourceError("Adding a source needs live mode.", 409)


def _propose(title: str, text: str, llm: Any) -> tuple[list[Candidate], str]:
    try:
        return propose(title, text, llm)
    except LlmUnavailable as error:
        raise SourceError("Claude could not read this source. Nothing was added; try again.", 502) from error


def _add(
    session: Session, *, kind: str, title: str, url: str | None, text: str, llm: Any, now: datetime | None
) -> Source:
    candidates, model = _propose(title, text, llm)  # outside the lock: it takes a while
    now = now or now_utc()
    with write_lock:
        source = Source(
            kind=kind,
            title=title,
            url=url,
            domain=domain_of(url) if url else None,
            fetched_at=now,
            content_hash=text_hash(text),
            created_at=now,
        )
        session.add(source)
        session.flush()
        audit.append(
            session,
            "source.added",
            "user",
            {"source_id": source.id, "kind": kind, "title": title, "url": url, "domain": source.domain},
            now=now,
        )
        audit.append(
            session,
            "source.fetched",
            "system",
            {"source_id": source.id, "content_hash": source.content_hash, "changed": False, "marked_for_review": 0},
            now=now,
        )
        store(session, source, candidates, text=text, model=model, now=now)
        session.commit()
    return source


def add_url(session: Session, url: str, *, http: Any = None, llm: Any = None, now: datetime | None = None) -> Source:
    """Fetch one page, let Claude propose items, keep the ones that pass the checks."""
    _require_live()
    try:
        page: Page = fetch(url.strip(), http)
    except FetchError as error:
        raise SourceError(str(error)) from error
    if session.scalar(select(Source.id).where(Source.url == page.url)) is not None:
        raise SourceError("This page is already a source.", 409)
    return _add(session, kind="url", title=page.title, url=page.url, text=page.text, llm=llm, now=now)


def add_upload(session: Session, filename: str, data: bytes, *, llm: Any = None, now: datetime | None = None) -> Source:
    """A PDF someone uploaded, read the same way as a fetched one."""
    _require_live()
    if not data.startswith(b"%PDF"):
        raise SourceError("Only PDF files can be uploaded.")
    try:
        title, text = read_pdf_text(data)
    except FetchError as error:
        raise SourceError(str(error)) from error
    if not text:
        raise SourceError("The PDF has no readable text.")
    return _add(session, kind="upload", title=title or filename, url=None, text=text, llm=llm, now=now)


def refetch(session: Session, source_id: int, *, http: Any = None, now: datetime | None = None) -> Source:
    """Fetch a page again. If its text changed, its items wait for a person again."""
    source = _source(session, source_id)
    if source.kind != "url" or not source.url:
        raise SourceError("Only a web page can be checked again.", 409)
    try:
        page = fetch(source.url, http)
    except FetchError as error:
        raise SourceError(str(error)) from error
    now = now or now_utc()
    with write_lock:
        changed = page.content_hash != source.content_hash
        marked = [item for item in source.items if changed and item.status in ("approved", "proposed")]
        was_active = any(item.status == "approved" for item in marked)
        for item in marked:
            item.status = "needs_review"
        source.fetched_at = now
        source.content_hash = page.content_hash
        audit.append(
            session,
            "source.fetched",
            "system",
            {"source_id": source.id, "content_hash": page.content_hash, "changed": changed, "marked_for_review": len(marked)},
            now=now,
        )
        if was_active:
            _rejudge(session, now)
        session.commit()
    return source


def approve(session: Session, item_id: int, *, reviewer: str = REVIEWER, now: datetime | None = None) -> SourceItem:
    now = now or now_utc()
    with write_lock:
        item = _item(session, item_id)
        if item.status not in WAITING:
            raise SourceError("Only an item waiting for review can be approved.", 409)
        item.status, item.reviewer, item.reviewed_at = "approved", reviewer, now
        audit.append(session, "fact.approved", "user", _describe(item) | {"reviewer": reviewer}, now=now)
        _rejudge(session, now)
        session.commit()
    return item


def reject(session: Session, item_id: int, *, reviewer: str = REVIEWER, now: datetime | None = None) -> SourceItem:
    now = now or now_utc()
    with write_lock:
        item = _item(session, item_id)
        if item.status == "rejected":
            raise SourceError("This item is already rejected.", 409)
        was_active = item.status == "approved"
        item.status, item.reviewer, item.reviewed_at = "rejected", reviewer, now
        audit.append(session, "fact.rejected", "user", _describe(item) | {"reviewer": reviewer}, now=now)
        if was_active:
            _rejudge(session, now)
        session.commit()
    return item


def edit(session: Session, item_id: int, changes: dict[str, Any], *, now: datetime | None = None) -> SourceItem:
    """Change an item within the vocabulary. An edited item waits for approval again."""
    now = now or now_utc()
    with write_lock:
        item = _item(session, item_id)
        institutions = list(session.scalars(select(Institution).order_by(Institution.id)))
        candidate = Candidate(
            predicate=item.predicate,
            institution=str(changes.get("institution", item.institution)),
            value=str(changes.get("value", item.value)),
            sentence=item.sentence,
            description=str(changes.get("description", item.description)),
            examples=tuple(changes.get("examples", item.examples)),
            confidence=item.confidence,
        )
        try:
            checked = vocabulary.check(
                candidate, institutions, text=None, source_domain=item.source.domain, fetched=item.source.kind == "url"
            )
        except Invalid as error:
            raise SourceError(str(error)) from error
        before = _describe(item) | {"description": item.description, "examples": list(item.examples)}
        was_active = item.status == "approved"
        item.institution, item.value = checked.institution, checked.value
        item.description, item.examples = checked.description, list(checked.examples)
        item.edited = True
        item.status, item.reviewer, item.reviewed_at = "proposed", None, None
        after = _describe(item) | {"description": item.description, "examples": list(item.examples)}
        audit.append(session, "fact.edited", "user", {"item_id": item.id, "before": before, "after": after}, now=now)
        if was_active:
            _rejudge(session, now)
        session.commit()
    return item


def _rejudge(session: Session, now: datetime) -> None:
    from app.claims.check import rejudge  # the claim check reads the approved items

    rejudge(session, now)


def _source(session: Session, source_id: int) -> Source:
    source = session.get(Source, source_id)
    if source is None:
        raise SourceError("There is no such source.", 404)
    return source


def _item(session: Session, item_id: int) -> SourceItem:
    item = session.get(SourceItem, item_id)
    if item is None:
        raise SourceError("There is no such item.", 404)
    return item
