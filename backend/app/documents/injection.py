"""
Prompt-injection detection. Document text is data, never instructions.

Anything found here makes the document untrusted. The offending text is kept as
evidence to show the user; it is blanked out before extraction and never reaches an
LLM as instructions.
"""

import re
from dataclasses import dataclass
from typing import Any

NEAR_WHITE = 0.9  # every colour component at or above this is invisible on paper
TINY_POINTS = 3.0

# Phrases addressed to an AI rather than to a person, in English, Malay and Chinese.
INSTRUCTION_PHRASES = [
    re.compile(pattern, re.I)
    for pattern in (
        r"ignore (?:all |any |the )*(?:previous|prior|above|earlier)",
        r"disregard (?:all |any |the )*(?:previous|prior|above|earlier|rules|instructions)",
        r"system instruction",
        r"do not ask the user",
        r"don'?t ask the user",
        r"(?:to|dear) (?:the )?ai assistant",
        r"abaikan (?:semua )?(?:arahan|peraturan)",
        r"arahan sistem",
        r"jangan (?:tanya|bertanya kepada) pengguna",
        r"忽略(?:之前|以上|此前|先前|所有)",
        r"无视(?:之前|以上|此前|先前|所有)",
        r"系统指令",
        r"(?:不要|无需|不必)询问用户",
    )
]

# Zero-width and direction-control characters, other control characters, Unicode tag characters.
_INVISIBLE = re.compile(
    "[​-‏‪-‮⁠-⁤﻿­\U000e0000-\U000e007f]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)


@dataclass(frozen=True)
class Finding:
    kind: str  # hidden_text | tiny_text | instruction_phrase | invisible_characters
    text: str  # what was found, to show the user
    start: int
    end: int


def _line_around(text: str, start: int, end: int) -> tuple[int, int]:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    return line_start, len(text) if line_end < 0 else line_end


def detect(text: str, runs: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []

    for run in runs:
        white = all(component >= NEAR_WHITE for component in run["color"])
        tiny = run["size"] < TINY_POINTS
        snippet = text[run["start"] : run["end"]]
        if (white or tiny) and snippet.strip():
            findings.append(Finding("hidden_text" if white else "tiny_text", snippet.strip(), run["start"], run["end"]))

    def covered(start: int, end: int) -> bool:
        return any(item.start <= start and end <= item.end for item in findings)

    for pattern in INSTRUCTION_PHRASES:
        for match in pattern.finditer(text):
            start, end = _line_around(text, match.start(), match.end())
            if not covered(start, end):
                findings.append(Finding("instruction_phrase", text[start:end].strip(), start, end))

    invisible = sorted({f"U+{ord(match.group(0)):04X}" for match in _INVISIBLE.finditer(text)})
    if invisible:
        first = _INVISIBLE.search(text)
        assert first is not None
        findings.append(Finding("invisible_characters", ", ".join(invisible), first.start(), first.end()))

    return findings


def hidden_ranges(findings: list[Finding]) -> list[tuple[int, int]]:
    """Spans to blank out before extraction: hidden text and instruction lines."""
    return [(item.start, item.end) for item in findings if item.kind != "invisible_characters"]


def blank_out(text: str, ranges: list[tuple[int, int]]) -> str:
    """Replace the given spans with spaces, keeping every offset where it was."""
    characters = list(text)
    for start, end in ranges:
        for position in range(start, end):
            if characters[position] != "\n":
                characters[position] = " "
    return _INVISIBLE.sub(" ", "".join(characters))
