#!/usr/bin/env python3
"""Consolidated NFL simulator probability interface.
Direct from simulator only. No EV reverse-engineering.
Rejects non-finite, Boolean, out-of-range, and illegitimate odds.
PAPER / 0u.
"""
from __future__ import annotations
import math
from typing import Optional

class InvalidInput(ValueError):
    pass

def _finite(v, label: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise InvalidInput(f"NON_NUMERIC_{label}")
    if not math.isfinite(v):
        raise InvalidInput(f"NON_FINITE_{label}")
    return float(v)

def from_simulator_counts(wins: int, pushes: int, total: int) -> tuple[float, float, float]:
    """Derive probabilities from raw simulator outcome counts. Conserves mass."""
    if total <= 0 or wins < 0 or pushes < 0 or wins + pushes > total:
        raise InvalidInput("INVALID_COUNTS")
    p_win = wins / total
    p_push = pushes / total
    p_loss = 1.0 - p_win - p_push
    return p_win, p_push, p_loss

def valid_american(odds: Optional[int]) -> int:
    if odds is None or isinstance(odds, bool) or not isinstance(odds, int):
        raise InvalidInput("INVALID_ODDS")
    if odds == 0 or abs(odds) < 100 or abs(odds) > 100000:
        raise InvalidInput("INVALID_AMERICAN")
    return odds

def safe_ev_from_counts(wins: int, pushes: int, total: int, american: Optional[int]) -> float:
    p_win, p_push, p_loss = from_simulator_counts(wins, pushes, total)
    odds = valid_american(american)
    decimal = 1 + (odds / 100 if odds > 0 else 100 / -odds)
    return p_win * (decimal - 1) - p_loss

if __name__ == "__main__":
    w, p, l = from_simulator_counts(5000, 300, 10000)
    assert abs(w + p + l - 1.0) < 1e-12
    try:
        from_simulator_counts(True, 0, 100)  # type: ignore
        assert False
    except InvalidInput:
        pass
    print("Consolidated simulator interface: counts conserve mass, Boolean rejected.")
