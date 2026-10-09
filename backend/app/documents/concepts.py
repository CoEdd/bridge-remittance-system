"""
Risk concepts and the words for them in English, Malay and Chinese.

One fixed, readable list, used in two places: the risk rules look for these concepts in
a document, and the passage search uses them to connect a message in one language to a
knowledge passage in another.
"""

import re

CONCEPTS: dict[str, re.Pattern[str]] = {
    # Someone standing between the student and the payee.
    "agent": re.compile(
        r"\bagents?\b|\bthird[ -]part(?:y|ies)\b|\bthrough us\b|\bon your behalf\b"
        r"|\bejen\b|\bpihak ketiga\b|\bmelalui kami\b|代缴|代付|代理|第三方",
        re.I,
    ),
    "discount": re.compile(
        r"\bdiscounts?\b|\d+\s*%\s*off\b|\bsave\b|\bcheaper\b|\blower price\b"
        r"|\bdiskaun\b|\bjimat\b|\bpotongan\b|优惠|折扣|打折|低价",
        re.I,
    ),
    "urgency": re.compile(
        r"\btoday only\b|\bwithin \d+ (?:hours?|minutes?)\b|\bhari ini sahaja\b|\bdalam (?:masa )?\d+ jam\b"
        r"|\d+\s*小时内|仅限今[天日]",
        re.I,
    ),
    "threat": re.compile(
        r"\bvisa\b|\bdeport(?:ed|ation)?\b|\barrest(?:ed)?\b|\bexpel(?:led)?\b|\bexpulsion\b"
        r"|\bdihantar pulang\b|\bditangkap\b|签证|遣返|拘捕|开除",
        re.I,
    ),
    "secrecy": re.compile(
        r"\bdon'?t tell\b|\bdo not tell\b|\bkeep (?:this|it) (?:a )?secret\b|\bjangan beritahu\b|\brahsiakan\b"
        r"|请勿联系|不要告诉|保密",
        re.I,
    ),
}

# Words that turn a statement around: "we never offer discounts" is not an offer.
NEGATION = re.compile(
    r"\b(?:not|never|no|don'?t|doesn'?t|cannot|won'?t|tidak|tak|bukan|jangan|tiada)\b|不|勿|没有|從不|从不", re.I
)


def concepts_in(text: str) -> set[str]:
    """Every risk concept mentioned in the text, in any of the three languages."""
    return {name for name, pattern in CONCEPTS.items() if pattern.search(text)}
