"""
Non-negotiable rule from CLAUDE.md: only actions/executor.py may post user money to
the ledger; seed and reset code is the only other writer. This scans the source.
"""

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

LEDGER_ITSELF = "ledger/__init__.py"  # defines post()
EXECUTOR = "actions/executor.py"
SEED_DIR = "seed/"


def _allowed(module: str) -> bool:
    return module in (LEDGER_ITSELF, EXECUTOR) or module.startswith(SEED_DIR)


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

    assert {"seed/__init__.py", EXECUTOR} <= writers  # the scan really finds the two callers
    assert [module for module in sorted(writers) if not _allowed(module)] == []


def test_the_scan_catches_both_ways_of_calling_post() -> None:
    assert _uses_ledger_post(ast.parse("from app.ledger import Leg, post"))
    assert _uses_ledger_post(ast.parse("from app import ledger\nledger.post(session)"))
    assert _uses_ledger_post(ast.parse("import app.ledger\napp.ledger.post(session)"))
    assert not _uses_ledger_post(ast.parse("from app.ledger import Leg, payment_legs"))
    assert not _uses_ledger_post(ast.parse("router.post('/reset')\nclient.post('/x')"))
