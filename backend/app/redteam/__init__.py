"""
The red-team suite: attacks run against the real policy engine, ledger and audit log.

Every case gets its own isolated copy of the database: a fresh seeded SQLite file in a
temporary folder, with its own document index. The copy is deleted when the case ends.
Nothing here opens the live demo database.

The attack itself is made by the scripted driver, whatever AGENT_MODE says, so the
results are repeatable and need no API key. What decides the outcome is not scripted.
"""

import logging
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import actions, documents, seed
from app.actions import OtpResult, Proposal
from app.agent.loop import build_context, run_turn
from app.agent.scripted import ScriptedDriver
from app.agent.types import ToolCall, ToolResult, Trigger
from app.audit.describe import event_label, summarise
from app.clock import now_utc
from app.config import get_settings
from app.db import make_engine
from app.documents.index import PassageIndex
from app.documents.reader import read_message, read_pdf
from app.fx import quote_to_receive
from app.ledger import user_account
from app.models import Account, AuditLog, Bill, Document, PendingAction, Posting, User
from app.money import format_amount
from app.seed.demo_docs import DEMO_DOCUMENTS, demo_docs_dir

logger = logging.getLogger(__name__)

Event = tuple[str, dict[str, Any]]
COPY_PREFIX = "bridge-redteam-"


class _OneCall:
    """Stands in for an LLM that makes exactly one tool call and then stops."""

    def __init__(self, call: ToolCall) -> None:
        self._rounds = [[call]]

    def next_calls(self, results: list[ToolResult]) -> list[ToolCall]:
        return self._rounds.pop(0) if self._rounds else []


class Sandbox:
    """One isolated copy of the database: what an attack can do to it, and what a case checks afterwards."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.user = session.get_one(User, seed.DEMO_USER_ID)
        self.passages = PassageIndex()  # this copy's documents never join the live index
        self.checks: list[dict[str, Any]] = []
        self.evidence: list[AuditLog] = []
        self._baseline: dict[str, int] = {}
        self._since = 0
        self._last_posting = 0
        self.mark()

    # ------------------------------------------------------------ what the attack does

    def ingest(self, key: str, source: str = "upload") -> Document:
        """Take in one of the bundled documents, through the whole pipeline."""
        demo = DEMO_DOCUMENTS[key]
        data = (demo_docs_dir() / demo.filename).read_bytes()
        read = read_pdf(data) if demo.filename.endswith(".pdf") else read_message(data.decode("utf-8"))
        return documents.ingest(
            self.session,
            self.user,
            filename=demo.filename,
            kind=demo.kind,
            read=read,
            source=source,
            passages=self.passages,
            scripted=True,
        )

    def _turn(self, text: str, driver: Any) -> list[Event]:
        events: list[Event] = []
        trigger = Trigger(kind="message", text=text)
        run_turn(self.session, self.user, trigger, lambda name, data: events.append((name, data)), driver)
        return events

    def ask(self, text: str) -> list[Event]:
        """One chat turn, as the student typing `text`."""
        trigger = Trigger(kind="message", text=text)
        return self._turn(text, ScriptedDriver(trigger, build_context(self.session, self.user)))

    def tool_call(self, name: str, args: dict[str, Any]) -> list[Event]:
        """One chat turn in which the model makes exactly this tool call."""
        return self._turn("(the model proposes a tool call)", _OneCall(ToolCall(name, args, "attack")))

    def propose(self, tool: str, args: dict[str, Any]) -> Proposal:
        return actions.propose(self.session, self.user, tool, args)

    def confirm(self, action_id: int) -> PendingAction:
        return actions.confirm(self.session, self.user, action_id)

    def enter_code(self, action_id: int, code: str) -> OtpResult:
        return actions.submit_otp(self.session, self.user, action_id, code)

    def approve(self, proposal: Proposal) -> PendingAction:
        """Approve a pending action the legitimate way: confirm, then the one-time code if it asks for one."""
        assert proposal.action is not None, "the proposal was refused"
        action = self.confirm(proposal.action.id)
        if action.status == "awaiting_otp":
            action = self.enter_code(action.id, get_settings().demo_otp).action
        return action

    def add_bill(self, payee_id: int, amount_minor: int, currency: str = "CNY") -> Bill:
        """A bill on record for an existing payee, as the set-up of a limits case."""
        bill = Bill(
            user_id=self.user.id, payee_id=payee_id, amount_minor=amount_minor, currency=currency, status="open"
        )
        self.session.add(bill)
        self.session.commit()
        return bill

    def fund(self, currency: str, needed_minor: int) -> None:
        """Make sure the wallet holds `needed_minor`, by an approved conversion from the home currency."""
        shortfall = needed_minor - self.balances()[currency]
        if shortfall <= 0:
            return
        quote = quote_to_receive(self.session, shortfall, self.user.home_currency, currency, now_utc())
        proposal = self.propose(
            "convert_currency",
            {
                "from_currency": self.user.home_currency,
                "to_currency": currency,
                "amount_minor": quote.amount_minor,
                "provider_id": quote.provider_id,
            },
        )
        if self.approve(proposal).status != "executed":
            raise RuntimeError("The set-up conversion did not run.")

    def wallet(self, currency: str) -> int:
        return user_account(self.session, self.user.id, currency).id

    # ------------------------------------------------------------ what the case checks

    def balances(self) -> dict[str, int]:
        self.session.expire_all()
        rows = self.session.execute(
            select(Account.currency, Account.balance_minor).where(Account.user_id == self.user.id).order_by(Account.id)
        )
        return {currency: balance for currency, balance in rows}

    def mark(self) -> None:
        """From here on: the balances that must not change, and the audit entries and postings that count."""
        self._baseline = self.balances()
        self._since = self.session.scalar(select(AuditLog.seq).order_by(AuditLog.seq.desc()).limit(1)) or 0
        self._last_posting = self.session.scalar(select(Posting.id).order_by(Posting.id.desc()).limit(1)) or 0

    def postings(self) -> list[Posting]:
        """Ledger postings made since the mark."""
        return list(self.session.scalars(select(Posting).where(Posting.id > self._last_posting).order_by(Posting.id)))

    def check(self, label: str, passed: bool) -> bool:
        self.checks.append({"label": label, "passed": bool(passed)})
        return bool(passed)

    def money_moved(self) -> dict[str, int]:
        """Change of each wallet since the mark, leaving out the wallets that did not change."""
        now = self.balances()
        return {currency: now[currency] - before for currency, before in self._baseline.items() if now[currency] != before}

    def no_money_moved(self) -> bool:
        return self.check("No money moved", self.money_moved() == {})

    def entries(self, *event_types: str) -> list[AuditLog]:
        """This copy's audit entries since the mark, oldest first."""
        query = select(AuditLog).where(AuditLog.seq > self._since).order_by(AuditLog.seq)
        if event_types:
            query = query.where(AuditLog.event_type.in_(event_types))
        return list(self.session.scalars(query))

    def logged(self, event_type: str, **wanted: Any) -> AuditLog | None:
        """
        Check that the audit log has such an entry since the mark, and keep it as evidence.
        `reasons` matches when the entry carries at least those codes; other keys must be equal.
        """

        def matches(entry: AuditLog) -> bool:
            payload = entry.payload or {}
            return all(
                set(value) <= set(payload.get("reasons") or []) if key == "reasons" else payload.get(key) == value
                for key, value in wanted.items()
            )

        found = next((entry for entry in reversed(self.entries(event_type)) if matches(entry)), None)
        described = ", ".join(
            f"{key} {'+'.join(value) if key == 'reasons' else value}" for key, value in wanted.items()
        )
        self.check(f"Audit log has {event_type}" + (f" ({described})" if described else ""), found is not None)
        if found is not None and found not in self.evidence:
            self.evidence.append(found)
        return found

    def refused(self, tool: str, *codes: str) -> AuditLog | None:
        """Check that the tool call was refused with at least these reasons."""
        return self.logged("action.refused", tool=tool, reasons=list(codes))

    # ------------------------------------------------------------ what was observed, in words

    def refusal_line(self) -> str:
        refusals = self.entries("action.refused")
        if not refusals:
            return "Nothing was refused."
        payload = refusals[-1].payload
        return f"{payload.get('tool')} refused: {', '.join(payload.get('reasons') or [])}."

    def money_line(self) -> str:
        moved = self.money_moved()
        if not moved:
            return "No money moved."
        return "Money moved: " + ", ".join(format_amount(change, currency) for currency, change in moved.items()) + "."


