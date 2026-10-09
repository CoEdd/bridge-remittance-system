"""
Field extraction, scripted mode: fixed regular expressions for English, Chinese and
Malay labels. Every field carries the exact source text it came from and its offsets.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

FIELD_NAMES = (
    "issuer",
    "issuer_local_name",
    "payee_name",
    "payee_account",
    "bank_name",
    "amount",
    "currency",
    "due_date",
    "late_fee_terms",
)

# Words for a currency -> ISO 4217 code.
CURRENCY_CODES = {"CNY": "CNY", "RMB": "CNY", "人民币": "CNY", "MYR": "MYR", "RM": "MYR", "USD": "USD"}

ENGLISH_MONTHS = {
    name: number
    for number, name in enumerate(
        "january february march april may june july august september october november december".split(), start=1
    )
}
MALAY_MONTHS = {
    name: number
    for number, name in enumerate(
        "januari februari mac april mei jun julai ogos september oktober november disember".split(), start=1
    )
}
MONTHS = {**ENGLISH_MONTHS, **MALAY_MONTHS}

_CURRENCY = r"(?P<currency>CNY|RMB|人民币|MYR|USD)"
_NUMBER = r"(?P<number>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
_MONEY = rf"{_CURRENCY}[ \t]*{_NUMBER}"
_LABEL_END = r"[^:：\n]*[:：][ \t]*"
_DATE_WORDS = r"\d{1,2}[ \t]+[A-Za-z]+[ \t]+\d{4}"
_DATE_ZH = r"\d{4}年\d{1,2}月\d{1,2}日"
_REST_OF_LINE = r"(?P<span>[^\n]+)"
_DIGIT_GROUPS = r"(?P<span>\d[\d \t-]{6,40}\d)"
_CJK = re.compile(r"[一-鿿]")

# In order of preference: English labels first, then Chinese, then Malay, then message wording.
AMOUNT_PATTERNS = [
    re.compile(rf"^Amount due{_LABEL_END}(?P<span>{_MONEY})", re.I | re.M),
    re.compile(rf"^(?:应缴金额|金额){_LABEL_END}(?P<span>{_MONEY}(?:[ \t]*元)?)", re.M),
    re.compile(rf"^(?:Jumlah|Amount|Total){_LABEL_END}(?P<span>{_MONEY})", re.I | re.M),
    re.compile(rf"\bbayar[ \t]+(?P<span>{_MONEY})", re.I),
    re.compile(rf"\b(?:forward|pay|send|transfer)[ \t]+(?P<span>{_MONEY})", re.I),
]
DUE_DATE_PATTERNS = [
    re.compile(rf"^Due date{_LABEL_END}(?P<span>{_DATE_WORDS})", re.I | re.M),
    re.compile(rf"^(?:Tarikh akhir|Tarikh tamat){_LABEL_END}(?P<span>{_DATE_WORDS})", re.I | re.M),
    re.compile(rf"(?:缴费截止日期|截止日期|到期日)[^\n]*?(?P<span>{_DATE_ZH})"),
]
PAYEE_PATTERNS = [
    re.compile(rf"^Payee{_LABEL_END}{_REST_OF_LINE}", re.I | re.M),
    re.compile(rf"^(?:收款单位|收款人){_LABEL_END}{_REST_OF_LINE}", re.M),
    re.compile(rf"^(?:Nama akaun|Nama penerima|Account name|Name){_LABEL_END}{_REST_OF_LINE}", re.I | re.M),
]
ACCOUNT_PATTERNS = [
    re.compile(rf"^(?:Account|Account number|No\. akaun|Nombor akaun){_LABEL_END}{_DIGIT_GROUPS}", re.I | re.M),
    re.compile(rf"^(?:账号|账户){_LABEL_END}{_DIGIT_GROUPS}", re.M),
]
BANK_PATTERNS = [
    re.compile(rf"^Bank{_LABEL_END}{_REST_OF_LINE}", re.I | re.M),
    re.compile(rf"^开户银行{_LABEL_END}{_REST_OF_LINE}", re.M),
]
LATE_FEE_PATTERNS = [
    re.compile(rf"^Late payment{_LABEL_END}{_REST_OF_LINE}", re.I | re.M),
    re.compile(rf"^(?:Denda lewat|Bayaran lewat){_LABEL_END}{_REST_OF_LINE}", re.I | re.M),
    re.compile(r"(?P<span>逾期[^\n。]*滞纳金[^\n。]*。?)"),
]


@dataclass
class Field:
    name: str
    value: str  # normalised: "12000.00", "CNY", "2026-11-15", or the text itself
    source: str  # the exact substring of the document the value came from
    start: int
    end: int
    verified: bool = False
    note: str | None = None  # why the field is unverified


def parse_amount(text: str) -> Decimal | None:
    """The first number in the text, e.g. "CNY 12,000.00" -> Decimal("12000.00")."""
    match = re.search(_NUMBER.replace("?P<number>", ""), text)
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def parse_date(text: str) -> date | None:
    """Understands "15 November 2026", Malay month names and "2026年11月15日"."""
    chinese = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    words = re.search(r"(\d{1,2})[ \t]+([A-Za-z]+)[ \t]+(\d{4})", text)
    try:
        if chinese:
            return date(int(chinese[1]), int(chinese[2]), int(chinese[3]))
        if words and words[2].lower() in MONTHS:
            return date(int(words[3]), MONTHS[words[2].lower()], int(words[1]))
    except ValueError:
        return None
    return None


def digits_of(text: str) -> str:
    return re.sub(r"\D", "", text)


def _preferred_part(text: str, start: int) -> tuple[str, int]:
    """
    For a bilingual value such as "Shenzhen Bay Commercial Bank 深圳湾商业银行", prefer the
    English part and accept the Chinese one. Returns the chosen text and where it starts.
    """
    chinese = _CJK.search(text)
    english = text[: chinese.start()] if chinese else text
    if english.strip():
        chosen = english.strip()
        return chosen, start + english.index(chosen)
    chosen = text.strip()
    return chosen, start + text.index(chosen)


def _first(patterns: list[re.Pattern[str]], text: str) -> re.Match[str] | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match
    return None


def _text_field(name: str, patterns: list[re.Pattern[str]], text: str) -> Field | None:
    match = _first(patterns, text)
    if not match:
        return None
    chosen, start = _preferred_part(match["span"], match.start("span"))
    return Field(name, chosen, chosen, start, start + len(chosen))


def _find(name: str, needle: str, text: str) -> Field | None:
    position = text.find(needle) if needle else -1
    return None if position < 0 else Field(name, needle, needle, position, position + len(needle))


def extract_scripted(text: str, kind: str, institutions: list[tuple[str, str]]) -> dict[str, Field]:
    """
    Extract what the fixed patterns can find. `text` must already have hidden text
    blanked out, so that hidden instructions can never supply a field.
    `institutions` lists (name, local name) of every registered institution.
    """
    fields: dict[str, Field] = {}

    def keep(field: Field | None) -> None:
        if field:
            fields[field.name] = field

    # Issuer: a registered institution named in the text, else an invoice's first line.
    for name, local_name in institutions:
        if "issuer" not in fields:
            keep(_find("issuer", name, text))
        if "issuer_local_name" not in fields:
            keep(_find("issuer_local_name", local_name, text))
    if "issuer" not in fields and "issuer_local_name" not in fields and kind == "invoice":
        first_line = re.search(r"^[ \t]*(?P<span>\S[^\n]*)", text, re.M)
        if first_line:
            heading = re.split(r"\s+[·|-]\s+", first_line["span"])[0]
            chosen, start = _preferred_part(heading, first_line.start("span"))
            keep(Field("issuer", chosen, chosen, start, start + len(chosen)))

    keep(_text_field("payee_name", PAYEE_PATTERNS, text))
    keep(_text_field("bank_name", BANK_PATTERNS, text))
    keep(_text_field("late_fee_terms", LATE_FEE_PATTERNS, text))

    account = _first(ACCOUNT_PATTERNS, text)
    if account:
        value = re.sub(r"[ \t]+", " ", account["span"].strip())
        keep(Field("payee_account", value, account["span"], account.start("span"), account.end("span")))

    amount = _first(AMOUNT_PATTERNS, text)
    if amount:
        number = Decimal(amount["number"].replace(",", ""))
        keep(Field("amount", f"{number:.2f}", amount["span"], amount.start("span"), amount.end("span")))
        code = CURRENCY_CODES[amount["currency"]]
        keep(Field("currency", code, amount["currency"], amount.start("currency"), amount.end("currency")))

    due = _first(DUE_DATE_PATTERNS, text)
    if due:
        parsed = parse_date(due["span"])
        if parsed:
            keep(Field("due_date", parsed.isoformat(), due["span"], due.start("span"), due.end("span")))

    return fields
