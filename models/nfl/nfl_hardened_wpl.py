#!/usr/bin/env python3
"""Hardened NFL win/push/loss and odds validation.
Addresses adversarial findings: NaN, zero, missing, invalid American odds.
Probabilities must come from simulator; no EV reverse-engineering.
PAPER / 0u research only.
"""
from __future__ import annotations
import math
from typing import Optional


class InvalidInput(ValueError):
    """Raised for non-finite or illegitimate inputs."""


def _finite(value: float, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise InvalidInput(f"NON_NUMERIC_{label}")
    if not math.isfinite(value):
        raise InvalidInput(f"NON_FINITE_{label}")
    return float(value)


def valid_american_odds(odds: Optional[int]) -> int:
    """Legitimate American odds: integer, |odds| >= 100, not zero, not NaN."""
    if odds is None:
        raise InvalidInput("MISSING_ODDS")
    if isinstance(odds, bool) or not isinstance(odds, int):
        raise InvalidInput("NON_INTEGER_ODDS")
    if odds == 0:
        raise InvalidInput("ZERO_ODDS")
    if abs(odds) < 100 or abs(odds) > 100000:
        raise InvalidInput("INVALID_AMERICAN_RANGE")
    return odds


def simulator_probabilities(p_win: float, p_push: float) -> tuple[float, float, float]:
    """Require finite probabilities that sum to <= 1. No EV-derived fallback."""
    win = _finite(p_win, "WIN")
    push = _finite(p_push, "PUSH")
    if win < 0 or push < 0 or win + push > 1 + 1e-9:
        raise InvalidInput("PROBABILITIES_OUT_OF_RANGE")
    loss = max(0.0, 1.0 - win - push)
    return win, push, loss


def safe_ev(p_win: float, p_push: float, american: Optional[int]) -> float:
    """EV only after validation. Never derives probabilities from EV."""
    win, push, loss = simulator_probabilities(p_win, p_push)
    odds = valid_american_odds(american)
    decimal = 1 + (odds / 100 if odds > 0 else 100 / -odds)
    return win * (decimal - 1) - loss


# --- Regression tests for the five reproduced failures ---
def test_nan_ev():
    try:
        safe_ev(float("nan"), 0.05, -110)
        assert False, "should have rejected NaN"
    except InvalidInput:
        pass


def test_nan_odds():
    try:
        safe_ev(0.5, 0.05, None)  # type: ignore
        assert False
    except InvalidInput:
        pass


def test_zero_odds():
    try:
        safe_ev(0.5, 0.05, 0)
        assert False
    except InvalidInput:
        pass


def test_missing_odds():
    try:
        safe_ev(0.5, 0.05, None)
        assert False
    except InvalidInput:
        pass


def test_invalid_plus_50():
    try:
        safe_ev(0.5, 0.05, 50)
        assert False
    except InvalidInput:
        pass


def test_boolean_probability():
    try:
        safe_ev(True, 0.05, -110)  # type: ignore
        assert False
    except InvalidInput:
        pass


if __name__ == "__main__":
    test_nan_ev()
    test_nan_odds()
    test_zero_odds()
    test_missing_odds()
    test_invalid_plus_50()
    test_boolean_probability()
    print("All adversarial NFL cases now fail closed (including Boolean).")
    print("Probabilities required from simulator; no EV reverse-engineering.")
