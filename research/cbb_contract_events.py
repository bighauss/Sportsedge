"""Group research contracts into event descriptors for independent schedule matching."""
from collections import defaultdict
from collections.abc import Mapping

from research.cbb_event_binding import timestamp


EVENT_FIELDS = (
    "home", "away", "tipoff_ct", "source_comment_id", "capture_start_ct", "capture_end_ct",
)
REQUIRED_MARKETS = {"SPREAD", "TOTAL"}
ALLOWED_MARKETS = REQUIRED_MARKETS | {"ML"}


def _event_metadata(rows):
    first = rows[0]
    metadata = {key: first[key] for key in EVENT_FIELDS}
    if any(row[key] != value for row in rows for key, value in metadata.items()):
        raise ValueError("inconsistent event metadata")

    teams = [first["home"], first["away"]]
    if not all(isinstance(team, str) and team.strip() for team in teams):
        raise ValueError("missing team identity")
    if teams[0].strip().casefold() == teams[1].strip().casefold():
        raise ValueError("identical team identities")
    source = first["source_comment_id"]
    if not ((type(source) is int and source > 0) or (isinstance(source, str) and source.strip())):
        raise ValueError("missing source comment ID")

    markets = [row["market"] for row in rows]
    unique = set(markets)
    if len(markets) != len(unique) or not REQUIRED_MARKETS <= unique <= ALLOWED_MARKETS:
        raise ValueError("invalid league market census")
    for row in rows:
        if (row["sport"] != "CBB" or row["period"] != "FULL_GAME"
                or row["eligible_for_pricing"] is not False or row["settlement_rules_verified"] is not False):
            raise ValueError("invalid research contract")
    if not timestamp(first["capture_start_ct"]) <= timestamp(first["capture_end_ct"]) < timestamp(first["tipoff_ct"]):
        raise ValueError("invalid capture chronology")
    return metadata


def group_events(contracts):
    groups = defaultdict(list)
    events, blocked = [], []
    for row in contracts:
        eid = row.get("dk_event_id") if isinstance(row, Mapping) else None
        if not isinstance(eid, str) or not eid.isascii() or not eid.isdigit():
            blocked.append({"dk_event_id": eid, "reason": "invalid event ID", "contract_count": 1})
            continue
        groups[eid].append(row)

    for eid, rows in groups.items():
        try:
            events.append({"dk_event_id": eid, **_event_metadata(rows)})
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            blocked.append({"dk_event_id": eid, "reason": str(exc), "contract_count": len(rows)})
    return events, blocked
