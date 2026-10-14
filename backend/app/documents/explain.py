"""
Explanations in Malay, English and Chinese, scripted mode: fixed templates filled with
verified fields only, plus a plain-words warning for every risk found.
"""

import re
from datetime import date
from typing import Any

from app.documents.extract import Field
from app.documents.index import knowledge_passages
from app.money import format_amount, to_minor

LANGUAGES = ("ms", "en", "zh")

_MONTHS = {
    "en": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(),
    "ms": "Jan Feb Mac Apr Mei Jun Jul Ogo Sep Okt Nov Dis".split(),
}
_ORGANISATION_WORDS = re.compile(
    r"university|college|school|housing|residence|bank|company|ltd|inc|sdn|bhd|mobile|office"
    r"|universiti|kolej|syarikat|大学|学院|公司|银行|中心|处",
    re.I,
)
_RATE = re.compile(r"\d+(?:\.\d+)?%")

# Bridge's own Malay wording of the university's policy clauses (the policy is published
# in English and Chinese only).
CLAUSES_MS = {
    "official-channel": (
        "Bayar yuran hanya ke akaun rasmi Universiti yang tertera pada invois anda, atau melalui portal pelajar."
    ),
    "no-agents-no-discounts": (
        "Universiti tidak pernah menggunakan ejen pembayaran dan tidak pernah menawarkan diskaun yuran "
        "pengajian melalui pihak ketiga."
    ),
    "no-visa-threats": "Universiti tidak pernah mengugut status visa pelajar kerana yuran.",
    "contact-finance-office": "Jika ragu-ragu tentang permintaan bayaran, tanya Pejabat Kewangan sebelum membayar.",
}

_KIND_WORDS = {
    "tuition": (re.compile(r"tuition|yuran pengajian|学费", re.I), {"ms": "yuran pengajian ", "en": "tuition ", "zh": "学费"}),
    "rent": (re.compile(r"\brent\b|\bsewa\b|房租|租金", re.I), {"ms": "sewa ", "en": "rent ", "zh": "房租"}),
}

_SCAM_WORDS = {
    "urgency": {"ms": "desakan untuk membayar segera", "en": "pressure to pay quickly", "zh": "催促尽快付款"},
    "threat": {"ms": "ugutan", "en": "threats", "zh": "威胁恐吓"},
    "secrecy": {"ms": "permintaan supaya dirahsiakan", "en": "a request for secrecy", "zh": "要求保密"},
}
# Approved scam patterns from rule sources, when their example phrases match.
_SCAM_WORDS |= {
    "deadline_pressure": _SCAM_WORDS["urgency"],
    "secrecy_request": _SCAM_WORDS["secrecy"],
    "third_party_fee_discount": {"ms": "diskaun untuk membayar pihak ketiga", "en": "a discount for paying a third party", "zh": "向第三方付款可享折扣"},
    "visa_threat": {"ms": "ugutan visa", "en": "a visa threat", "zh": "签证威胁"},
    "personal_account_request": {"ms": "bayaran ke akaun peribadi", "en": "payment into a personal account", "zh": "付款到个人账户"},
    "changed_account_details": {"ms": "akaun yang bertukar", "en": "a changed account", "zh": "账户变更"},
    "money_mule_forwarding": {"ms": "memindahkan wang bagi orang asing", "en": "forwarding money for a stranger", "zh": "替陌生人转账"},
}


def format_date(value: date, language: str) -> str:
    if language == "zh":
        return f"{value.year}年{value.month}月{value.day}日"
    return f"{value.day} {_MONTHS[language][value.month - 1]} {value.year}"


def looks_like_person(name: str) -> bool:
    return not _ORGANISATION_WORDS.search(name)


def clause_text(clause: str | None, language: str, fallback: str) -> str:
    """The first sentence of a policy clause in the wanted language."""
    if clause and language == "ms" and clause in CLAUSES_MS:
        return CLAUSES_MS[clause]
    for passage in knowledge_passages():
        if clause and passage.clause == clause and passage.language == language and passage.source == "policy":
            return re.split(r"(?<=[.。])\s*", passage.text)[0]
    return fallback


def _join(items: list[str], language: str) -> str:
    if language == "zh":
        return "、".join(items)
    word = " dan " if language == "ms" else " and "
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + word + items[-1]


def amount_text(fields: dict[str, Field]) -> str | None:
    """The verified amount with its currency code, e.g. "CNY 12,000.00"."""
    amount, currency = fields.get("amount"), fields.get("currency")
    if not (amount and currency and amount.verified and currency.verified):
        return None
    return format_amount(to_minor(amount.value, currency.value), currency.value)


def build(
    *,
    kind: str,
    visible_text: str,
    fields: dict[str, Field],
    signals: list[dict[str, Any]],
    untrusted: bool,
    account_status: str,  # official | known | new | none
    payable: bool,
    institution_names: tuple[str, str] | None = None,  # (name, local name) of the registered institution named
) -> dict[str, str]:
    """A short explanation per language, from verified fields only."""
    verified = {name: field for name, field in fields.items() if field.verified}
    by_code = {signal["code"]: signal for signal in signals}
    return {
        language: ("" if language == "zh" else " ").join(
            _sentences(language, kind, visible_text, verified, by_code, untrusted, account_status, payable, institution_names)
        )
        for language in LANGUAGES
    }


