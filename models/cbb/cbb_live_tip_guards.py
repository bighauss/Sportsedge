#!/usr/bin/env python3
"""CBB live/tip guards — remaining admission defects closed.
Empty, False-only, NaN, invalid types, timezone-less timestamps all rejected.
PAPER / 0u.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import math

ALLOWED_PREGAME = {"pregame", "scheduled", "upcoming"}


def is_explicitly_live(quote: Dict[str, Any]) -> bool:
    """Any non-explicitly-pregame status rejects the quote."""
    status_fields = ["is_live", "live", "status", "game_status", "state"]
    has_explicit_pregame = False
    for field in status_fields:
        raw = quote.get(field)
        if raw is None:
            continue
        if isinstance(raw, bool):
            if raw is True:
                return True
            continue
        if isinstance(raw, (int, float)):
            if math.isnan(raw) or raw == 1:
                return True
            continue
        if isinstance(raw, str):
            s = raw.strip().lower()
            if not s:
                return True
            if s not in ALLOWED_PREGAME:
                return True
            has_explicit_pregame = True
            continue
        return True
    if not has_explicit_pregame:
        return True
    return False


def _parse_utc_strict(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts.strip():
        return None
    if not (ts.endswith("Z") or "+" in ts or "-" in ts[10:]):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt
    except Exception:
        return None


def is_at_or_after_tip(quote: Dict[str, Any]) -> bool:
    tip = _parse_utc_strict(quote.get("actual_tip_utc") or quote.get("tipoff_utc"))
    captured = _parse_utc_strict(quote.get("captured_at_utc") or quote.get("timestamp"))
    if tip is None or captured is None:
        return True
    return captured >= tip


def filter_pregame(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [q for q in quotes if not is_explicitly_live(q) and not is_at_or_after_tip(q)]


if __name__ == "__main__":
    assert is_explicitly_live({"status": ""})
    assert is_explicitly_live({"is_live": False})
    assert is_explicitly_live({"status": float("nan")})
    assert is_explicitly_live({"status": object()})
    assert is_at_or_after_tip({"actual_tip_utc": "2026-11-26T12:00:00", "captured_at_utc": "2026-11-26T12:00:00Z"})
    print("Remaining CBB admission defects now rejected.")
