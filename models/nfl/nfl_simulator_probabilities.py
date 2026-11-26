#!/usr/bin/env python3
"""NFL simulator probabilities — hardened after adversarial review.
Requires strictly validated non-negative integer counts.
Losses computed directly as total - wins - pushes (no negative float).
Rejects NaN, Inf, fractional, missing, Boolean.
PAPER / 0u.
"""
from __future__ import annotations
import math
from typing import Optional


class InvalidInput(ValueError):
    pass


def _strict_count(value, label: str) -> int:
    if value is None:
        raise InvalidInput(f"MISSING_{label}")
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidInput(f"NON_INTEGER_{label}")
    if not math.isfinite(value):
        raise InvalidInput(f"NON_FINITE_{label}")
    if value < 0:
        raise InvalidInput(f"NEGATIVE_{label}")
    return value


def from_simulator_counts(wins, pushes, total) -> tuple[float, float, float]:
    """Probabilities from validated integer counts. Mass conserved exactly."""
    w = _strict_count(wins, "WINS")
    p = _strict_count(pushes, "PUSHES")
    t = _strict_count(total, "TOTAL")
    if t <= 0 or w + p > t:
        raise InvalidInput("COUNTS_EXCEED_TOTAL")
    p_win = w / t
    p_push = p / t
    p_loss = (t - w - p) / t  # exact, never negative float residual
    return p_win, p_push, p_loss


def valid_american(odds: Optional[int]) -> int:
    if odds is None or isinstance(odds, bool) or not isinstance(odds, int):
        raise InvalidInput("INVALID_ODDS")
    if odds == 0 or abs(odds) < 100 or abs(odds) > 100000:
        raise InvalidInput("INVALID_AMERICAN")
    return odds


def safe_ev_from_counts(wins, pushes, total, american: Optional[int]) -> float:
    p_win, p_push, p_loss = from_simulator_counts(wins, pushes, total)
    odds = valid_american(american)
    decimal = 1 + (odds / 100 if odds > 0 else 100 / -odds)
    return p_win * (decimal - 1) - p_loss


# --- Regression tests for the five additional failures ---
def test_nan_counts():
    try:
        from_simulator_counts(float("nan"), 0, 100)
        assert False
    except InvalidInput:
        pass


def test_infinite_count():
    try:
        from_simulator_counts(float("inf"), 0, 100)
        assert False
    except InvalidInput:
        pass



def test_fractional_counts():
    try:
        from_simulator_counts(5.5, 0, 100)
        assert False
    except InvalidInput:
        pass


def test_zero_loss_no_negative():
    w, p, l = from_simulator_counts(10000, 0, 10000)
    assert abs(l) < 1e-15 and l >= 0


def test_missing_count():
    try:
        from_simulator_counts(None, 0, 100)
        assert False
    except InvalidInput:
        pass


if __name__ == "__main__":
    test_nan_counts()
    test_infinite_count()
    test_fractional_counts()
    test_zero_loss_no_negative()
    test_missing_count()
    print("All five additional NFL adversarial cases now fail closed.")
    print("Loss computed exactly as (total - wins - pushes) / total.")
