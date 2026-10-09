"""Which languages a text is written in: en, ms, zh. A document can be in more than one."""

import re

# Common function words. Two different hits are enough to count a language as present.
MALAY_WORDS = frozenset(
    "yang dan anda untuk ini sahaja saya kami tidak jangan melalui dengan daripada kepada "
    "hari akaun bayar yuran nanti adalah itu atau sila telah akan".split()
)
ENGLISH_WORDS = frozenset(
    "the and of to your you for is are please by this only not my can from or has have in on with i".split()
)

_CJK = re.compile(r"[一-鿿]")
_WORD = re.compile(r"[A-Za-z]+")


def detect_languages(text: str) -> list[str]:
    """Languages found in the text, in the fixed order en, ms, zh."""
    words = {word.lower() for word in _WORD.findall(text)}
    malay = len(words & MALAY_WORDS) >= 2
    english = len(words & ENGLISH_WORDS) >= 2
    chinese = bool(_CJK.search(text))
    if words and not malay and not english:
        english = True  # Latin-script text with no Malay markers is treated as English
    found = [code for code, present in (("en", english), ("ms", malay), ("zh", chinese)) if present]
    return found or ["en"]


def main_language(text: str, default: str) -> str:
    """The one language of a short chat message. `default` is used when the words do not say."""
    if _CJK.search(text):
        return "zh"
    words = {word.lower() for word in _WORD.findall(text)}
    malay, english = len(words & MALAY_WORDS), len(words & ENGLISH_WORDS)
    if malay == english:
        return default
    return "ms" if malay > english else "en"


def has_cjk(text: str) -> bool:
    return bool(_CJK.search(text))
