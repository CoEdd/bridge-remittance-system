"""
The rules of the claim check, written as data. This is the symbolic side: no LLM here.

How to read a rule: WHEN every line holds, THEN the conclusion follows.
- ("agent_of_institution", "?i") is a claim found in the document: "?i" stands for any institution.
- ("policy", "?i", "no_payment_agents") is a fact we trust: the same institution's own policy.
- Either(...) means at least one of the lines; Not(...) means we hold no such fact;
  Differ("?a", "?old") means the two values are not the same.

`raises` is the reason the policy engine then gives. A rule can only add caution:
"block" refuses the payment, "warn" forces a one-time code and a cooling-off wait.
"""

from dataclasses import dataclass

from app.rules.engine import Atom, Condition, Differ, Either, Not

Texts = dict[str, str]  # keyed by language: en, ms, zh

SPEAKS_FOR = Either((("represents_institution", "?i"), ("agent_of_institution", "?i")))
PRESSURE = Either((("deadline_pressure",), ("secrecy_request",)))
# Any earlier doubt about who is being paid.
PAYEE_DOUBT = Either(
    (
        ("payee_not_official", "?i", "?a"),
        ("account_changed", "?n", "?a"),
        ("discount_via_third_party",),
        ("unverifiable_payee", "?a"),
    )
)


@dataclass(frozen=True)
class CoreRule:
    id: str
    severity: str  # block | warn
    raises: str  # the policy reason code this conclusion adds
    title: Texts
    text: Texts
    when: tuple[Condition, ...]
    then: Atom
    marks: str = "contradicted"  # what the claims it uses are then called


