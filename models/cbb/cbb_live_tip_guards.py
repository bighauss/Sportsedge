#!/usr/bin/env python3
"""CBB live/tip guards — six additional admission failures.
Conservative: missing status, unrecognized status, exact tip, malformed timestamps all rejected.
PAPER / 0u.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

LIVE_STRINGS = {"live", "true", "1", "yes", "inprogress", "in-progress", "in_progress", "final", "started", "active"}


def _parse_utc(ts: Any) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def is_explicitly_live(quote: Dict[str, Any]) -> bool:
    """Conservative rejection."""
    candidates = [
        quote.get("is_live"), quote.get("live"), quote.get("status"),
        quote.get("game_status"), quote.get("state"),
    ]
    seen_any = False
    for raw in candidates:
        if raw is None:
            continue
        seen_any = True
        if isinstance(raw, bool) and raw is True:
            return True
        if isinstance(raw, (int, float)) and raw == 1:
            return True
        if isinstance(raw, str):
            s = raw.strip().lower()
            if s and s not in ("pregame", "scheduled", "upcoming"):
                return True
    if not seen_any:
        return True
    return False


def is_at_or_after_tip(quote: Dict[str, Any]) -> bool:
    tip = _parse_utc(quote.get("actual_tip_utc") or quote.get("tipoff_utc"))
    captured = _parse_utc(quote.get("captured_at_utc") or quote.get("timestamp"))
    if tip is None or captured is None:
        return True
    return captured >= tip


def filter_pregame(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [q for q in quotes if not is_explicitly_live(q) and not is_at_or_after_tip(q)]


if __name__ == "__main__":
    assert is_at_or_after_tip({"actual_tip_utc": "2026-11-26T12:00:00Z", "captured_at_utc": "2026-11-26T12:00:00Z"})
    assert is_at_or_after_tip({"actual_tip_utc": "not-a-date", "captured_at_utc": "2026-11-26T12:00:00Z"})
    assert is_explicitly_live({"status": "UNKNOWN"})
    assert is_explicitly_live({})
    print("Six additional CBB admission failures now rejected.")
