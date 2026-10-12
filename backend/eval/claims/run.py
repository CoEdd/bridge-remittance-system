"""
make eval-claims: measure the neuro-symbolic claim check on the evaluation set.

Each item is read three ways:
  A  the keyword risk rules alone (step 5),
  B  the claim check alone (Claude extracts the claims, the rules judge them),
  C  both combined: a block from either one. This is what Bridge uses.

Live mode only: B needs Claude. Every item runs in its own isolated copy of the
database. The test split is never used for tuning; `--split dev` is for that.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import documents, llm
from app.config import effective_agent_mode
from app.documents.reader import read_message
from app.redteam import isolated_copy

HERE = Path(__file__).resolve().parent
RESULTS_FILE = HERE / "results.json"
REPORT_FILE = HERE.parent.parent / "docs" / "claim-check-eval.md"
ARMS = {
    "A": "Keyword rules only",
    "B": "Claim check only",
    "C": "Both combined (what Bridge uses)",
}
LANGUAGES = {"en": "English", "ms": "Malay", "zh": "Chinese"}


def load(split: str) -> list[dict[str, Any]]:
    lines = (HERE / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def judge_item(item: dict[str, Any]) -> dict[str, Any]:
    """Read one item with both layers and say what each would do."""
    with isolated_copy() as box:
        document = documents.ingest(
            box.session,
            box.user,
            filename=item["id"],
            kind=item["kind"],
            read=read_message(item["text"]),
            source="evaluation",
            passages=box.passages,
            scripted=True,  # the keyword layer is the scripted one: fixed patterns, no LLM
            claims_live=True,  # the claim check gets its claims from Claude
        )
        check = document.claim_check
        keyword = document.trust_flag == "untrusted" or bool(documents.policy_signals(document))
        claims = bool(documents.claim_blocks(document))
        return {
            **item,
            "A": keyword,
            "B": claims,
            "C": keyword or claims,
            "origin": check["origin"],
            "signals": [signal["code"] for signal in documents.policy_signals(document)],
            "rules": [conclusion["rule"] for conclusion in check["conclusions"]],
            "claims": [f"{claim['type']}:{claim['status']}" for claim in check["claims"]],
        }


def rates(rows: list[dict[str, Any]], arm: str) -> dict[str, int]:
    scams = [row for row in rows if row["label"] == "block"]
    legit = [row for row in rows if row["label"] == "allow"]
    return {
        "scams": len(scams),
        "caught": sum(row[arm] for row in scams),
        "legit": len(legit),
        "false_blocks": sum(row[arm] for row in legit),
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Scam catch rate and false-block rate of each arm, overall and per language."""
    return {
        "overall": {arm: rates(rows, arm) for arm in ARMS},
        "by_language": {
            language: {arm: rates([row for row in rows if row["lang"] == language], arm) for arm in ARMS}
            for language in LANGUAGES
        },
        "misses": {arm: [row["id"] for row in rows if row[arm] != (row["label"] == "block")] for arm in ARMS},
    }


def _share(part: int, whole: int) -> str:
    return f"{part} / {whole} ({round(100 * part / whole)}%)" if whole else "none"


def _table(by_arm: dict[str, dict[str, int]]) -> list[str]:
    lines = ["| | Scams caught | Legitimate blocked by mistake |", "|---|---|---|"]
    for arm, name in ARMS.items():
        numbers = by_arm[arm]
        lines.append(f"| {arm}. {name} | {_share(numbers['caught'], numbers['scams'])} | {_share(numbers['false_blocks'], numbers['legit'])} |")
    return lines


