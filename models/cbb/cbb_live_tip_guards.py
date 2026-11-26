#!/usr/bin/env python3
"""CBB live and tip guards — hardened for five admission failures.
Conservative: any live-indicating field rejects the quote.
Actual tip boundary enforced.
PAPER / 0u.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

LIVE_STRINGS = {"live", "true", "1", "yes", "inprogress", "in-progress", "in_progress", "final"}


def is_explicitly_live(quote: Dict[str, Any]) -> bool:
    """Conservative: reject if ANY field indicates live or final."""
    candidates = [
        quote.get("is_live"),
        quote.get("live"),
        quote.get("status"),
        quote.get("game_status"),
        quote.get("state"),
    ]
    for raw in candidates:
        if raw is None:
            continue
        if isinstance(raw, bool) and raw is True:
            return True
        if isinstance(raw, (int, float)) and raw == 1:
            return True
        if isinstance(raw, str) and raw.strip().lower() in LIVE_STRINGS:
            return True
    return False


def is_after_actual_tip(quote: Dict[str, Any], now_utc: Optional[datetime] = None) -> bool:
    """Reject if capture time is after verified actual tip."""
    tip = quote.get("actual_tip_utc") or quote.get("tipoff_utc")
    captured = quote.get("captured_at_utc") or quote.get("timestamp")
    if not tip or not captured:
        return False
    try:
        tip_dt = datetime.fromisoformat(str(tip).replace("Z", "+00:00"))
        cap_dt = datetime.fromisoformat(str(captured).replace("Z", "+00:00"))
        if tip_dt.tzinfo is None:
            tip_dt = tip_dt.replace(tzinfo=timezone.utc)
        if cap_dt.tzinfo is None:
            cap_dt = cap_dt.replace(tzinfo=timezone.utc)
        return cap_dt > tip_dt
    except Exception:
        return False


def filter_pregame(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [q for q in quotes if not is_explicitly_live(q) and not is_after_actual_tip(q)]


if __name__ == "__main__":
    assert is_explicitly_live({"is_live": False, "status": "LIVE"})
    assert is_explicitly_live({"is_live": 1})
    assert is_explicitly_live({"live": True})
    assert is_explicitly_live({"status": "Final"})
    q = {"actual_tip_utc": "2026-11-26T12:00:00Z", "captured_at_utc": "2026-11-26T12:05:00Z"}
    assert is_after_actual_tip(q)
    print("All five CBB live-admission failures now rejected.")
