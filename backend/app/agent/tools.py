"""
The agent's tools. One registry for both drivers (scripted and live).

Read and suggest tools (Tier 0 and 1) have a handler that looks something up. The
money-moving tools have none: for them the agent loop only calls actions.propose, which
creates a pending action for the student to approve. No tool here can execute a payment.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import documents
from app.agent import replies
from app.documents.extract import digits_of
from app.fx import get_mid_rate, get_quote, get_transfer_quote
from app.models import Account, Bill, Document, Institution, Payee, PendingAction, User
from app.money import Currency, convert, format_amount
from app.planner.funding import plan_funding
from app.planner.spending import analyse_spending
from app.policy import BASE_TIERS, AddPayeeArgs, ConvertCurrencyArgs, PayBillArgs, requires_for

MONEY_TOOLS = ("convert_currency", "pay_bill", "add_payee")


@dataclass(frozen=True)
class ToolContext:
    session: Session
    user: User
    today: date  # demo clock
    now: datetime  # real UTC


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoInput(_Input):
    pass


class GetTransactionsInput(_Input):
    currency: Currency | None = None
    category: str | None = None
    days: int | None = Field(default=None, ge=1, le=366)
    limit: int = Field(default=10, ge=1, le=50)


class ReadDocumentInput(_Input):
    document_id: int


class GetFxRateInput(_Input):
    base: Currency
    quote: Currency


class GetTransferQuoteInput(_Input):
    amount_source_minor: int = Field(gt=0, description="Amount to send, in minor units of from_currency.")
    from_currency: Currency
    to_currency: Currency


class PlanFundingInput(_Input):
    bill_id: int


class VerifyPayeeInput(_Input):
    payee_id: int


class CheckClaimsInput(_Input):
    document_id: int


class ExplainDecisionInput(_Input):
    action_id: int


class RespondInput(_Input):
    text: str = Field(min_length=1, max_length=2000, description="The reply, in the student's preferred language.")
    text_en: str = Field(min_length=1, max_length=2000, description="The same reply in English.")


Handler = Callable[[ToolContext, Any], dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    label: str  # plain English for the UI
    description: str  # for the LLM
    input_model: type[BaseModel]
    handler: Handler | None  # None: a money-moving tool, which can only be proposed

    @property
    def tier(self) -> str:
        return BASE_TIERS[self.name]


# ---------------------------------------------------------------- handlers


def _get_balances(ctx: ToolContext, _: NoInput) -> dict[str, Any]:
    home = ctx.user.home_currency
    wallets = ctx.session.scalars(select(Account).where(Account.user_id == ctx.user.id).order_by(Account.id))
    return {
        "home_currency": home,
        "accounts": [
            {
                "account_id": wallet.id,
                "currency": wallet.currency,
                "balance_minor": wallet.balance_minor,
                "home_equivalent_minor": convert(wallet.balance_minor, get_mid_rate(ctx.session, wallet.currency, home)),
            }
            for wallet in wallets
        ],
    }


def _get_transactions(ctx: ToolContext, args: GetTransactionsInput) -> dict[str, Any]:
    from app.routers.accounts import list_transactions

    rows = list_transactions(ctx.session, ctx.user, args.currency, args.category, args.days, args.limit)
    return {"transactions": [row.model_dump(mode="json") for row in rows]}


def _analyse_spending(ctx: ToolContext, _: NoInput) -> dict[str, Any]:
    from app.schemas import SpendingInsightsOut

    insights = analyse_spending(ctx.session, ctx.user, ctx.today)
    return SpendingInsightsOut.model_validate(insights).model_dump(mode="json")


def _bill_summary(bill: Bill) -> dict[str, Any]:
    return {
        "bill_id": bill.id,
        "payee_id": bill.payee_id,
        "payee_name": bill.payee.name,
        "amount_minor": bill.amount_minor,
        "currency": bill.currency,
        "due_date": bill.due_date.isoformat() if bill.due_date else None,
        "status": bill.status,
        "flagged": documents.bill_is_flagged(bill),
    }


def _read_document(ctx: ToolContext, args: ReadDocumentInput) -> dict[str, Any]:
    """What plain code verified in a document. The raw text and any hidden text are not returned."""
    document = ctx.session.get(Document, args.document_id)
    if document is None or document.user_id != ctx.user.id:
        return {"error": "There is no such document."}
    bill = ctx.session.scalars(select(Bill).where(Bill.document_id == document.id)).first()
    fields = document.extracted_fields or {}
    return {
        "document_id": document.id,
        "filename": document.filename,
        "kind": document.kind,
        "languages": document.source_language.split(","),
        "status": documents.document_status(document, bill is not None),
        "trust_flag": document.trust_flag,
        "hidden_text_found": bool(documents.hidden_findings(document)),
        "verified_fields": {name: field["value"] for name, field in fields.items() if field["verified"]},
        "unverified_fields": sorted(name for name, field in fields.items() if not field["verified"]),
        "risk_signals": [signal["code"] for signal in documents.policy_signals(document)],
        "claim_check": {
            "blocks": documents.claim_blocks(document),
            "rules": [item["rule"] for item in (document.claim_check or {}).get("conclusions") or []],
        },
        "explanation": document.explanation,
        "bill": _bill_summary(bill) if bill else None,
    }


def _check_claims(ctx: ToolContext, args: CheckClaimsInput) -> dict[str, Any]:
    """The neuro-symbolic claim check of a document, as stored when the document was read."""
    document = ctx.session.get(Document, args.document_id)
    if document is None or document.user_id != ctx.user.id:
        return {"error": "There is no such document."}
    check = document.claim_check or {}
    return {
        "document_id": document.id,
        "origin": check.get("origin"),
        "claims": [
            {
                "type": item["type"],
                "meaning": item["meaning"]["en"],
                "source": item["source"],
                "status": item["status"],
                "evidence": item["evidence"]["words"]["en"] if item["evidence"] else None,
            }
            for item in check.get("claims") or []
        ],
        "conclusions": [
            {"rule": item["rule"], "severity": item["severity"], "title": item["title"]["en"]}
            for item in check.get("conclusions") or []
        ],
    }


def _get_fx_rate(ctx: ToolContext, args: GetFxRateInput) -> dict[str, Any]:
    if args.base == args.quote:
        return {"base": args.base, "quote": args.quote, "mid_rate": "1", "source": None, "fetched_at": None}
    quote = get_quote(ctx.session, args.base, args.quote)
    return {
        "base": quote.base,
        "quote": quote.quote,
        "mid_rate": quote.mid_rate,
        "source": quote.source,
        "fetched_at": quote.fetched_at.isoformat(),
    }


def _get_transfer_quote(ctx: ToolContext, args: GetTransferQuoteInput) -> dict[str, Any]:
    quote = get_transfer_quote(ctx.session, args.amount_source_minor, args.from_currency, args.to_currency, ctx.now)
    return quote.as_breakdown()


def _plan_funding(ctx: ToolContext, args: PlanFundingInput) -> dict[str, Any]:
    return asdict(plan_funding(ctx.session, ctx.user, args.bill_id, ctx.today, ctx.now))


def _verify_payee(ctx: ToolContext, args: VerifyPayeeInput) -> dict[str, Any]:
    payee = ctx.session.get(Payee, args.payee_id)
    if payee is None or payee.user_id != ctx.user.id:
        return {"error": "There is no such payee."}
    official = next(
        (
            institution
            for institution in ctx.session.scalars(select(Institution))
            if digits_of(institution.official_account_ref) == digits_of(payee.account_ref)
        ),
        None,
    )
    return {
        "payee_id": payee.id,
        "name": payee.name,
        "account_ref": payee.account_ref,
        "bank_name": payee.bank_name,
        "verified_source": payee.verified_source,
        "is_official_account": official is not None,
        "institution": official.name if official else None,
        "first_paid_at": payee.first_paid_at.isoformat() if payee.first_paid_at else None,
        "is_new": payee.first_paid_at is None,
    }


def _explain_decision(ctx: ToolContext, args: ExplainDecisionInput) -> dict[str, Any]:
    action = ctx.session.get(PendingAction, args.action_id)
    if action is None or action.user_id != ctx.user.id:
        return {"error": "There is no such action."}
    codes = [item["code"] for item in action.reasons]
    return {
        "action_id": action.id,
        "tool": action.tool,
        "status": action.status,
        "tier": action.tier,
        "requires": requires_for(action.tier, codes),
        "why": replies.why(action.tier, codes)["en"],
        "reasons": [{"code": item["code"], "title": item["title"]["en"], "text": item["text"]["en"]} for item in action.reasons],
        "inputs": action.args,
        "cost_breakdown": action.cost_breakdown,
    }


def _respond(_: ToolContext, __: RespondInput) -> dict[str, Any]:
    return {"delivered": True}


# ---------------------------------------------------------------- registry

TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool("get_balances", "Checked your balances", "The student's wallet balances and account ids.", NoInput, _get_balances),
        Tool("get_transactions", "Looked at your transactions", "Recent transactions, newest first.", GetTransactionsInput, _get_transactions),
        Tool("analyse_spending", "Analysed your spending", "Spending by category for the last 30 days against the 30 before.", NoInput, _analyse_spending),
        Tool("read_document", "Read the document", "The verified fields, risk signals and explanation of an uploaded document.", ReadDocumentInput, _read_document),
        Tool("check_claims", "Checked its claims", "The claims a document makes, each judged by fixed rules against trusted facts.", CheckClaimsInput, _check_claims),
        Tool("get_fx_rate", "Checked the exchange rate", "The frozen mid-market rate for a currency pair.", GetFxRateInput, _get_fx_rate),
        Tool("get_transfer_quote", "Checked the true cost of this transfer", "The true cost of a conversion: fee plus exchange-rate markup.", GetTransferQuoteInput, _get_transfer_quote),
        Tool("plan_funding", "Planned how to pay", "A funding plan for one bill: shortfall, conversion and payment steps.", PlanFundingInput, _plan_funding),
        Tool("verify_payee", "Checked the payee", "Whether a payee is verified, official and paid before.", VerifyPayeeInput, _verify_payee),
        Tool("convert_currency", "Proposed a conversion", "Propose a currency conversion. The student must approve it.", ConvertCurrencyArgs, None),
        Tool("pay_bill", "Proposed a payment", "Propose paying a bill. Amount and payee always come from the bill record.", PayBillArgs, None),
        Tool("add_payee", "Proposed a new payee", "Propose saving a new payee. The student must approve it.", AddPayeeArgs, None),
        Tool("explain_decision", "Looked up the decision", "The stored verdict, reasons and inputs of an action.", ExplainDecisionInput, _explain_decision),
        Tool("respond_to_user", "Replied", "Send the final reply to the student. This ends the turn.", RespondInput, _respond),
    )
}


def tool_schemas() -> list[dict[str, Any]]:
    """Tool definitions for the Anthropic API, generated from the Pydantic input models."""
    return [
        {"name": tool.name, "description": tool.description, "input_schema": tool.input_model.model_json_schema()}
        for tool in TOOLS.values()
    ]


# ---------------------------------------------------------------- one-line summaries for the UI


def action_summary(tool: str, breakdown: dict[str, Any] | None) -> str:
    """What a money action would do, e.g. "Pay CNY 12,000.00 to ...". Built from the policy's own numbers."""
    breakdown = breakdown or {}
    if tool == "pay_bill" and "amount_minor" in breakdown:
        return f"Pay {format_amount(breakdown['amount_minor'], breakdown['currency'])} to {breakdown['payee_name']}"
    if tool == "convert_currency" and "amount_minor" in breakdown:
        received = format_amount(breakdown["amount_received_minor"], breakdown["to_currency"])
        return f"Convert {format_amount(breakdown['amount_minor'], breakdown['from_currency'])} to {received}"
    if tool == "add_payee" and "name" in breakdown:
        return f"Add payee {breakdown['name']}"
    return TOOLS[tool].label if tool in TOOLS else tool


