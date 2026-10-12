"""
The scripted driver (AGENT_MODE=scripted): a deterministic stand-in for the LLM.

It only decides WHICH tool to call next and fills reply templates from the results.
Every call still goes through the real policy engine, ledger and audit log, exactly as
a live model's would. It never skips a proposal: when the student asks to pay a scam
request, it proposes the payment and lets the policy engine refuse it.
"""

import re
from collections.abc import Generator

from app.agent import replies
from app.agent.types import ToolCall, ToolResult, Trigger, TurnContext

Script = Generator[ToolCall, ToolResult, None]

# Intents, matched by keywords in English, Malay and Chinese, in this order.
FORWARD = re.compile(r"\bforward\b|pindahkan|转给|转出|转到", re.I)
THROUGH_AGENT = re.compile(r"\bagent\b|\bthrough\b|\bejen\b|\bmelalui\b|代理|代缴", re.I)
DEADLINE = re.compile(r"\bdeadline\b|\bbefore\b|\bon time\b|tarikh akhir|\bsebelum\b|截止|到期", re.I)
PAY = re.compile(r"\bpay\b|\bbayar\b|付款|支付|能付|缴费", re.I)
SPENDING = re.compile(r"\bspend(?:ing)?\b|\bperbelanjaan\b|\bbelanja\b|消费|支出", re.I)


class ScriptedDriver:
    def __init__(self, trigger: Trigger, context: TurnContext) -> None:
        self._context = context
        self._script = self._choose(trigger)
        self._started = False

    def next_calls(self, results: list[ToolResult]) -> list[ToolCall]:
        try:
            if not self._started:
                self._started = True
                return [next(self._script)]
            return [self._script.send(results[0])]
        except StopIteration:
            return []

    # ---------------------------------------------------------------- choosing a script

    def _choose(self, trigger: Trigger) -> Script:
        if trigger.kind == "document" and trigger.document_id is not None:
            return self._explain_document(trigger.document_id)
        text = trigger.text
        latest = self._context.latest_document or {}
        if FORWARD.search(text) or THROUGH_AGENT.search(text):
            return self._pay_latest_request()
        if DEADLINE.search(text):
            return self._plan_and_pay()
        if PAY.search(text):
            # "Pay this": a clean invoice gets a funding plan; anything else is proposed as it is.
            if latest.get("bill_id") is not None and latest.get("bill_id") == self._context.payable_invoice_bill_id:
                return self._plan_and_pay()
            return self._pay_latest_request()
        if SPENDING.search(text):
            return self._spending()
        return self._reply(replies.fallback())

    def _respond(self, texts: replies.Texts) -> ToolCall:
        text, text_en = replies.both(texts, self._context.language)
        return ToolCall("respond_to_user", {"text": text, "text_en": text_en})

    # ---------------------------------------------------------------- scripts

    def _reply(self, texts: replies.Texts) -> Script:
        yield self._respond(texts)

    def _explain_document(self, document_id: int) -> Script:
        """After an upload or a pasted message: read it, check the payee, explain it."""
        read = yield ToolCall("read_document", {"document_id": document_id})
        document = read.data
        if document.get("bill"):
            yield ToolCall("verify_payee", {"payee_id": document["bill"]["payee_id"]})
        explanation = document.get("explanation") or {}
        if not explanation:
            yield self._respond(replies.no_bill())
            return
        # The explanation was built from verified fields; for a flagged document it already
        # carries the risk warnings and the university's policy clause.
        yield self._respond({language: explanation[language] for language in ("ms", "en", "zh")})

    def _plan_and_pay(self) -> Script:
        """"Can I pay this before the deadline?": check balances, plan, quote, then propose each step."""
        bill_id = self._context.payable_invoice_bill_id
        if bill_id is None:
            yield self._respond(replies.no_bill())
            return
        balances = yield ToolCall("get_balances", {})
        planned = yield ToolCall("plan_funding", {"bill_id": bill_id})
        plan = planned.data
        if plan["status"] == "not_payable":
            yield self._respond(replies.no_bill())
            return
        if plan["status"] == "insufficient_funds":
            yield self._respond(replies.plan_insufficient(plan))
            return

        steps = {step["tool"]: step for step in plan["steps"]}
        wallets = {item["currency"]: item["account_id"] for item in balances.data["accounts"]}
        pay_args = {"bill_id": bill_id, "from_account_id": wallets[plan["currency"]]}
        quote = None

        # If the policy would refuse the payment anyway, do not set up a conversion for it.
        payment_refused = steps["pay_bill"]["predicted_tier"] == "REFUSED"
        if "convert_currency" in steps and not payment_refused:
            convert_args = steps["convert_currency"]["args"]
            quoted = yield ToolCall(
                "get_transfer_quote",
                {
                    "amount_source_minor": convert_args["amount_minor"],
                    "from_currency": convert_args["from_currency"],
                    "to_currency": convert_args["to_currency"],
                },
            )
            quote = quoted.data
            conversion = yield ToolCall("convert_currency", convert_args)
            if conversion.verdict == "refused":
                yield self._respond(replies.blocked(conversion.data["reasons"]))
                return

        payment = yield ToolCall("pay_bill", pay_args)
        if payment.verdict == "refused":
            yield self._respond(replies.blocked(payment.data["reasons"]))
            return
        if quote:
            yield self._respond(replies.plan_with_conversion(plan, quote))
        else:
            yield self._respond(replies.plan_ready(plan, payment.data["cost_breakdown"]["payee_name"]))

    def _pay_latest_request(self) -> Script:
        """
        "Can I pay through this agent?" or "Can I forward this money?": propose the payment the
        latest document asks for. The policy engine decides; the driver never refuses on its own.
        """
        latest = self._context.latest_document or {}
        bill = latest.get("bill")
        if not bill:
            yield self._respond(replies.no_bill())
            return
        account_id = self._context.accounts.get(bill["currency"])
        payment = yield ToolCall("pay_bill", {"bill_id": bill["bill_id"], "from_account_id": account_id})
        if payment.verdict == "refused":
            yield self._respond(replies.blocked(payment.data["reasons"]))
        else:
            yield self._respond(replies.payment_prepared(payment.data["cost_breakdown"]))

    def _spending(self) -> Script:
        insights = yield ToolCall("analyse_spending", {})
        yield self._respond(replies.spending(insights.data))
