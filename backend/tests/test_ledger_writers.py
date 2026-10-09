"""
Non-negotiable rule from CLAUDE.md: only actions/executor.py may post user money to
the ledger; seed and reset code is the only other writer. This scans the source.
"""

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

ALLOWED_WRITERS = {
    "ledger/__init__.py",  # defines post()
    "seed/__init__.py",  # seed and reset
    "actions/executor.py",  # arrives in a later step
}


def _uses_ledger_post(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.ledger":
            if any(alias.name in ("post", "*") for alias in node.names):
                return True
        if isinstance(node, ast.Attribute) and node.attr == "post":
            owner = node.value
            name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", None)
            if name == "ledger":
                return True
    return False


def test_only_seed_and_the_executor_can_post_to_the_ledger() -> None:
    writers = {
        path.relative_to(APP_DIR).as_posix()
        for path in APP_DIR.rglob("*.py")
        if _uses_ledger_post(ast.parse(path.read_text(encoding="utf-8")))
    }

    assert "seed/__init__.py" in writers  # the scan really finds callers
    assert writers <= ALLOWED_WRITERS, f"Not allowed to post: {sorted(writers - ALLOWED_WRITERS)}"


def test_the_scan_catches_both_ways_of_calling_post() -> None:
    assert _uses_ledger_post(ast.parse("from app.ledger import Leg, post"))
    assert _uses_ledger_post(ast.parse("from app import ledger\nledger.post(session)"))
    assert _uses_ledger_post(ast.parse("import app.ledger\napp.ledger.post(session)"))
    assert not _uses_ledger_post(ast.parse("from app.ledger import Leg, payment_legs"))
    assert not _uses_ledger_post(ast.parse("router.post('/reset')\nclient.post('/x')"))
