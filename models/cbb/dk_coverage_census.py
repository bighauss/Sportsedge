"""Per-event coverage census for CBB DraftKings research board (PAPER / 0u).

Emits a row for every (period, market) family in the catalog. Team-total order
remains NOT_VERIFIED until independent confirmation. No prices or probabilities
are invented.
"""
from __future__ import annotations

def census_for_event(event_id: str, observed_families: set) -> list:
    """Return list of dicts covering the catalog for one DK event."""
    # Minimal catalog subset used by the team-total diagnostic
    families = [
        ("FG", "SPREAD"), ("FG", "ML"), ("FG", "TOTAL"),
        ("FG", "TT_HOME"), ("FG", "TT_AWAY"),
        ("FG", "ALT_SPREAD"), ("FG", "ALT_TOTAL"),
        ("1H", "SPREAD"), ("1H", "TOTAL"),
    ]
    rows = []
    for period, market in families:
        status = "OBSERVED" if (period, market) in observed_families else "NO_QUOTE"
        reason = None if status == "OBSERVED" else "NO_QUOTE"
        if market in ("TT_HOME", "TT_AWAY", "TOTAL", "ALT_TOTAL"):
            reason = reason or "TOTALS_ORDER_UNVERIFIED"
            status = "NOT_VERIFIED" if status == "OBSERVED" else status
        rows.append({
            "dk_event_id": event_id,
            "period": period,
            "market": market,
            "status": status,
            "reason_code": reason,
            "label": "PAPER_0U",
        })
    return rows
