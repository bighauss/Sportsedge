#!/usr/bin/env python3
"""CBB identity and live guards — hardened after adversarial review.
Requires authoritative player_id (no name fallback).
Normalizes and strictly validates live-status.
Rejects missing/malformed thresholds.
Preserves conflicting quotes with explicit hold reason.
PAPER / 0u.
"""
from __future__ import annotations
from typing import Any, Dict, List
import math


def _require_player_id(quote: Dict[str, Any]) -> str:
    pid = quote.get("player_id")
    if not pid or not isinstance(pid, str) or not pid.strip():
        raise ValueError("MISSING_AUTHORITATIVE_PLAYER_ID")
    return pid.strip()


def market_key(quote: Dict[str, Any]) -> tuple:
    pid = _require_player_id(quote)
    thresh = quote.get("threshold")
    if thresh is None or not isinstance(thresh, (int, float)) or not math.isfinite(thresh):
        raise ValueError("MISSING_OR_INVALID_THRESHOLD")
    return (
        str(quote.get("event_id", "")),
        str(quote.get("period", "full")),
        str(quote.get("market", "")),
        pid,
        float(thresh),
    )


def is_explicitly_live(quote: Dict[str, Any]) -> bool:
    raw = quote.get("is_live", quote.get("status", ""))
    if isinstance(raw, bool):
        return raw is True
    if isinstance(raw, str):
        return raw.strip().lower() in ("live", "true", "1", "inprogress", "in-progress", "yes")
    return False


def filter_pregame(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [q for q in quotes if not is_explicitly_live(q)]


def hold_conflicting(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Preserve conflicts with explicit hold reason instead of silent discard."""
    seen = {}
    out = []
    for q in quotes:
        try:
            k = market_key(q)
        except ValueError as e:
            q = dict(q)
            q["hold_reason"] = str(e)
            out.append(q)
            continue
        if k in seen:
            seen[k]["hold_reason"] = "CONFLICTING_PRICE"
            q = dict(q)
            q["hold_reason"] = "CONFLICTING_PRICE"
            out.append(q)
        else:
            seen[k] = q
            out.append(q)
    return out


if __name__ == "__main__":
    assert is_explicitly_live({"status": "LIVE"})
    assert is_explicitly_live({"is_live": "true"})
    try:
        market_key({"player": "Name Only", "threshold": 15.5})
        assert False
    except ValueError:
        pass
    try:
        market_key({"player_id": "p1"})
        assert False
    except ValueError:
        pass
    q1 = {"event_id": "g1", "player_id": "p1", "threshold": 15.5, "market": "points", "price": -110}
    q2 = {"event_id": "g1", "player_id": "p1", "threshold": 15.5, "market": "points", "price": -115}
    held = hold_conflicting([q1, q2])
    assert any(q.get("hold_reason") == "CONFLICTING_PRICE" for q in held)
    print("CBB guards hardened: string live rejected, missing ID/threshold rejected, conflicts held.")
