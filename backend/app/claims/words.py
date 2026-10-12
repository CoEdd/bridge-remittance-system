"""
The claim check in plain words: what a claim means, what a trusted fact says, and the
status names, in English, Malay and Chinese. Fixed text written by people.
"""

from app.claims.schema import Claim
from app.rules.engine import Fact

Texts = dict[str, str]
LANGUAGES = ("en", "ms", "zh")

STATUS_LABELS: dict[str, Texts] = {
    "supported": {"en": "Supported", "ms": "Disokong", "zh": "已证实"},
    "contradicted": {"en": "Contradicted", "ms": "Bercanggah", "zh": "相矛盾"},
    "flagged": {"en": "Flagged", "ms": "Ditanda", "zh": "已标记"},
    "unverifiable": {"en": "Unverifiable", "ms": "Tidak dapat disahkan", "zh": "无法核实"},
}

# {0} is the claim's first argument, {1} its second.
_MEANINGS: dict[str, Texts] = {
    "represents_institution": {"en": "Says it is {0}", "ms": "Mengaku sebagai {0}", "zh": "自称是{0}"},
    "agent_of_institution": {"en": "Says it acts for {0}", "ms": "Mengaku bertindak bagi pihak {0}", "zh": "自称代表{0}办理"},
    "payee_name": {"en": "Pay to {0}", "ms": "Bayar kepada {0}", "zh": "收款人：{0}"},
    "payee_account": {"en": "Pay into account {0}", "ms": "Bayar ke akaun {0}", "zh": "收款账户：{0}"},
    "payee_bank": {"en": "Bank: {0}", "ms": "Bank: {0}", "zh": "开户行：{0}"},
    "amount": {"en": "Amount: {1} {0}", "ms": "Jumlah: {1} {0}", "zh": "金额：{1} {0}"},
    "due": {"en": "Due: {0}", "ms": "Tarikh akhir: {0}", "zh": "截止日期：{0}"},
    "fee_discount": {"en": "Offers the fee for less", "ms": "Menawarkan yuran yang lebih murah", "zh": "提供学费优惠"},
    "pays_via_third_party": {
        "en": "The money goes to someone else",
        "ms": "Wang pergi kepada pihak lain",
        "zh": "款项付给其他人",
    },
    "deadline_pressure": {"en": "Pressure to pay fast", "ms": "Desakan untuk bayar segera", "zh": "催促尽快付款"},
    "threat": {"en": "Threat: {0}", "ms": "Ugutan: {0}", "zh": "威胁：{0}"},
    "secrecy_request": {"en": "Asks you to keep it secret", "ms": "Meminta anda merahsiakannya", "zh": "要求保密"},
    "account_change_notice": {"en": "Says the account has changed", "ms": "Mengatakan akaun telah bertukar", "zh": "称账户已变更"},
}

_POLICIES: dict[str, Texts] = {
    "no_payment_agents": {"en": "does not use payment agents", "ms": "tidak menggunakan ejen pembayaran", "zh": "不使用缴费代理"},
    "no_third_party_discounts": {
        "en": "offers no discounts through third parties",
        "ms": "tidak menawarkan diskaun melalui pihak ketiga",
        "zh": "不通过第三方提供折扣",
    },
    "never_threatens_visa": {"en": "never threatens a student's visa", "ms": "tidak pernah mengugut visa pelajar", "zh": "从不以签证相威胁"},
}
_PATTERNS: dict[str, Texts] = {
    "third_party_fee_discount": {
        "en": "A discount for paying a third party is a known scam pattern",
        "ms": "Diskaun untuk membayar pihak ketiga ialah corak penipuan yang diketahui",
        "zh": "向第三方付款可享折扣是已知的诈骗手法",
    },
    "deadline_pressure": {"en": "Pressure to pay fast is a known scam pattern", "ms": "Desakan bayar segera ialah corak penipuan yang diketahui", "zh": "催促尽快付款是已知的诈骗手法"},
    "visa_threat": {"en": "A visa threat is a known scam pattern", "ms": "Ugutan visa ialah corak penipuan yang diketahui", "zh": "以签证相威胁是已知的诈骗手法"},
    "secrecy_request": {"en": "A request for secrecy is a known scam pattern", "ms": "Permintaan kerahsiaan ialah corak penipuan yang diketahui", "zh": "要求保密是已知的诈骗手法"},
}
_FACTS: dict[str, Texts] = {
    "registered_institution": {"en": "{0} is a registered institution", "ms": "{0} ialah institusi berdaftar", "zh": "{0}是已登记的机构"},
    "official_account": {"en": "{0}'s registered account ends in {tail}", "ms": "Akaun berdaftar {0} berakhir dengan {tail}", "zh": "{0}登记的账户尾号为 {tail}"},
    "official_channel": {"en": "{0} takes payment only by its {1}", "ms": "{0} hanya menerima bayaran melalui {1}", "zh": "{0}只通过其{1}收款"},
    "paid_before": {"en": "You paid {0} before, into the account ending in {tail}", "ms": "Anda pernah membayar {0}, ke akaun berakhir {tail}", "zh": "您以前向{0}付过款，账户尾号为 {tail}"},
}
_SAYS = {"en": "The message says: {meaning} (“{source}”).", "ms": "Mesej itu menyatakan: {meaning} (“{source}”).", "zh": "消息声称：{meaning}（“{source}”）。"}
_FROM = {"en": "{fact} (source: {source}).", "ms": "{fact} (sumber: {source}).", "zh": "{fact}（来源：{source}）。"}
_RULE = {"en": "Rule {id}: {text}", "ms": "Peraturan {id}: {text}", "zh": "规则 {id}：{text}"}
_POLICY_SAYS = {"en": "{0}'s policy says it {1}", "ms": "Dasar {0} menyatakan ia {1}", "zh": "{0}的政策规定其{1}"}


def meaning(claim: Claim, short_name: str | None = None) -> Texts:
    """What a claim asserts, in a few plain words. `short_name` replaces a long institution name."""
    values = [*claim.args.values(), "", ""]
    if short_name:
        values[0] = short_name
    return {language: text.format(*values) for language, text in _MEANINGS[claim.type].items()}


def _short(name: str) -> str:
    """A long institution name by its initials ("SPIU"); anything else unchanged."""
    words_in_name = name.split()
    initials = "".join(word[0] for word in words_in_name if word[:1].isupper())
    return initials if len(words_in_name) >= 3 and len(initials) >= 3 else name


def fact_words(fact: Fact) -> Texts:
    """What a trusted fact says."""
    predicate, *values = fact.atom
    values = [_short(values[0]), *values[1:]] if values else values
    if predicate == "policy":
        return {language: _POLICY_SAYS[language].format(values[0], _POLICIES[values[1]][language]) for language in LANGUAGES}
    if predicate == "known_scam_pattern":
        return _PATTERNS[values[0]]
    tail = values[-1][-4:] if values else ""
    return {language: text.format(*values, tail=tail) for language, text in _FACTS[predicate].items()}


def says(claim: Claim, short_name: str | None = None) -> Texts:
    said = meaning(claim, short_name)
    return {language: _SAYS[language].format(meaning=said[language], source=claim.source) for language in LANGUAGES}


def from_source(fact: Fact) -> Texts:
    words = fact_words(fact)
    return {language: _FROM[language].format(fact=words[language], source=fact.source) for language in LANGUAGES}


def rule_line(rule_id: str, text: Texts) -> Texts:
    return {language: _RULE[language].format(id=rule_id, text=text[language]) for language in LANGUAGES}