CORE_RULES: tuple[CoreRule, ...] = (
    CoreRule(
        id="R1",
        severity="block",
        raises="PAYEE_NOT_OFFICIAL",
        title={
            "en": "Payee is not the official account",
            "ms": "Penerima bukan akaun rasmi",
            "zh": "收款账户不是官方账户",
        },
        text={
            "en": "The sender speaks for a registered institution, but the account is not that institution's registered account.",
            "ms": "Pengirim mewakili institusi berdaftar, tetapi akaun itu bukan akaun berdaftar institusi tersebut.",
            "zh": "对方以注册机构的名义来信，但收款账户并非该机构登记的账户。",
        },
        when=(
            SPEAKS_FOR,
            ("registered_institution", "?i"),
            ("official_account", "?i", "?official"),
            ("payee_account", "?a"),
            Not(("official_account", "?i", "?a")),
        ),
        then=("payee_not_official", "?i", "?a"),
    ),
    CoreRule(
        id="R2",
        severity="block",
        raises="THIRD_PARTY_DISCOUNT",
        title={
            "en": "Agent claim contradicted by policy",
            "ms": "Dakwaan ejen bercanggah dengan dasar",
            "zh": "代理身份与机构政策相矛盾",
        },
        text={
            "en": "An agent claim contradicted by the institution's own policy blocks the payment.",
            "ms": "Dakwaan sebagai ejen yang bercanggah dengan dasar institusi itu sendiri menyekat bayaran.",
            "zh": "自称代理却与该机构自身政策相矛盾，付款将被阻止。",
        },
        when=(("agent_of_institution", "?i"), ("policy", "?i", "no_payment_agents")),
        then=("agent_contradicted", "?i"),
    ),
    CoreRule(
        id="R3",
        severity="block",
        raises="THIRD_PARTY_DISCOUNT",
        title={
            "en": "Discount contradicted by policy",
            "ms": "Diskaun bercanggah dengan dasar",
            "zh": "折扣与机构政策相矛盾",
        },
        text={
            "en": "A fee discount offered in the institution's name, when its policy offers none through third parties, blocks the payment.",
            "ms": "Diskaun yuran atas nama institusi, sedangkan dasarnya tidak menawarkan diskaun melalui pihak ketiga, menyekat bayaran.",
            "zh": "以机构名义提供学费折扣，而该机构政策不通过第三方提供折扣，付款将被阻止。",
        },
        when=(("fee_discount",), SPEAKS_FOR, ("policy", "?i", "no_third_party_discounts")),
        then=("discount_contradicted", "?i"),
    ),
    CoreRule(
        id="R4",
        severity="block",
        raises="THIRD_PARTY_DISCOUNT",
        title={
            "en": "Discount for paying a third party",
            "ms": "Diskaun untuk membayar pihak ketiga",
            "zh": "向第三方付款可享折扣",
        },
        text={
            "en": "A fee discount for paying someone other than the institution is a known scam pattern, whatever the institution.",
            "ms": "Diskaun yuran untuk membayar pihak selain institusi ialah corak penipuan yang diketahui, tidak kira institusi mana.",
            "zh": "向机构以外的人付款即可享受学费折扣，是已知的诈骗手法，与哪家机构无关。",
        },
        when=(("fee_discount",), ("pays_via_third_party",), ("known_scam_pattern", "third_party_fee_discount")),
        then=("discount_via_third_party",),
    ),
    CoreRule(
        id="R5",
        severity="block",
        raises="BANK_DETAILS_CHANGED",
        title={
            "en": "Account differs from the one paid before",
            "ms": "Akaun berbeza daripada yang pernah dibayar",
            "zh": "账户与以往付款的账户不同",
        },
        text={
            "en": "A payee you have paid before, now with a different account, blocks the payment.",
            "ms": "Penerima yang pernah anda bayar, kini dengan akaun yang berbeza, menyekat bayaran.",
            "zh": "您以前付过款的收款方，现在换了账户，付款将被阻止。",
        },
        when=(
            ("payee_name", "?n"),
            ("paid_before", "?n", "?old"),
            ("payee_account", "?a"),
            Differ("?a", "?old"),
            Not(("paid_before", "?n", "?a")),
            Not(("official_account", "?n", "?a")),
        ),
        then=("account_changed", "?n", "?a"),
    ),
    CoreRule(
        id="R6",
        severity="block",
        raises="SCAM_PATTERN",
        title={
            "en": "Visa threat contradicted by policy",
            "ms": "Ugutan visa bercanggah dengan dasar",
            "zh": "签证威胁与机构政策相矛盾",
        },
        text={
            "en": "A visa threat in the institution's name, when its policy says it never makes one, blocks the payment.",
            "ms": "Ugutan visa atas nama institusi, sedangkan dasarnya menyatakan ia tidak pernah berbuat demikian, menyekat bayaran.",
            "zh": "以机构名义威胁签证，而该机构政策明确从不如此，付款将被阻止。",
        },
        when=(("threat", "visa"), SPEAKS_FOR, ("policy", "?i", "never_threatens_visa")),
        then=("threat_contradicted", "?i"),
    ),
    CoreRule(
        id="R7",
        severity="block",
        raises="SCAM_PATTERN",
        title={
            "en": "Pressure or secrecy with a doubtful payee",
            "ms": "Desakan atau kerahsiaan dengan penerima yang diragui",
            "zh": "催促或保密，且收款方存疑",
        },
        text={
            "en": "Pressure to pay fast, or a request for secrecy, together with a doubt about the payee blocks the payment.",
            "ms": "Desakan untuk membayar segera, atau permintaan supaya dirahsiakan, bersama keraguan tentang penerima menyekat bayaran.",
            "zh": "催促尽快付款或要求保密，同时收款方存疑，付款将被阻止。",
        },
        when=(PRESSURE, PAYEE_DOUBT),
        then=("pressure_with_doubt",),
        marks="flagged",
    ),
    CoreRule(
        id="R8",
        severity="warn",
        raises="NEW_PAYEE",
        title={
            "en": "Payee cannot be verified",
            "ms": "Penerima tidak dapat disahkan",
            "zh": "无法核实收款方",
        },
        text={
            "en": "An unknown account with no registered institution behind it needs a one-time code and a waiting period.",
            "ms": "Akaun yang tidak dikenali tanpa institusi berdaftar di belakangnya memerlukan kod sekali guna dan tempoh menunggu.",
            "zh": "账户未知且背后没有注册机构，需要一次性验证码和等待期。",
        },
        when=(
            ("payee_account", "?a"),
            Not(("official_account", "_", "?a")),
            Not(("paid_before", "_", "?a")),
            Either((("represents_institution", "?x"), ("agent_of_institution", "?x"), ("payee_name", "?x"))),
            Not(("registered_institution", "?x")),
        ),
        then=("unverifiable_payee", "?a"),
    ),
)

RULES_BY_ID = {rule.id: rule for rule in CORE_RULES}


@dataclass(frozen=True)
class SupportRule:
    """A claim that matches something we trust. Changes no verdict; it marks the claim Supported."""

    id: str
    when: tuple[Condition, ...]
    then: Atom


SUPPORT_RULES: tuple[SupportRule, ...] = (
    SupportRule("S1", (("payee_account", "?a"), ("official_account", "?i", "?a")), ("account_is_official", "?i", "?a")),
    SupportRule("S2", (("payee_account", "?a"), ("paid_before", "?n", "?a")), ("account_paid_before", "?n", "?a")),
    SupportRule(
        "S3",
        (("payee_name", "?n"), ("payee_account", "?a"), Either((("paid_before", "?n", "?a"), ("official_account", "?n", "?a")))),
        ("payee_known", "?n", "?a"),
    ),
    SupportRule(
        "S4",
        (("represents_institution", "?i"), ("payee_account", "?a"), ("official_account", "?i", "?a")),
        ("institution_pays_itself", "?i", "?a"),
    ),
)
