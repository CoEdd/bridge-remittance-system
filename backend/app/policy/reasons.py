"""
Every reason the policy engine can give, in English, Malay and Chinese.

This table is fixed text written by people. Nothing here is generated at run time.
"""

from dataclasses import dataclass
from typing import Literal

Severity = Literal["info", "warn", "block"]
Texts = dict[str, str]  # keyed by language: en, ms, zh


@dataclass(frozen=True)
class Reason:
    code: str
    severity: Severity
    title: Texts
    text: Texts
    # Extra steps this reason adds before the action may run ("otp", "cooling_off").
    requires: tuple[str, ...] = ()


def _reason(
    code: str,
    severity: Severity,
    en: tuple[str, str],
    ms: tuple[str, str],
    zh: tuple[str, str],
    requires: tuple[str, ...] = (),
) -> Reason:
    return Reason(
        code=code,
        severity=severity,
        title={"en": en[0], "ms": ms[0], "zh": zh[0]},
        text={"en": en[1], "ms": ms[1], "zh": zh[1]},
        requires=requires,
    )


_ALL = [
    # ---- Integrity ----
    _reason(
        "UNKNOWN_TOOL",
        "block",
        ("Unknown action", "Bridge does not recognise this action, so it was refused."),
        ("Tindakan tidak dikenali", "Bridge tidak mengenali tindakan ini, jadi ia ditolak."),
        ("未知操作", "Bridge 无法识别该操作，因此已拒绝。"),
    ),
    _reason(
        "INVALID_ARGUMENTS",
        "block",
        ("Request is incomplete", "The request is missing details or contains values that are not valid."),
        ("Permintaan tidak lengkap", "Permintaan ini tidak lengkap atau mengandungi nilai yang tidak sah."),
        ("请求不完整", "请求缺少必要信息，或包含无效的内容。"),
    ),
    _reason(
        "BILL_NOT_PAYABLE",
        "block",
        ("Bill cannot be paid", "This bill is not open. It may already be paid or cancelled."),
        ("Bil tidak boleh dibayar", "Bil ini tidak lagi terbuka. Mungkin ia sudah dibayar atau dibatalkan."),
        ("账单无法支付", "该账单不在待支付状态，可能已经支付或已取消。"),
    ),
    _reason(
        "ARGUMENT_MISMATCH",
        "block",
        (
            "Request does not match the bill",
            "The amount, currency, payee or account in the request differs from the verified bill. "
            "Bridge only pays what the bill says.",
        ),
        (
            "Permintaan tidak sepadan dengan bil",
            "Jumlah, mata wang, penerima atau akaun dalam permintaan berbeza daripada bil yang disahkan. "
            "Bridge hanya membayar mengikut bil.",
        ),
        ("请求与账单不符", "请求中的金额、币种、收款方或账户与已核实的账单不一致。Bridge 只按账单内容付款。"),
    ),
    _reason(
        "UNSUPPORTED_CONVERSION",
        "block",
        ("Conversion not available", "This sandbox converts MYR to CNY only, through one simulated transfer service."),
        (
            "Penukaran tidak tersedia",
            "Persekitaran ujian ini hanya menukar MYR kepada CNY, melalui satu perkhidmatan pemindahan simulasi.",
        ),
        ("暂不支持该兑换", "本沙盒仅支持通过一家模拟汇款服务将 MYR 兑换为 CNY。"),
    ),
    _reason(
        "QUOTE_CHANGED",
        "block",
        ("Cost changed after approval", "The cost changed after you approved it. No money moved. Please review it again."),
        (
            "Kos berubah selepas kelulusan",
            "Kos berubah selepas anda meluluskannya. Tiada wang dipindahkan. Sila semak semula.",
        ),
        ("批准后费用发生变化", "在您批准之后费用发生了变化。资金没有变动，请重新确认。"),
    ),
    # ---- Fraud ----
    _reason(
        "UNTRUSTED_DOCUMENT",
        "block",
        ("Document is not trusted", "This payment request comes from a document Bridge could not verify."),
        ("Dokumen tidak dipercayai", "Permintaan bayaran ini datang daripada dokumen yang tidak dapat disahkan oleh Bridge."),
        ("文件不可信", "这笔付款请求来自 Bridge 无法核实的文件。"),
    ),
    _reason(
        "PAYEE_NOT_OFFICIAL",
        "block",
        ("Not the official account", "This account is not the one the institution has registered for payments."),
        ("Bukan akaun rasmi", "Akaun ini bukan akaun yang didaftarkan oleh institusi tersebut untuk menerima bayaran."),
        ("不是官方账户", "该账户不是该机构登记的官方收款账户。"),
    ),
    _reason(
        "BANK_DETAILS_CHANGED",
        "block",
        ("Bank details changed", "The bank details differ from the ones you paid before. This is a common sign of invoice fraud."),
        (
            "Butiran bank berubah",
            "Butiran bank berbeza daripada yang anda bayar sebelum ini. Ini tanda biasa penipuan invois.",
        ),
        ("银行信息已变更", "银行信息与您以前付款时使用的不同。这是发票诈骗的常见迹象。"),
    ),
    _reason(
        "THIRD_PARTY_DISCOUNT",
        "block",
        ("Discount through a third party", "The institution's own policy says it never offers discounts through agents."),
        (
            "Diskaun melalui pihak ketiga",
            "Dasar institusi itu sendiri menyatakan bahawa ia tidak pernah menawarkan diskaun melalui ejen.",
        ),
        ("第三方折扣", "该机构的政策明确规定，从不通过代理提供折扣。"),
    ),
    _reason(
        "SCAM_PATTERN",
        "block",
        ("Matches a known scam pattern", "Pressure to pay today and a request for secrecy match known fee-scam patterns."),
        (
            "Sepadan dengan corak penipuan",
            "Desakan untuk membayar hari ini dan permintaan supaya dirahsiakan sepadan dengan corak penipuan yuran.",
        ),
        ("符合已知诈骗特征", "催促当天付款并要求保密，符合已知的学费诈骗特征。"),
    ),
    _reason(
        "MONEY_MULE_PATTERN",
        "block",
        (
            "Looks like money-mule recruitment",
            "Forwarding money a stranger sent you is how students get used as money mules. "
            "Return it through your bank, never to an account the sender names.",
        ),
        (
            "Menyerupai perekrutan keldai wang",
            "Memindahkan wang yang dihantar oleh orang tidak dikenali ialah cara pelajar dipergunakan sebagai keldai wang. "
            "Pulangkan wang itu melalui bank anda, bukan ke akaun yang ditentukan oleh penghantar.",
        ),
        ("疑似招募“钱骡”", "替陌生人转走其汇给您的钱，正是学生被利用成为“钱骡”的方式。请通过您的银行退回，不要转到对方指定的账户。"),
    ),
    # ---- Limits and funds ----
    _reason(
        "DAILY_LIMIT",
        "block",
        ("Daily limit reached", "With this payment, today's payments to other people would exceed your daily limit."),
        (
            "Had harian dicapai",
            "Dengan bayaran ini, jumlah bayaran kepada pihak lain hari ini akan melebihi had harian anda.",
        ),
        ("超出每日限额", "加上这笔付款，您今天向他人付款的总额将超过每日限额。"),
    ),
    _reason(
        "INSUFFICIENT_FUNDS",
        "block",
        ("Not enough money", "The wallet does not hold enough for this amount and its fee."),
        ("Baki tidak mencukupi", "Baki dompet tidak mencukupi untuk jumlah ini dan yurannya."),
        ("余额不足", "钱包余额不足以支付这笔金额及其手续费。"),
    ),
    _reason(
        "NEW_PAYEE_LIMIT",
        "block",
        ("Too much for a new payee", "A first payment to a new payee cannot exceed your new-payee limit."),
        (
            "Melebihi had penerima baharu",
            "Bayaran pertama kepada penerima baharu tidak boleh melebihi had penerima baharu anda.",
        ),
        ("超出新收款方限额", "首次向新收款方付款，金额不能超过新收款方限额。"),
    ),
    # ---- Tiering (these raise the tier; they do not block) ----
    _reason(
        "OVER_TXN_LIMIT",
        "info",
        (
            "Above your per-payment limit",
            "A one-time code is needed because this is above your per-payment limit, counting today's related actions.",
        ),
        (
            "Melebihi had setiap bayaran",
            "Kod sekali guna diperlukan kerana jumlah ini melebihi had setiap bayaran anda, "
            "termasuk tindakan berkaitan pada hari ini.",
        ),
        ("超出单笔限额", "该金额（含今日相关操作）超过您的单笔限额，需要输入一次性验证码。"),
        requires=("otp",),
    ),
    _reason(
        "NEW_PAYEE",
        "info",
        (
            "First payment to this payee",
            "A first payment needs a one-time code and a short wait, so you can still cancel.",
        ),
        (
            "Bayaran pertama kepada penerima ini",
            "Bayaran pertama memerlukan kod sekali guna dan tempoh menunggu yang singkat, supaya anda masih boleh membatalkannya.",
        ),
        ("首次向该收款方付款", "首次付款需要一次性验证码，并设有短暂的等待期，以便您仍可取消。"),
        requires=("otp", "cooling_off"),
    ),
    _reason(
        "PAYEE_ADDITION",
        "info",
        ("Adding a new payee", "Adding a payee needs a one-time code and a short wait."),
        ("Menambah penerima baharu", "Menambah penerima memerlukan kod sekali guna dan tempoh menunggu yang singkat."),
        ("添加新收款方", "添加收款方需要一次性验证码，并设有短暂的等待期。"),
        requires=("otp", "cooling_off"),
    ),
    # ---- For the agent layer (step 6) ----
    _reason(
        "INVESTMENT_ADVICE",
        "block",
        ("No investment advice", "Bridge does not give investment advice. It can help you plan and make payments."),
        (
            "Tiada nasihat pelaburan",
            "Bridge tidak memberikan nasihat pelaburan. Bridge boleh membantu anda merancang dan membuat bayaran.",
        ),
        ("不提供投资建议", "Bridge 不提供投资建议，但可以帮助您规划和完成付款。"),
    ),
]

REASONS: dict[str, Reason] = {reason.code: reason for reason in _ALL}

# Risk signals a document can carry. Each one refuses a payment (step 5 computes them).
DOCUMENT_RISK_SIGNALS = ("PAYEE_NOT_OFFICIAL", "BANK_DETAILS_CHANGED", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN")


def reason(code: str) -> Reason:
    return REASONS[code]
