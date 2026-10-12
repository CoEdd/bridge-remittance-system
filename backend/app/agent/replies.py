"""
Reply templates for the scripted driver and for the agent loop's own fixed messages, in
Malay, English and Chinese. Every number is filled in from a tool result; none is written here.
"""

import re
from typing import Any

from app.money import format_amount
from app.policy.reasons import reason

Texts = dict[str, str]

# Investment questions are declined before any driver runs. Bridge never gives investment advice.
INVESTMENT_WORDS = re.compile(
    r"\binvest(?:s|ed|ing|ments?|ors?)?\b|\bstocks?\b|\bcrypto(?:currency|currencies)?\b|\bbitcoin\b"
    r"|\bforex trading\b|\bmutual funds?\b"
    r"|\bsaham\b|\bpelaburan\b|\bmelabur\b|\bkripto\b|\bunit amanah\b"
    r"|投资|股票|炒股|理财|基金|加密货币|比特币",
    re.I,
)

FRAUD_CODES = ("UNTRUSTED_DOCUMENT", "PAYEE_NOT_OFFICIAL", "BANK_DETAILS_CHANGED", "THIRD_PARTY_DISCOUNT", "SCAM_PATTERN")

BLOCKED_TITLE: Texts = {"ms": "Bayaran disekat", "en": "Payment blocked", "zh": "付款已被阻止"}

_ADVICE: dict[str, Texts] = {
    "fraud": {
        "ms": (
            "Bayar hanya ke akaun pada invois rasmi anda atau melalui portal pelajar. Jika ragu-ragu, hubungi pejabat "
            "kewangan menggunakan maklumat di portal rasmi, bukan maklumat dalam mesej ini."
        ),
        "en": (
            "Pay only to the account on your official invoice or through the student portal. If unsure, contact the "
            "finance office using the details on the official portal, not the ones in this message."
        ),
        "zh": "请只向正式账单上的账户付款，或通过学生门户付款。如有疑问，请使用官方门户上的联系方式联系财务处，不要使用这条消息里的联系方式。",
    },
    "MONEY_MULE_PATTERN": {
        "ms": "Jangan pindahkan wang daripada orang yang tidak dikenali. Minta bank anda memulangkannya kepada penghantar.",
        "en": "Do not forward money from strangers. Ask your bank to return it to the sender.",
        "zh": "不要替陌生人转移资金。请让您的银行把这笔钱退回给汇款人。",
    },
    "DAILY_LIMIT": {
        "ms": "Cuba lagi esok, atau bayar jumlah yang lebih kecil.",
        "en": "Try again tomorrow, or pay a smaller amount.",
        "zh": "请明天再试，或支付较小的金额。",
    },
    "INSUFFICIENT_FUNDS": {
        "ms": "Tambah wang ke dompet ini, atau tukar mata wang dahulu.",
        "en": "Add money to this wallet, or convert currency first.",
        "zh": "请先为该钱包充值，或先兑换货币。",
    },
    "NEW_PAYEE_LIMIT": {
        "ms": "Bayaran pertama kepada penerima baharu adalah terhad. Bayar jumlah yang lebih kecil dahulu.",
        "en": "A first payment to a new payee is limited. Pay a smaller amount first.",
        "zh": "首次向新收款方付款有金额限制，请先支付较小的金额。",
    },
    "default": {
        "ms": "Semak butirannya dan cuba lagi.",
        "en": "Check the details and try again.",
        "zh": "请核对信息后重试。",
    },
}

_CATEGORIES: dict[str, Texts] = {
    "rent": {"ms": "Sewa", "en": "Rent", "zh": "房租"},
    "tuition": {"ms": "Yuran pengajian", "en": "Tuition", "zh": "学费"},
    "phone": {"ms": "Telefon", "en": "Phone", "zh": "话费"},
    "groceries": {"ms": "Barangan runcit", "en": "Groceries", "zh": "日用杂货"},
    "eating_out": {"ms": "Makan di luar", "en": "Eating out", "zh": "外出就餐"},
    "transport": {"ms": "Pengangkutan", "en": "Transport", "zh": "交通"},
    "subscriptions": {"ms": "Langganan", "en": "Subscriptions", "zh": "订阅服务"},
    "bill_payment": {"ms": "Bayaran bil", "en": "Bill payment", "zh": "账单付款"},
}


def is_investment_question(text: str) -> bool:
    return bool(INVESTMENT_WORDS.search(text))


def both(texts: Texts, language: str) -> tuple[str, str]:
    """(reply in the student's language, the same reply in English)."""
    return texts[language], texts["en"]


