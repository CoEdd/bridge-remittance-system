"""
The sources every reset starts with: SPIU's payment policy and the sample scam advisory,
two files bundled with Bridge (fictional content, see the files themselves).

These items were written by people, not proposed by Claude. They go through the same
checks as any proposal (fixed vocabulary, sentence found word for word in the file) and
are stored as approved with reviewer "seed". They carry no example phrases, so with only
the seed the keyword layer and Claude's claims prompt are exactly as measured in Step 9.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.documents.index import KNOWLEDGE_DIR
from app.models import Source
from app.sources import store
from app.sources.fetch import text_hash
from app.sources.vocabulary import Candidate

SPIU = "Shenzhen Polytechnic International University"
SEED_REVIEWER = "seed"


@dataclass(frozen=True)
class SeedSource:
    title: str
    file: str
    domain: str | None
    items: tuple[Candidate, ...]


def _pattern(name: str, description: str, sentence: str) -> Candidate:
    return Candidate("known_scam_pattern", "", name, sentence, description)


SEED_SOURCES = (
    SeedSource(
        title="Scam advisory (sample)",
        file="scam_advisory_en.md",
        domain=None,
        items=(
            _pattern(
                "third_party_fee_discount",
                "Someone posing as a payment agent offers a tuition discount if you pay them instead.",
                "They offer to pay your tuition for you at a discount if you send the money to them first.",
            ),
            _pattern(
                "deadline_pressure",
                "A very short deadline, so there is no time to check.",
                'Scammers set short deadlines such as "today only" or "within two hours" so that you do not '
                "have time to check with your university.",
            ),
            _pattern(
                "visa_threat",
                "A threat to your visa, enrolment or freedom unless you pay at once.",
                "Messages that threaten your visa, your enrolment, deportation or arrest unless you pay at once "
                "are a warning sign.",
            ),
            _pattern(
                "personal_account_request",
                "Tuition to be paid into an account in a person's name.",
                "A request to pay tuition into an account in a person's name is a warning sign.",
            ),
            _pattern(
                "changed_account_details",
                "A message saying the receiving account has changed.",
                "Be careful when a message or invoice says the receiving account has changed.",
            ),
            _pattern(
                "secrecy_request",
                "A request to keep the payment secret from the finance office or family.",
                "Being told not to tell the finance office, your family or your friends is a warning sign.",
            ),
        ),
    ),
    SeedSource(
        title="SPIU payment policy",
        file="spiu_payment_policy_en.md",
        domain="spiu.example",
        items=(
            Candidate(
                "official_channel",
                SPIU,
                "official account or student portal",
                "Pay tuition and fees only to the University's official account printed on your invoice, or "
                "through the student portal.",
            ),
            Candidate(
                "policy",
                SPIU,
                "no_payment_agents",
                "The University never uses payment agents and never offers tuition discounts through third parties.",
            ),
            Candidate(
                "policy",
                SPIU,
                "no_third_party_discounts",
                "The University never uses payment agents and never offers tuition discounts through third parties.",
            ),
            Candidate(
                "policy",
                SPIU,
                "never_threatens_visa",
                "The University never threatens a student's visa status over fees.",
            ),
        ),
    ),
)


def add_seed_sources(session: Session, approved_at: datetime) -> None:
    """Store the bundled sources and their approved items. Fails loudly if any item fails a check."""
    for seed in SEED_SOURCES:
        text = (KNOWLEDGE_DIR / seed.file).read_text(encoding="utf-8")
        source = Source(
            kind="bundled",
            title=seed.title,
            url=None,
            domain=seed.domain,
            fetched_at=approved_at,
            content_hash=text_hash(text),
            created_at=approved_at,
        )
        session.add(source)
        session.flush()
        items, dropped = store(session, source, seed.items, text=text, model=None, now=approved_at, approve_as=SEED_REVIEWER)
        if dropped or len(items) != len(seed.items):
            raise RuntimeError(f"A seed item of {seed.file} failed the checks: {dropped}")
