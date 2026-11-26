#!/usr/bin/env python3
"""CBB player identity and live-quote guards.
Key: (event_id, period, market, player_id, threshold)
Rejects explicitly live quotes regardless of scheduled tip.
PAPER / 0u.
"""
from __future__ import annotations
from typing import Any, Dict, List

def market_key(quote: Dict[str, Any]) -> tuple:
    """Stable identity key. Collisions only if true duplicate."""
    return (
        str(quote.get("event_id", "")),
        str(quote.get("period", "full")),
        str(quote.get("market", "")),
        str(quote.get("player_id", quote.get("player", ""))),
        float(quote.get("threshold", 0)),
    )

def is_explicitly_live(quote: Dict[str, Any]) -> bool:
    status = str(quote.get("status", "")).lower()
    live_flag = quote.get("is_live", False)
    return live_flag is True or status in ("live", "inprogress", "in-progress")

def filter_pregame(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop any explicitly live quote. Scheduled tip is insufficient."""
    return [q for q in quotes if not is_explicitly_live(q)]

def dedupe_by_identity(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for q in quotes:
        k = market_key(q)
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out

if __name__ == "__main__":
    q1 = {"event_id": "g1", "player_id": "p1", "threshold": 15.5, "market": "points", "status": "pregame"}
    q2 = {"event_id": "g1", "player_id": "p2", "threshold": 15.5, "market": "points", "status": "pregame"}
    assert market_key(q1) != market_key(q2)
    live = {"event_id": "g1", "player_id": "p1", "threshold": 15.5, "status": "live", "is_live": True}
    assert is_explicitly_live(live)
    kept = filter_pregame([q1, live])
    assert len(kept) == 1 and kept[0]["player_id"] == "p1"
    print("CBB identity and live guards: distinct players preserved, live rejected.")