def advice_for(codes: list[str]) -> Texts:
    if "MONEY_MULE_PATTERN" in codes:
        return _ADVICE["MONEY_MULE_PATTERN"]
    if any(code in FRAUD_CODES for code in codes):
        return _ADVICE["fraud"]
    return next((_ADVICE[code] for code in codes if code in _ADVICE), _ADVICE["default"])


_WHY: dict[str, Texts] = {
    "T0": {
        "ms": "Bacaan sahaja. Dijalankan tanpa perlu bertanya.",
        "en": "Reading only. It runs without asking.",
        "zh": "仅读取信息，无需询问即可执行。",
    },
    "T1": {
        "ms": "Cadangan sahaja. Tiada bayaran atau perubahan dibuat.",
        "en": "A suggestion only. Nothing is paid or changed.",
        "zh": "仅为建议，不会付款或更改任何内容。",
    },
    "T2": {
        "ms": "Ia memindahkan wang, jadi ia menunggu pengesahan anda.",
        "en": "It moves money, so it waits for your confirmation.",
        "zh": "涉及资金变动，需要您确认。",
    },
    "T3": {
        "ms": "Ia memerlukan pengesahan anda dan kod sekali guna.",
        "en": "It needs your confirmation and a one-time code.",
        "zh": "需要您确认并输入一次性验证码。",
    },
}
_REFUSED: Texts = {"ms": "Ditolak", "en": "Refused", "zh": "已拒绝"}


def why(tier: str, codes: list[str]) -> Texts:
    """Why a tool call got its tier, in plain words: the policy's own reasons, or the tier's rule."""
    if tier == "REFUSED":
        return {
            language: f"{_REFUSED[language]}: {'; '.join(reason(code).title[language] for code in codes)}."
            for language in ("ms", "en", "zh")
        }
    if codes:
        return {language: " ".join(reason(code).text[language] for code in codes) for language in ("ms", "en", "zh")}
    return _WHY.get(tier, _WHY["T2"])


def investment_declined() -> Texts:
    return reason("INVESTMENT_ADVICE").text


def fallback() -> Texts:
    return {
        "ms": "Dalam mod skrip, saya hanya boleh menjawab soalan demo.",
        "en": "In scripted mode I can only answer the demo questions.",
        "zh": "在脚本模式下，我只能回答演示问题。",
    }


def no_bill() -> Texts:
    return {
        "ms": "Saya tidak menemui bil yang boleh dibayar. Muat naik invois atau tampal mesej bayaran dahulu.",
        "en": "I could not find a bill to pay. Upload an invoice or paste a payment message first.",
        "zh": "我没有找到可以支付的账单。请先上传缴费通知或粘贴付款信息。",
    }


def error_reply() -> Texts:
    return {
        "ms": "Maaf, saya tidak dapat menjawab sekarang. Tiada wang yang dipindahkan. Sila cuba lagi.",
        "en": "Sorry, I cannot answer right now. No money has moved. Please try again.",
        "zh": "抱歉，我暂时无法回答。资金没有任何变动，请稍后再试。",
    }


def too_many_steps() -> Texts:
    return {
        "ms": "Saya berhenti di sini kerana permintaan ini memerlukan terlalu banyak langkah. Tiada wang yang dipindahkan.",
        "en": "I stopped here because this request needed too many steps. No money has moved.",
        "zh": "这个请求需要的步骤过多，我先停在这里。资金没有任何变动。",
    }


def plan_with_conversion(plan: dict[str, Any], quote: dict[str, Any]) -> Texts:
    """The Act 1 reply: not enough CNY, convert once, then pay. The costs are on the approval sheet."""
    send = format_amount(quote["amount_minor"], quote["from_currency"])
    bill = format_amount(plan["bill_amount_minor"], plan["currency"])
    currency = plan["currency"]
    return {
        "ms": f"Baki {currency} tidak cukup. Tukar {send} dahulu, kemudian bayar {bill}.",
        "en": f"Not enough {currency}. Convert {send} first, then pay {bill}.",
        "zh": f"{currency} 余额不足。先兑换 {send}，再支付 {bill}。",
    }


def plan_ready(plan: dict[str, Any], payee: str) -> Texts:
    bill = format_amount(plan["bill_amount_minor"], plan["currency"])
    return {
        "ms": f"Baki {plan['currency']} mencukupi. Bayaran {bill} kepada {payee} sedia untuk kelulusan anda.",
        "en": f"You have enough {plan['currency']}. A payment of {bill} to {payee} is ready for your approval.",
        "zh": f"{plan['currency']} 余额充足。向{payee}支付 {bill} 已准备好，等待您批准。",
    }


