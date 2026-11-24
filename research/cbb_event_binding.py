"""Research-only event reconciliation; no pricing or production changes."""
from datetime import datetime
from collections import Counter

def timestamp(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.utcoffset() is None:
        raise ValueError("timezone required")
    return d

def reconcile(events, slate, *, tolerance_seconds=900):
    """Exact oriented team names; no inferred aliases or provider identities."""
    events, slate = list(events), list(slate)
    dk = Counter(str(e["dk_event_id"]) for e in events)
    cb = Counter(str(g["game_id"]) for g in slate)
    results = []
    for e in events:
        eid = str(e["dk_event_id"])
        row = {"dk_event_id": eid, "status": "BLOCKED", "cbbd_game_id": None}
        try:
            if not eid.isdigit() or dk[eid] != 1:
                raise ValueError("invalid or duplicate DK event")
            if not e["home"] or not e["away"] or e["home"] == e["away"]:
                raise ValueError("invalid team pair")
            tip = timestamp(e["tipoff_ct"])
            hits = [g for g in slate if g["_home"] == e["home"]
                    and g["_away"] == e["away"]
                    and abs((timestamp(g["tipoff_utc"]) - tip).total_seconds()) <= tolerance_seconds]
            if len(hits) != 1:
                raise ValueError("no unique oriented time-matched game")
            gid = str(hits[0]["game_id"])
            if not gid.isdigit() or cb[gid] != 1:
                raise ValueError("invalid or duplicate CBBD game")
            row.update(status="MATCHED", cbbd_game_id=gid)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            row["reason"] = str(exc)
        results.append(row)
    counts = Counter(r["cbbd_game_id"] for r in results if r["status"] == "MATCHED")
    for r in results:
        if r["status"] == "MATCHED" and counts[r["cbbd_game_id"]] != 1:
            r.update(status="BLOCKED", cbbd_game_id=None, reason="multiple DK events map to CBBD game")
    return results
