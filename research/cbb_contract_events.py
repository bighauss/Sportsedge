"""Research adapter for Muse league contract sidecar v1."""
from collections import defaultdict
from research.cbb_event_binding import timestamp

def group_events(contracts):
    groups = defaultdict(list)
    for row in contracts:
        groups[row["dk_event_id"]].append(row)
    events, blocked = [], []
    for eid, rows in groups.items():
        try:
            keys = ("home", "away", "tipoff_ct", "source_comment_id",
                    "capture_start_ct", "capture_end_ct")
            first = rows[0]
            if not isinstance(eid, str) or not eid.isdigit():
                raise ValueError("invalid event ID")
            if any(any(r[k] != first[k] for k in keys) for r in rows):
                raise ValueError("inconsistent event metadata")
            markets = [r["market"] for r in rows]
            if len(set(markets)) != len(markets) or not {"SPREAD", "TOTAL"} <= set(markets) or not set(markets) <= {"SPREAD", "TOTAL", "ML"}:
                raise ValueError("invalid league market census")
            if any(r["sport"] != "CBB" or r["period"] != "FULL_GAME" or r["eligible_for_pricing"] is not False or r["settlement_rules_verified"] is not False for r in rows):
                raise ValueError("invalid research contract")
            if not timestamp(first["capture_start_ct"]) <= timestamp(first["capture_end_ct"]) < timestamp(first["tipoff_ct"]):
                raise ValueError("invalid capture chronology")
            events.append({"dk_event_id": eid, **{k:first[k] for k in keys}})
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            blocked.append({"dk_event_id":eid, "reason":str(exc), "contract_count":len(rows)})
    return events, blocked
