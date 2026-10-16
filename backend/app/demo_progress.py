"""
What the presenter has shown since the last reset, for the steps that leave nothing in the
database: the invoice's source view, the chain check, the tamper simulation, the red-team
run and the rule sources. Kept in memory; a reset or a restart clears it.
"""

import threading

FLAGS = ("invoice_viewed", "chain_verified", "tamper_simulated", "redteam_run", "sources_viewed")

_lock = threading.Lock()
_seen: set[str] = set()


def mark(flag: str) -> None:
    if flag not in FLAGS:
        raise ValueError(f"Unknown demo flag: {flag}")
    with _lock:
        _seen.add(flag)


def seen() -> set[str]:
    with _lock:
        return set(_seen)


def clear() -> None:
    with _lock:
        _seen.clear()