def plan_insufficient(plan: dict[str, Any]) -> Texts:
    shortfall = format_amount(plan["shortfall_minor"], plan["currency"])
    source = plan.get("source_currency") or ""
    most = plan.get("affordable")
    if not most:
        return {
            "ms": f"Anda kekurangan {shortfall}, dan baki {source} anda tidak cukup untuk menampungnya.",
            "en": f"You are short by {shortfall}, and your {source} balance cannot cover it.",
            "zh": f"您还差 {shortfall}，而您的 {source} 余额不足以补足。",
        }
    send = format_amount(most["amount_minor"], source)
    receive = format_amount(most["receives_minor"], plan["currency"])
    return {
        "ms": f"Anda kekurangan {shortfall}, dan baki {source} anda tidak cukup. Paling banyak, anda boleh menukar {send} untuk menerima {receive}.",
        "en": f"You are short by {shortfall}, and your {source} balance is not enough. At most you can convert {send} to receive {receive}.",
        "zh": f"您还差 {shortfall}，而您的 {source} 余额不足。您最多可以兑换 {send}，到账 {receive}。",
    }


def payment_prepared(summary: dict[str, Any]) -> Texts:
    amount = format_amount(summary["amount_minor"], summary["currency"])
    payee = summary["payee_name"]
    return {
        "ms": f"Bayaran {amount} kepada {payee} sedia untuk kelulusan anda.",
        "en": f"A payment of {amount} to {payee} is ready for your approval.",
        "zh": f"向{payee}支付 {amount} 已准备好，等待您批准。",
    }


def blocked(codes: list[str]) -> Texts:
    """What Bridge says when a payment is refused. Short: the reasons are shown beside it."""
    if "MONEY_MULE_PATTERN" in codes:
        return {
            "ms": (
                "Saya tidak boleh memindahkan wang ini. Memindahkan wang daripada orang yang tidak dikenali ialah cara pelajar "
                "dipergunakan sebagai keldai wang, dan boleh menyebabkan akaun bank anda ditutup, rekod jenayah serta kehilangan "
                "visa. Pulangkan wang yang tersilap hantar melalui bank anda, bukan ke akaun yang diberikan oleh penghantar."
            ),
            "en": (
                "I cannot forward this money. Forwarding money from strangers is how students get used as money mules, and it "
                "can cost you your bank account, a criminal record and your visa. Return money sent by mistake through your "
                "bank, not to an account the sender names."
            ),
            "zh": "我不能替您转出这笔钱。替陌生人转移资金正是学生被利用成为“钱骡”的方式，可能导致银行账户被关闭、留下犯罪记录并失去签证。误汇的款项应通过您的银行退回，而不是转到对方指定的账户。",
        }
    # The reasons and the advice travel in the "blocked" event; the reply does not repeat them.
    return {
        "ms": "Saya tidak boleh meneruskan bayaran ini. Tiada wang dipindahkan.",
        "en": "I cannot go ahead with this payment. No money was moved.",
        "zh": "我无法继续这笔付款。资金没有任何变动。",
    }


def spending(insights: dict[str, Any]) -> Texts:
    categories = insights["categories"]
    if not categories:
        return {
            "ms": "Tiada perbelanjaan dalam 30 hari lepas.",
            "en": "There was no spending in the last 30 days.",
            "zh": "过去30天没有消费记录。",
        }
    top = categories[0]
    top_amount = format_amount(top["total_minor"], top["currency"])
    movers = [item for item in categories if item["change_pct"] not in (None, 0)]
    mover = max(movers, key=lambda item: abs(item["change_pct"])) if movers else None

    def name(item: dict[str, Any], language: str) -> str:
        return _CATEGORIES.get(item["category"], {}).get(language, item["label"])

    replies = {
        "ms": f"Dalam 30 hari lepas, perbelanjaan terbesar anda ialah {name(top, 'ms')} ({top_amount}).",
        "en": f"In the last 30 days your largest spending was {name(top, 'en')} ({top_amount}).",
        "zh": f"过去30天里，您最大的一项支出是{name(top, 'zh')}（{top_amount}）。",
    }
    if mover:
        percent = abs(mover["change_pct"])
        up = mover["change_pct"] > 0
        replies["ms"] += f" {name(mover, 'ms')} {'naik' if up else 'turun'} {percent}% berbanding 30 hari sebelumnya."
        replies["en"] += f" {name(mover, 'en')} is {'up' if up else 'down'} {percent}% compared with the previous 30 days."
        replies["zh"] += f"{name(mover, 'zh')}比之前30天{'增加' if up else '减少'}了{percent}%。"
    return replies
