"""Where the measured results of the claim check live, for the Security page to show."""

import json
from pathlib import Path
from typing import Any

# Written by `make eval-claims` (eval/claims/run.py). Committed, so the page shows real numbers.
RESULTS_FILE = Path(__file__).resolve().parent.parent.parent / "eval" / "claims" / "results.json"


def load_results() -> dict[str, Any] | None:
    try:
        return json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
