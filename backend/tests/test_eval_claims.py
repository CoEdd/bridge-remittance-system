"""The claim-check evaluation: the data set is well formed and the arithmetic of the report is right."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from eval.claims import run as evaluation

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"


def row(item_id: str, label: str, lang: str, a: bool, b: bool) -> dict[str, Any]:
    return {
        "id": item_id, "label": label, "lang": lang, "A": a, "B": b, "C": a or b, "category": "test",
        "reason": "Because.", "text": f"Text of {item_id}\nsecond line", "signals": ["SCAM_PATTERN"] if a else [], "rules": ["R2"] if b else [],
    }  # fmt: skip


def test_the_data_set_is_forty_labelled_items_in_three_languages() -> None:
    dev, test = evaluation.load("dev"), evaluation.load("test")

    assert (len(dev), len(test)) == (15, 25)
    assert len({item["id"] for item in [*dev, *test]}) == 40
    assert not {item["text"] for item in dev} & {item["text"] for item in test}  # nothing leaks from test into dev
    for item in [*dev, *test]:
        assert set(item) == {"id", "lang", "kind", "label", "category", "reason", "text"}
        assert item["label"] in ("block", "allow") and item["lang"] in ("en", "ms", "zh") and item["kind"] in ("invoice", "message")
        assert item["reason"].endswith(".") and len(item["text"]) > 40
    assert sum(item["label"] == "block" for item in test) == 13
    assert {item["lang"] for item in test if item["label"] == "block"} == {"en", "ms", "zh"}
    assert {item["lang"] for item in test if item["label"] == "allow"} == {"en", "ms", "zh"}


def test_rates_count_scams_caught_and_legitimate_messages_blocked() -> None:
    rows = [
        row("1", "block", "en", a=True, b=True),
        row("2", "block", "en", a=False, b=True),
        row("3", "block", "ms", a=False, b=False),
        row("4", "allow", "ms", a=True, b=False),
        row("5", "allow", "zh", a=False, b=False),
    ]

    summary = evaluation.summarise(rows)

    assert summary["overall"]["A"] == {"scams": 3, "caught": 1, "legit": 2, "false_blocks": 1}
    assert summary["overall"]["B"] == {"scams": 3, "caught": 2, "legit": 2, "false_blocks": 0}
    assert summary["overall"]["C"] == {"scams": 3, "caught": 2, "legit": 2, "false_blocks": 1}
    assert summary["by_language"]["en"]["A"] == {"scams": 2, "caught": 1, "legit": 0, "false_blocks": 0}
    assert summary["misses"] == {"A": ["2", "3", "4"], "B": ["3"], "C": ["3", "4"]}


@pytest.mark.parametrize(
    "rows, opening",
    [
        ([row("1", "block", "en", a=False, b=True), row("2", "allow", "en", a=False, b=False)], "Adding the claim check catches 1 more of the 1 scams than the keyword rules alone, with no extra"),
        ([row("1", "block", "en", a=False, b=True), row("2", "allow", "en", a=False, b=True)], "Adding the claim check catches 1 more of the 1 scams than the keyword rules alone, but it also blocks 1 more"),
        ([row("1", "block", "en", a=True, b=True), row("2", "allow", "en", a=False, b=False)], "On this split the claim check does not beat the keyword rules alone: both catch the same"),
        ([row("1", "block", "en", a=True, b=False), row("2", "allow", "en", a=False, b=True)], "On this split the claim check does not beat the keyword rules alone: it catches no additional scam and blocks 1 more"),
    ],
)
def test_the_verdict_says_plainly_whether_the_claim_check_helps(rows: list[dict[str, Any]], opening: str) -> None:
    assert evaluation.verdict(evaluation.summarise(rows)).startswith(opening)


def test_the_report_lists_every_miss_with_its_text() -> None:
    rows = [row("S1", "block", "ms", a=False, b=False), row("L1", "allow", "zh", a=True, b=False)]
    meta = {"split": "test", "items": 2, "scams": 1, "legit": 1, "model": "m", "date": "2026-10-12", "llm_calls": 2, "live_items": 2}

    text = evaluation.report(rows, evaluation.summarise(rows), meta)

    assert text.startswith("# Neuro-symbolic claim check: evaluation\n\nThe LLM turns a message into a fixed set of claims")
    assert "| C. Both combined (what Bridge uses) | 0 / 1 (0%) | 1 / 1 (100%) |" in text
    assert "## Every miss of C (Both combined (what Bridge uses)): 2" in text
    assert "**S1** (Malay, test). Scam not caught. Because. Found: nothing." in text
    assert "**L1** (Chinese, test). Legitimate message blocked. Because. Found: SCAM_PATTERN." in text
    assert "> Text of S1\n> second line" in text
    assert "not yet reviewed by a person" in text


def test_the_evaluation_refuses_to_run_without_live_mode(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["run"])  # scripted mode, as every test

    assert evaluation.main() == 1
    assert "needs live mode" in capsys.readouterr().out


def test_the_published_numbers_are_the_ones_the_app_shows(client: TestClient) -> None:
    results = json.loads(evaluation.RESULTS_FILE.read_text(encoding="utf-8"))
    shown = client.get("/security/claim-check").json()["evaluation"]

    assert shown == results
    assert (results["split"], results["items"], results["live_items"]) == ("test", 25, 25)
    # The numbers follow from the recorded misses: nothing typed in by hand.
    for arm, numbers in results["overall"].items():
        missed_scams = [item for item in results["misses"][arm] if item in SCAM_IDS]
        assert numbers["caught"] == numbers["scams"] - len(missed_scams)
        assert numbers["false_blocks"] == len(results["misses"][arm]) - len(missed_scams)
    report = DOCS / "claim-check-eval.md"
    if report.exists():  # docs/ is mounted by `make test`
        text = report.read_text(encoding="utf-8")
        for arm, name in results["arms"].items():
            numbers = results["overall"][arm]
            assert f"| {arm}. {name} | {numbers['caught']} / {numbers['scams']} " in text
        assert results["verdict"] in text


SCAM_IDS = {item["id"] for item in evaluation.load("test") if item["label"] == "block"}
