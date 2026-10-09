"""Small shared types for the agent loop and its drivers."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True)
class Trigger:
    """What started a turn: a chat message, or a document that was just uploaded."""

    kind: str  # message | document
    text: str = ""
    document_id: int | None = None


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    call_id: str | None = None  # the model's tool_use id in live mode


@dataclass
class ToolResult:
    call: ToolCall
    verdict: str  # allowed | pending | refused | error
    data: dict[str, Any]


@dataclass(frozen=True)
class TurnContext:
    """Facts the app gives a driver. They come from the database, not from any model."""

    language: str
    student_name: str
    demo_today: date
    accounts: dict[str, int]  # currency -> the student's wallet account id
    # The newest document, with its bill if it has one.
    latest_document: dict[str, Any] | None = None
    # Newest open bill that comes from a trusted, unflagged invoice.
    payable_invoice_bill_id: int | None = None
    open_bills: list[dict[str, Any]] = field(default_factory=list)


class Driver(Protocol):
    """Proposes tool calls. The scripted driver follows fixed scripts; the live driver asks Claude."""

    def next_calls(self, results: list[ToolResult]) -> list[ToolCall]:
        """The next tool calls, given the results of the previous ones. Empty when there is nothing more."""
        ...