def verdict(summary: dict[str, Any]) -> str:
    """One plain sentence: does the combination beat the keyword rules alone on this split?"""
    alone, both = summary["overall"]["A"], summary["overall"]["C"]
    more_caught = both["caught"] - alone["caught"]
    more_false = both["false_blocks"] - alone["false_blocks"]
    if more_caught > 0 and more_false <= 0:
        return f"Adding the claim check catches {more_caught} more of the {both['scams']} scams than the keyword rules alone, with no extra legitimate message blocked."
    if more_caught > 0:
        return f"Adding the claim check catches {more_caught} more of the {both['scams']} scams than the keyword rules alone, but it also blocks {more_false} more legitimate message(s) by mistake."
    if more_false > 0:
        return f"On this split the claim check does not beat the keyword rules alone: it catches no additional scam and blocks {more_false} more legitimate message(s) by mistake."
    return "On this split the claim check does not beat the keyword rules alone: both catch the same scams and block the same legitimate messages."


def report(rows: list[dict[str, Any]], summary: dict[str, Any], meta: dict[str, Any]) -> str:
    by_id = {row["id"]: row for row in rows}
    lines = [
        "# Neuro-symbolic claim check: evaluation",
        "",
        "The LLM turns a message into a fixed set of claims; fixed rules judge them against facts we trust.",
        "This file is written by `make eval-claims` and holds its real results.",
        "",
        f"- Split: **{meta['split']}** ({meta['items']} items: {meta['scams']} scams, {meta['legit']} legitimate). Never used for tuning.",
        f"- Model: `{meta['model']}` · Date: {meta['date']} · LLM calls: {meta['llm_calls']}",
        f"- Claims extracted live for {meta['live_items']} of {meta['items']} items.",
        "- Read with care: a small set, written by the same author as the rules and not yet reviewed by a person.",
        "- How the set was made: `backend/eval/claims/DATA_CARD.md`.",
        "",
        f"**Result.** {verdict(summary)}",
        "",
        "## Overall",
        "",
        *_table(summary["overall"]),
        "",
    ]
    for language, name in LANGUAGES.items():
        lines += [f"## {name}", "", *_table(summary["by_language"][language]), ""]
    for arm, name in ARMS.items():
        missed = [by_id[item_id] for item_id in summary["misses"][arm]]
        lines += [f"## Every miss of {arm} ({name}): {len(missed)}", ""]
        if not missed:
            lines += ["None.", ""]
        for row in missed:
            kind = "Scam not caught" if row["label"] == "block" else "Legitimate message blocked"
            found = ", ".join([*row["signals"], *row["rules"]]) or "nothing"
            lines += [
                f"**{row['id']}** ({LANGUAGES[row['lang']]}, {row['category']}). {kind}. {row['reason']} Found: {found}.",
                "",
                *[f"> {line}" for line in row["text"].splitlines()],
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--split", choices=("dev", "test"), default="test")
    args = parser.parse_args()
    if effective_agent_mode() != "live":
        print("eval-claims needs live mode: set AGENT_MODE=live and ANTHROPIC_API_KEY in .env.")
        return 1

    calls_before = llm.calls
    rows = []
    for item in load(args.split):
        row = judge_item(item)
        rows.append(row)
        marks = " ".join(f"{arm}={'block' if row[arm] else 'allow'}" for arm in ARMS)
        print(f"{row['id']} {row['lang']} expect {row['label']:5} | {marks} | {row['origin']} | {','.join(row['rules']) or '-'}")

    summary = summarise(rows)
    meta = {
        "split": args.split,
        "items": len(rows),
        "scams": summary["overall"]["C"]["scams"],
        "legit": summary["overall"]["C"]["legit"],
        "model": llm.model_name(),
        "date": datetime.now(timezone.utc).date().isoformat(),
        "llm_calls": llm.calls - calls_before,
        "live_items": sum(row["origin"] == "live" for row in rows),
    }
    print()
    print("\n".join(_table(summary["overall"])))
    print(verdict(summary))
    if args.split == "test":
        # Only the test split is reported: the dev split is for tuning.
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(report(rows, summary, meta), encoding="utf-8")
        results = {
            **meta,
            **summary,
            "arms": ARMS,
            "verdict": verdict(summary),
            "caveat": "Small set, written by the same author as the rules, not yet reviewed by a person.",
        }
        RESULTS_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {REPORT_FILE.name} and {RESULTS_FILE.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