def _sentences(
    language: str,
    kind: str,
    visible_text: str,
    fields: dict[str, Field],
    signals: dict[str, dict[str, Any]],
    untrusted: bool,
    account_status: str,
    payable: bool,
    institution_names: tuple[str, str] | None,
) -> list[str]:
    ms, en, zh = language == "ms", language == "en", language == "zh"
    out: list[str] = []

    def say(malay: str, english: str, chinese: str) -> None:
        out.append(malay if ms else english if en else chinese)

    issuer = fields.get("issuer")
    local = fields.get("issuer_local_name")
    if institution_names and (issuer or local):
        # A registered institution: use its name in the reader's language.
        name: str | None = institution_names[1] if zh else institution_names[0]
    else:
        name = issuer.value if issuer else local.value if local else None
    subject = next((words[language] for pattern, words in _KIND_WORDS.values() if pattern.search(visible_text)), "")

    english_invoice = f"a {subject}invoice" if subject else "an invoice"
    if kind == "invoice" and name:
        say(f"Ini invois {subject}daripada {name}.", f"This is {english_invoice} from {name}.", f"这是{name}的{subject}缴费通知。")
    elif kind == "invoice":
        say(f"Ini invois {subject}".strip() + ".", f"This is {english_invoice}.", f"这是一份{subject}缴费通知。")
    elif name:
        say(f"Mesej ini mendakwa datang daripada {name}.", f"This message claims to come from {name}.", f"这条信息自称来自{name}。")
    else:
        say("Ini mesej yang meminta anda membuat bayaran.", "This is a message asking you to make a payment.", "这是一条要求您付款的信息。")

    amount = amount_text(fields)
    if amount:
        say(f"Jumlah: {amount}.", f"Amount: {amount}.", f"金额：{amount}。")
    if "due_date" in fields:
        due = format_date(date.fromisoformat(fields["due_date"].value), language)
        say(f"Tarikh akhir: {due}.", f"Due date: {due}.", f"截止日期：{due}。")

    if account_status == "official":
        say(
            "Akaun penerima sepadan dengan akaun rasmi universiti.",
            "The payee account matches the university's official account.",
            "收款账户与学校的官方账户一致。",
        )
    elif account_status == "known":
        say("Anda pernah membayar ke akaun ini.", "You have paid this account before.", "您以前向该账户付过款。")
    elif account_status == "new" and not signals and not untrusted:
        say("Ini akaun penerima yang baharu.", "This is a new payee account.", "这是一个新的收款账户。")

    late_fee = fields.get("late_fee_terms")
    rate = _RATE.search(late_fee.value) if late_fee else None
    if late_fee and rate and re.search(r"per day|sehari|每日", late_fee.value):
        say(
            f"Denda lewat {rate.group(0)} sehari dikenakan selepas tarikh akhir.",
            f"A late fee of {rate.group(0)} per day applies after the due date.",
            f"逾期将按每日{rate.group(0)}收取滞纳金。",
        )

    if untrusted:
        say(
            "Amaran: dokumen ini mengandungi teks tersembunyi yang ditujukan kepada pembantu AI. Bridge mengabaikannya.",
            "Warning: this document contains hidden text written for an AI assistant. Bridge ignored it.",
            "警告：该文件含有写给 AI 助手的隐藏文字，Bridge 已将其忽略。",
        )

    not_official = signals.get("PAYEE_NOT_OFFICIAL")
    if not_official:
        payee = not_official.get("payee_name")
        if payee and looks_like_person(payee):
            say(
                f"Akaun ini milik individu ({payee}), bukan akaun rasmi universiti.",
                f"The account belongs to a person ({payee}), not to the university's official account.",
                f"该账户属于个人（{payee}），不是学校的官方账户。",
            )
        else:
            say(
                "Akaun ini bukan akaun rasmi universiti.",
                "The account is not the university's official account.",
                "该账户不是学校的官方账户。",
            )

    discount = signals.get("THIRD_PARTY_DISCOUNT")
    if discount:
        clause = discount.get("policy_clause")
        if clause:
            quote = clause_text(clause.get("clause"), language, clause["text"])
            say(
                f"Dasar bayaran universiti menyatakan: “{quote}”",
                f"The university's payment policy says: “{quote}”",
                f"学校的缴费规定写明：“{quote}”",
            )
        else:
            say(
                "Mesej ini menawarkan diskaun melalui pihak ketiga.",
                "It offers a discount through a third party.",
                "该信息声称可通过第三方获得折扣。",
            )

    changed = signals.get("BANK_DETAILS_CHANGED")
    if changed:
        known = changed["known_account"]
        say(
            f"Akaun ini berbeza daripada akaun yang pernah anda bayar ({known}).",
            f"The account differs from the one you paid before ({known}).",
            f"该账户与您以前付款的账户（{known}）不同。",
        )

    scam = signals.get("SCAM_PATTERN")
    if scam:
        signs = _join(list(dict.fromkeys(_SCAM_WORDS[category][language] for category in scam["categories"])), language)
        say(f"Tanda amaran: {signs}.", f"Warning signs: {signs}.", f"危险信号：{signs}。")

    if signals or untrusted:
        say(
            "Jangan bayar. Gunakan saluran rasmi sahaja.",
            "Do not pay this. Use only the official channel.",
            "请不要付款，只通过官方渠道缴费。",
        )
    elif not payable:
        say(
            "Bridge tidak dapat mengesahkan jumlah atau akaun, jadi bayaran tidak boleh dibuat.",
            "Bridge could not verify the amount or the account, so this cannot be paid.",
            "Bridge 无法核实金额或账户，因此无法付款。",
        )
    return out


# Added when the claim check blocks something the keyword rules did not find.
CLAIM_CHECK_NOTE = {
    "ms": "Semakan dakwaan menemui masalah: {titles}.",
    "en": "The claim check found a problem: {titles}.",
    "zh": "声明核查发现问题：{titles}。",
}
