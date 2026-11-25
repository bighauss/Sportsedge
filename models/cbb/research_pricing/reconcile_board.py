"""Reconcile the corrected 738-row DraftKings board for research pricing (PAPER/0u).

Inherits missing dk_event_id from any full-game row that shares the same
(away, home, tip_utc) pair. Records explicit rejection reasons for rows that
cannot be priced. Does not invent event IDs or modify original evidence.
"""
from __future__ import annotations
import csv
from collections import defaultdict
from typing import Dict, List, Tuple

def load_board(path: str) -> List[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))

def inherit_event_ids(rows: List[dict]) -> Tuple[List[dict], List[dict]]:
    """Return (enriched_rows, rejections)."""
    by_key = defaultdict(set)
    for r in rows:
        if r.get("dk_event_id") and r.get("period") == "FG":
            key = (r["away"], r["home"], r["tip_utc"])
            by_key[key].add(r["dk_event_id"])
    enriched, rejected = [], []
    for i, r in enumerate(rows):
        row = dict(r)
        if not row.get("dk_event_id"):
            key = (row["away"], row["home"], row["tip_utc"])
            candidates = by_key.get(key, set())
            if len(candidates) == 1:
                row["dk_event_id"] = next(iter(candidates))
                row["event_id_source"] = "INHERITED_FROM_FG"
            elif len(candidates) > 1:
                rejected.append({"index": i, "reason": "AMBIGUOUS_EVENT_ID", "key": key})
                continue
            else:
                rejected.append({"index": i, "reason": "MISSING_EVENT_ID", "key": key})
                continue
        else:
            row["event_id_source"] = "ORIGINAL"
        enriched.append(row)
    return enriched, rejected

def census(rows: List[dict]) -> Dict:
    from collections import Counter
    return {
        "total": len(rows),
        "by_period": dict(Counter(r["period"] for r in rows)),
        "by_market": dict(Counter(r["market"] for r in rows)),
        "missing_event": sum(1 for r in rows if not r.get("dk_event_id")),
    }

if __name__ == "__main__":
    path = "models/cbb/lines/board_2026-11-25_0636CT_pdf_capture_h1_corrected.csv"
    rows = load_board(path)
    print("before", census(rows))
    enriched, rejected = inherit_event_ids(rows)
    print("after enriched", census(enriched))
    print("rejected", len(rejected))
    from collections import Counter
    print("rejection reasons", Counter(r["reason"] for r in rejected))
    print("1H still missing event", sum(1 for r in enriched if r["period"] == "1H" and not r.get("dk_event_id")))
