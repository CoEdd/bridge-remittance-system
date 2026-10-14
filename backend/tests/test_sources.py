"""
Rule sources with human approval: fetching, the fixed vocabulary, the word-for-word
citation check, review, re-review after a change, and provenance in the claim check.
No network: pages are served by httpx.MockTransport and Claude by a stand-in client.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import sources
from app.claims import facts
from app.claims.check import judge
from app.claims.schema import Claim
from app.models import Institution, Source, SourceItem
from app.sources import SourceError, vocabulary
from app.sources.fetch import MAX_BYTES, FetchError, fetch
from app.sources.vocabulary import Candidate, Invalid
from tests.helpers import NOW, StandInClient, audit_events, only, say, the_user
from tests.test_claims import ingest_demo, ingest_text

SPIU = "Shenzhen Polytechnic International University"
PAGE_URL = "https://www.example.edu/fees/warning"
SCAM_SENTENCE = (
    "Scammers, claiming to be agents of the University, are offering to pay tuition fees on behalf of the "
    "student at a discounted rate."
)
OTHER_SENTENCE = "Victims lose the money they paid and still owe the full fee."
PAGE = f"""<html><head><title>Fee payment scams</title><script>var x = 1;</script></head>
<body><nav>Home | Fees</nav><main><h1>Warning</h1>
<p>{SCAM_SENTENCE} {OTHER_SENTENCE}</p><p>Pay only through the <a href="/pay">student portal</a>.</p></main>
<footer>Copyright</footer></body></html>"""


def site(pages: dict[str, Any], robots: str = "User-agent: *\nAllow: /", seen: list[str] | None = None) -> httpx.Client:
    """A fake web site. A page is HTML text, a (status, headers, body) tuple, or a callable."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if seen is not None:
            seen.append(url)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        page = pages.get(url)
        if callable(page):
            page = page()
        if page is None:
            return httpx.Response(404)
        if isinstance(page, tuple):
            status, headers, body = page
            return httpx.Response(status, headers=headers, content=body)
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=page)

    return httpx.Client(transport=httpx.MockTransport(handler))


def item(predicate: str, value: str, sentence: str, institution: str = "", description: str = "", examples: list[str] | None = None, confidence: float = 0.9) -> dict[str, Any]:
    return {
        "predicate": predicate,
        "institution": institution,
        "value": value,
        "description": description,
        "examples": examples or [],
        "sentence": sentence,
        "confidence": confidence,
    }


DISCOUNT_ITEM = item(
    "known_scam_pattern",
    "third_party_fee_discount",
    SCAM_SENTENCE,
    description="A fake agent offers a tuition discount.",
    examples=["discounted rate"],
)


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources, "effective_agent_mode", lambda: "live")


def add_page(session: Session, *answers: dict[str, Any], pages: dict[str, Any] | None = None) -> Source:
    return sources.add_url(session, PAGE_URL, http=site(pages or {PAGE_URL: PAGE}), llm=StandInClient({"items": list(answers)}), now=NOW)


def agent_offer_claims() -> list[Claim]:
    return [
        Claim("agent_of_institution", {"institution_name": SPIU}, "official agent"),
        Claim("fee_discount", {"description": "15% off"}, "15% off"),
        Claim("pays_via_third_party", {}, "Lim Wei Jie"),
    ]


def verdict(session: Session) -> list[str]:
    """The rules that fire for a fixed agent offer, with today's trusted facts."""
    claims = agent_offer_claims()
    result = judge(claims, facts.collect(session, the_user(session)), facts.ground(claims, session))
    return [conclusion["rule"] for conclusion in result["conclusions"]]


def items_of(session: Session, source: Source) -> list[SourceItem]:
    session.refresh(source)
    return list(source.items)


# ---------------------------------------------------------------- the seed


def test_the_seed_holds_two_bundled_sources_approved_by_seed(session: Session) -> None:
    seeded = list(session.scalars(select(Source).order_by(Source.id)))

    assert [(source.kind, source.title, source.domain) for source in seeded] == [
        ("bundled", "Scam advisory (sample)", None),
        ("bundled", "SPIU payment policy", "spiu.example"),
    ]
    items = [item for source in seeded for item in source.items]
    assert len(items) == 10
    assert {(item.status, item.reviewer, item.model) for item in items} == {("approved", "seed", None)}
    # No example phrases: with only the seed, the keyword layer and the claims prompt are as measured.
    assert all(item.examples == [] for item in items) and sources.approved_patterns(session) == []
    assert sources.pattern_hints(sources.approved_patterns(session)) == ""
    assert audit_events(session) == ["system.genesis", "system.reset"]