def result_summary(tool: str, result: dict[str, Any]) -> str:
    """One line about what a read or suggest tool found."""
    if "error" in result:
        return str(result["error"])
    if tool == "get_balances":
        return " · ".join(format_amount(item["balance_minor"], item["currency"]) for item in result["accounts"])
    if tool == "get_transactions":
        return f"{len(result['transactions'])} transactions"
    if tool == "analyse_spending":
        return str(result["insight"])
    if tool == "read_document":
        signals = result["risk_signals"]
        risk = f"{len(signals)} risk signals" if signals else "no risk signals"
        return f"{result['filename']} · {result['status'].replace('_', ' ')} · {risk}"
    if tool == "check_claims":
        against = sum(item["status"] in ("contradicted", "flagged") for item in result["claims"])
        return f"{len(result['claims'])} claims · {against} contradicted or flagged" if against else f"{len(result['claims'])} claims · none contradicted"
    if tool == "get_fx_rate":
        return f"1 {result['base']} = {result['mid_rate']} {result['quote']}"
    if tool == "get_transfer_quote":
        cost = format_amount(result["total_cost_minor"], result["from_currency"])
        return f"{result['provider_name']} · true cost {cost}"
    if tool == "plan_funding":
        if result["status"] == "ready":
            return "Enough in the wallet"
        if result["status"] == "needs_conversion":
            return f"Short by {format_amount(result['shortfall_minor'], result['currency'])}: convert, then pay"
        if result["status"] == "insufficient_funds":
            return f"Short by {format_amount(result['shortfall_minor'], result['currency'])}: not enough to convert"
        return "This bill cannot be paid"
    if tool == "verify_payee":
        if result["is_official_account"]:
            return f"{result['name']} · official account"
        return f"{result['name']} · {'new payee' if result['is_new'] else 'paid before'}"
    if tool == "explain_decision":
        return f"Action #{result['action_id']} · {result['status'].replace('_', ' ')}"
    return ""

