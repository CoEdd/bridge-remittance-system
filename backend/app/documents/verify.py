"""
Field verification, in plain code, for both modes.

A field is verified only if its cited source text exists verbatim in the document and
really contains the value. An unverified field can never be used for a payment.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.documents.extract import CURRENCY_CODES, Field, digits_of, parse_date

# ISO 4217 codes Bridge accepts as a document currency.
ISO_4217 = frozenset({"CNY", "MYR", "USD", "EUR", "GBP", "SGD", "HKD", "JPY", "AUD"})
MIN_ACCOUNT_DIGITS = 8

_NUMBERS = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?")


def _check(field: Field) -> str | None:
    """Returns why the value is not supported by its source, or None when it is."""
    source = field.source
    if field.name == "amount":
        try:
            value = Decimal(field.value)
        except InvalidOperation:
            return "The amount is not a number."
        found = [Decimal(number.replace(",", "")) for number in _NUMBERS.findall(source)]
        return None if value > 0 and value in found else "The amount is not in the cited text."
    if field.name == "payee_account":
        digits = digits_of(field.value)
        if len(digits) < MIN_ACCOUNT_DIGITS:
            return "The account number is too short."
        return None if digits == digits_of(source) else "The account digits are not in the cited text."
    if field.name == "due_date":
        try:
            value_date = date.fromisoformat(field.value)
        except ValueError:
            return "The date cannot be read."
        return None if parse_date(source) == value_date else "The date is not in the cited text."
    if field.name == "currency":
        code = CURRENCY_CODES.get(source.strip().upper(), CURRENCY_CODES.get(source.strip()))
        if field.value not in ISO_4217:
            return "The currency is not a valid ISO 4217 code."
        return None if code == field.value else "The currency does not match the cited text."
    # Text fields: the value must be the cited text, or a part of it.
    return None if field.value.strip() and field.value.strip() in source else "The value is not in the cited text."


def verify_fields(fields: dict[str, Field], raw_text: str, hidden: list[tuple[int, int]]) -> None:
    """Sets `verified` and `note` on every field."""
    for field in fields.values():
        if not field.source or raw_text[field.start : field.end] != field.source:
            field.verified, field.note = False, "The cited text is not in the document."
        elif any(field.start < end and start < field.end for start, end in hidden):
            field.verified, field.note = False, "The cited text is hidden or addressed to an AI."
        else:
            field.note = _check(field)
            field.verified = field.note is None


def locate(name: str, value: str, source: str, raw_text: str) -> Field:
    """Build a field from a value and a quoted source (live mode), finding the quote's offsets."""
    start = raw_text.find(source) if source else -1
    if start < 0:
        return Field(name, value, source, 0, 0)
    return Field(name, value, source, start, start + len(source))