def test_every_policy_fact_and_scam_pattern_now_comes_from_an_approved_item(session: Session) -> None:
    trusted = facts.collect(session, the_user(session))
    from_items = [fact for fact in trusted if fact.atom[0] in ("policy", "official_channel", "known_scam_pattern")]

    assert len(from_items) == 10
    assert all(cite.reviewer == "seed" for fact in from_items for cite in facts.cites(fact))


# ---------------------------------------------------------------- fetching


def test_a_page_is_read_from_its_main_part_without_scripts_or_menus() -> None:
    page = fetch(PAGE_URL, site({PAGE_URL: PAGE}))

    assert page.title == "Fee payment scams"
    assert SCAM_SENTENCE in page.text and "Pay only through the student portal." in page.text
    assert "var x" not in page.text and "Home | Fees" not in page.text and "Copyright" not in page.text


def test_robots_txt_is_respected_and_the_page_is_never_requested() -> None:
    seen: list[str] = []
    client = site({"https://www.example.edu/private/page": PAGE}, robots="User-agent: *\nDisallow: /private/", seen=seen)

    with pytest.raises(FetchError, match="robots.txt does not allow"):
        fetch("https://www.example.edu/private/page", client)
    assert seen == ["https://www.example.edu/robots.txt"]


def test_a_disallowed_page_adds_no_source(session: Session, live: None) -> None:
    client = site({PAGE_URL: PAGE}, robots="User-agent: *\nDisallow: /fees/")

    with pytest.raises(SourceError, match="robots.txt"):
        sources.add_url(session, PAGE_URL, http=client, llm=StandInClient({"items": [DISCOUNT_ITEM]}), now=NOW)
    assert session.scalars(select(Source).where(Source.kind == "url")).all() == []


def test_redirects_size_and_type_are_limited() -> None:
    hops = {f"https://www.example.edu/{n}": (301, {"location": f"/{n + 1}"}, b"") for n in range(5)}
    with pytest.raises(FetchError, match="more than three"):
        fetch("https://www.example.edu/0", site(hops))
    fine = {**{f"https://www.example.edu/{n}": (302, {"location": f"/{n + 1}"}, b"") for n in range(3)}, "https://www.example.edu/3": PAGE}
    assert fetch("https://www.example.edu/0", site(fine)).url == "https://www.example.edu/3"

    with pytest.raises(FetchError, match="Only HTML pages and PDF"):
        fetch(PAGE_URL, site({PAGE_URL: (200, {"content-type": "image/png"}, b"\x89PNG")}))
    with pytest.raises(FetchError, match="larger than 2 MB"):
        fetch(PAGE_URL, site({PAGE_URL: (200, {"content-type": "text/html"}, b"a" * (MAX_BYTES + 1))}))
    with pytest.raises(FetchError, match="https://"):
        fetch("file:///etc/passwd")


# ---------------------------------------------------------------- the checks on every proposal


def test_an_invented_sentence_is_dropped(session: Session, live: None) -> None:
    invented = item("known_scam_pattern", "deadline_pressure", "Pay within one hour or lose your place.", description="Pressure.")

    source = add_page(session, DISCOUNT_ITEM, invented)

    assert [(item.value, item.sentence) for item in items_of(session, source)] == [("third_party_fee_discount", SCAM_SENTENCE)]
    assert source.dropped == 1
    assert audit_events(session)[2:] == ["source.added", "source.fetched", "fact.proposed"]


@pytest.mark.parametrize(
    "candidate, reason",
    [
        (Candidate("rule", "", "x", SCAM_SENTENCE), "not in the vocabulary"),
        (Candidate("policy", SPIU, "always_discounts", SCAM_SENTENCE), "not a known policy"),
        (Candidate("known_scam_pattern", "", "free_money", SCAM_SENTENCE, "A scam."), "not a known scam pattern"),
        (Candidate("policy", "University of Nowhere", "no_payment_agents", SCAM_SENTENCE), "not a registered institution"),
        (Candidate("known_scam_pattern", "", "deadline_pressure", SCAM_SENTENCE, ""), "one-line description"),
        (Candidate("official_account", SPIU, "6217 9988 2041 5530", SCAM_SENTENCE), "account number must be in the sentence"),
    ],
)
def test_only_the_fixed_vocabulary_is_accepted(session: Session, candidate: Candidate, reason: str) -> None:
    registered = list(session.scalars(select(Institution)))
    with pytest.raises(Invalid, match=reason):
        vocabulary.check(candidate, registered, text=PAGE + SCAM_SENTENCE, source_domain="spiu.example", fetched=True)