@dataclass(frozen=True)
class Case:
    id: str
    title: str  # a name of two or three words
    attack: str  # what is tried, in one line
    expected: str
    # Makes the attack, records its checks on the sandbox and returns what was observed, in one line.
    run: Callable[[Sandbox], str]


@contextmanager
def isolated_copy() -> Iterator[Sandbox]:
    """A fresh seeded database in a temporary folder. Deleted on the way out."""
    with tempfile.TemporaryDirectory(prefix=COPY_PREFIX) as folder:
        engine = make_engine(f"sqlite:///{Path(folder) / 'copy.db'}")
        try:
            seed.build(engine, offline=True)  # the fixed FX snapshot: no network, same numbers every run
            with Session(engine) as session:
                yield Sandbox(session)
        finally:
            engine.dispose()


def _evidence(entry: AuditLog) -> dict[str, Any]:
    return {
        "seq": entry.seq,
        "event_type": entry.event_type,
        "label": event_label(entry.event_type),
        "summary": summarise(entry.event_type, entry.payload),
        "payload": entry.payload,
    }


def describe(case: Case, status: str) -> dict[str, Any]:
    return {
        "id": case.id,
        "title": case.title,
        "attack": case.attack,
        "status": status,
        "expected": case.expected,
        "observed": None,
        "evidence": [],
        "checks": [],
    }


def run_case(case: Case) -> dict[str, Any]:
    """Run one case in its own copy. It passes only if every one of its checks holds."""
    started = time.monotonic()
    result = describe(case, "failed")
    try:
        with isolated_copy() as box:
            result["observed"] = case.run(box)
            result["checks"] = box.checks
            result["evidence"] = [_evidence(entry) for entry in sorted(box.evidence, key=lambda entry: entry.seq)]
            if box.checks and all(check["passed"] for check in box.checks):
                result["status"] = "passed"
    except Exception as error:
        # A case that cannot run has proved nothing: it counts as failed.
        logger.exception("Red-team case %s could not run.", case.id)
        result["observed"] = f"The case could not run ({type(error).__name__})."
    result["duration_ms"] = round((time.monotonic() - started) * 1000)
    return result


def run_all() -> Iterator[Event]:
    """Every case in order: "case" as it starts, "case" with its result, then "done" with the totals."""
    from app.redteam.cases import CASES

    started = time.monotonic()
    passed = 0
    for case in CASES:
        yield "case", describe(case, "running")
        result = run_case(case)
        passed += result["status"] == "passed"
        yield "case", result
    yield "done", {"passed": passed, "total": len(CASES), "duration_ms": round((time.monotonic() - started) * 1000)}
