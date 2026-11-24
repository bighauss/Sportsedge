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
    if type(tolerance_seconds) is not int or not 0 <= tolerance_seconds <= 900:
        raise ValueError("invalid time tolerance")
    def identity(record, key):
        return str(record.get(key, "")) if isinstance(record, dict) else ""
    dk = Counter(identity(e, "dk_event_id") for e in events)
    cb = Counter(identity(g, "game_id") for g in slate)
    valid_slate = []
    for g in slate:
        try:
            if not identity(g, "game_id").isdigit() or not g["_home"] or not g["_away"] or g["_home"] == g["_away"]:
                continue
            valid_slate.append((g, timestamp(g["tipoff_utc"])))
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    results = []
    for e in events:
        eid = identity(e, "dk_event_id")
        row = {"dk_event_id": eid, "status": "BLOCKED", "cbbd_game_id": None}
        try:
            if not eid.isdigit() or dk[eid] != 1:
                raise ValueError("invalid or duplicate DK event")
            if not e["home"] or not e["away"] or e["home"] == e["away"]:
                raise ValueError("invalid team pair")
            tip = timestamp(e["tipoff_ct"])
            hits = [g for g, game_tip in valid_slate if g["_home"] == e["home"]
                    and g["_away"] == e["away"]
                    and abs((game_tip - tip).total_seconds()) <= tolerance_seconds]
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