def test_odd_example_phrases_are_left_out_but_the_item_is_kept(session: Session, live: None) -> None:
    long_example = "pay tuition fees directly on behalf of the student at a discounted rate, sometimes ten to twenty percent off"
    proposal = {**DISCOUNT_ITEM, "examples": ["discounted rate", long_example, "x", "discounted rate"]}

    source = add_page(session, proposal)

    assert [(item.value, item.examples) for item in items_of(session, source)] == [("third_party_fee_discount", ["discounted rate"])]
    assert source.dropped == 0


def test_another_site_can_never_state_facts_about_spiu(session: Session, live: None) -> None:
    """A real university's warning is scam-pattern evidence, never a fact about SPIU."""
    about_spiu = item("policy", "no_payment_agents", SCAM_SENTENCE, institution=SPIU)

    source = add_page(session, DISCOUNT_ITEM, about_spiu)

    assert [item.predicate for item in items_of(session, source)] == ["known_scam_pattern"]
    assert source.dropped == 1


# ---------------------------------------------------------------- review and verdicts


def spiu_source(session: Session, sentence: str) -> Source:
    """A page on SPIU's own domain, stored directly (the fetch is tested above)."""
    source = Source(kind="url", title="SPIU fees", url="https://www.spiu.example/fees", domain="spiu.example", fetched_at=NOW, content_hash="h", created_at=NOW)
    session.add(source)
    session.flush()
    sources.store(session, source, [Candidate("policy", SPIU, "no_payment_agents", sentence)], text=sentence, model="test-model", now=NOW)
    session.commit()
    return source


def test_unapproved_and_rejected_items_never_change_a_verdict_and_approving_does(session: Session) -> None:
    seeded = session.scalars(select(SourceItem).where(SourceItem.value == "no_payment_agents")).one()
    assert "R2" in verdict(session)

    sources.reject(session, seeded.id, now=NOW)
    assert "R2" not in verdict(session)  # rejected: the fact is gone

    source = spiu_source(session, "The University never uses payment agents.")
    proposed = items_of(session, source)[0]
    assert proposed.status == "proposed" and "R2" not in verdict(session)  # proposed: still nothing

    sources.approve(session, proposed.id, now=NOW)
    assert "R2" in verdict(session)  # approved: active at once
    r2 = next(fact for fact in facts.collect(session, the_user(session)) if fact.atom == ("policy", SPIU, "no_payment_agents"))
    assert [(cite.title, cite.domain, cite.reviewer) for cite in facts.cites(r2)] == [("SPIU fees", "spiu.example", "Demo reviewer")]
    assert audit_events(session)[-3:] == ["fact.rejected", "fact.proposed", "fact.approved"]


def test_a_review_rechecks_stored_documents_at_once(session: Session) -> None:
    document = ingest_demo(session, "agent_offer")
    assert "R2" in [item["rule"] for item in document.claim_check["conclusions"]]
    seeded = session.scalars(select(SourceItem).where(SourceItem.value == "no_payment_agents")).one()

    sources.reject(session, seeded.id, now=NOW)

    session.refresh(document)
    assert "R2" not in [item["rule"] for item in document.claim_check["conclusions"]]
    assert audit_events(session)[-2:] == ["fact.rejected", "claims.checked"]


def test_editing_stays_within_the_vocabulary_and_needs_approval_again(session: Session) -> None:
    seeded = session.scalars(select(SourceItem).where(SourceItem.value == "deadline_pressure")).one()

    with pytest.raises(SourceError, match="not a known scam pattern"):
        sources.edit(session, seeded.id, {"value": "anything_goes"}, now=NOW)
    edited = sources.edit(session, seeded.id, {"examples": ["last chance"]}, now=NOW)

    assert (edited.status, edited.edited, edited.examples, edited.reviewer) == ("proposed", True, ["last chance"], None)
    assert ("known_scam_pattern", "deadline_pressure") not in [fact.atom for fact in facts.collect(session, the_user(session))]
    assert audit_events(session)[-1] == "fact.edited"


def test_a_changed_page_marks_its_items_for_re_review(session: Session, live: None) -> None:
    versions = iter([PAGE, PAGE, PAGE.replace("full fee", "whole fee")])
    pages: dict[str, Callable[[], str]] = {PAGE_URL: lambda: next(versions)}
    source = add_page(session, DISCOUNT_ITEM, pages=pages)
    sources.approve(session, items_of(session, source)[0].id, now=NOW)

    sources.refetch(session, source.id, http=site(pages), now=NOW)  # same text
    assert [item.status for item in items_of(session, source)] == ["approved"]

    sources.refetch(session, source.id, http=site(pages), now=NOW)  # changed text
    assert [item.status for item in items_of(session, source)] == ["needs_review"]
    fetched = [entry for entry in audit_events(session) if entry == "source.fetched"]
    assert len(fetched) == 3
    patterns = [fact for fact in facts.collect(session, the_user(session)) if fact.atom == ("known_scam_pattern", "third_party_fee_discount")]
    assert [cite.title for fact in patterns for cite in facts.cites(fact)] == ["Scam advisory (sample)"]


# ---------------------------------------------------------------- what an approved pattern feeds


def test_an_approved_pattern_feeds_the_keyword_layer_and_the_claims_prompt(session: Session, live: None) -> None:
    message = "Hi, I am an agent. I can pay your fees at a discounted rate for you."
    source = add_page(session, DISCOUNT_ITEM)
    before = ingest_text(session, message)
    assert not any(signal["code"] == "SCAM_PATTERN" for signal in before.risk_signals)  # proposed only

    sources.approve(session, items_of(session, source)[0].id, now=NOW)
    after = ingest_text(session, message)

    scam = next(signal for signal in after.risk_signals if signal["code"] == "SCAM_PATTERN")
    assert scam["matches"][-1] == {
        "category": "third_party_fee_discount",
        "text": "discounted rate",
        "sentence": "I can pay your fees at a discounted rate for you.",
        "source": "Fee payment scams",
    }
    hints = sources.pattern_hints(sources.approved_patterns(session))
    assert "third_party_fee_discount" in hints and '"discounted rate"' in hints


# ---------------------------------------------------------------- the API


def test_in_scripted_mode_the_page_lists_sources_and_adding_one_needs_live_mode(client: TestClient) -> None:
    listing = client.get("/sources").json()

    assert (listing["can_add"], listing["note"]) == (False, "Adding a source needs live mode.")
    assert [(source["title"], source["counts"]["approved"]) for source in listing["sources"]] == [
        ("Scam advisory (sample)", 6),
        ("SPIU payment policy", 4),
    ]
    response = client.post("/sources", json={"url": PAGE_URL})
    assert (response.status_code, response.json()["detail"]) == (409, "Adding a source needs live mode.")
    detail = client.get("/sources/2").json()
    first = detail["items"][0]
    assert (first["label"], first["words"]["en"], first["link"]) == (
        "Official channel",
        "SPIU takes payment only by its official account or student portal",
        None,
    )
    vocabulary_out = client.get("/sources/vocabulary").json()
    assert [choice["name"] for choice in vocabulary_out["policies"]] == list(vocabulary.POLICIES)


def test_review_through_the_api(client: TestClient) -> None:
    item_id = client.get("/sources/1").json()["items"][1]["id"]

    rejected = client.post(f"/source-items/{item_id}/reject").json()
    assert (rejected["status"], rejected["reviewer"]) == ("rejected", "Demo reviewer")
    assert client.post(f"/source-items/{item_id}/reject").status_code == 409
    assert client.post(f"/source-items/{item_id}/approve").status_code == 409
    edited = client.patch(f"/source-items/{item_id}", json={"description": "A deadline of hours."}).json()
    assert (edited["status"], edited["edited"]) == ("proposed", True)
    assert client.post(f"/source-items/{item_id}/approve").json()["status"] == "approved"
    assert client.patch(f"/source-items/{item_id}", json={"value": "made_up"}).status_code == 422
    assert client.post("/source-items/999/approve").status_code == 404


def test_a_blocked_payment_cites_every_source_of_a_fact(client: TestClient) -> None:
    """Approve a second source for a scam pattern: the blocked panel's reasoning cites both."""
    from app.db import get_engine

    with Session(get_engine()) as session:
        source = Source(kind="url", title="Fee payment scams", url=PAGE_URL, domain="example.edu", fetched_at=NOW, content_hash="h", created_at=NOW)
        session.add(source)
        session.flush()
        candidate = Candidate("known_scam_pattern", "", "third_party_fee_discount", SCAM_SENTENCE, "A fake agent offers a discount.")
        stored, _ = sources.store(session, source, [candidate], text=PAGE, model="test-model", now=NOW)
        session.commit()
        sources.approve(session, stored[0].id, now=NOW)

    client.post("/demo/documents/agent_offer")
    blocked = only(say(client, "Can I pay through this agent?"), "blocked")[0]

    r4 = next(item for item in blocked["claim_check"]["reasoning"] if item["rule"] == "R4")
    cites = [cite["text"]["en"] for line in r4["lines"] for cite in line["cites"]]
    assert "Source: Scam advisory (sample), approved by seed on 15 Sep 2026" in cites
    assert any(text.startswith("Source: Fee payment scams (example.edu), approved by Demo reviewer on ") for text in cites)
    assert next(cite["url"] for line in r4["lines"] for cite in line["cites"] if cite["title"] == "Fee payment scams") == PAGE_URL
