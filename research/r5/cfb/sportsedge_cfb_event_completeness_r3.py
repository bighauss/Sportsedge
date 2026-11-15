"""CFB event completeness R3 RECOVERED CANDIDATE (not original claimed SHA).

Fail-closed structural audits of two scoreboard snapshots against an independently
supplied event census and team-id map. This cannot independently authenticate
source data; a clean structural audit stays PAPER/0u and source_admitted=False.

Compatible with existing R4/R5 wrappers, and deliberately composes the
original R2 validator rather than silently replacing its source/date checks.
"""
from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit
from sportsedge_cfb_event_completeness_r2 import audit as audit_r2


def _nonempty(value, label):
    if isinstance(value, bool) or value is None or not isinstance(value, (str, int)):
        raise ValueError(f"invalid_{label}")
    result = str(value).strip()
    if not result or result.casefold() in {"none", "null", "nan"}:
        raise ValueError(f"blank_{label}")
    return result


def _validated_payload(payload, name):
    """Return {event_id: ((role, team_id),...)} without inferring missing roles."""
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name}_not_object")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError(f"{name}_missing_events")
    out = {}
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError(f"{name}_bad_event")
        eid = _nonempty(event.get("id"), "event_id")
        if eid in out:
            raise ValueError(f"{name}_duplicate_event_id")
        comps = event.get("competitions")
        if not isinstance(comps, list) or len(comps) != 1 or not isinstance(comps[0], Mapping):
            raise ValueError(f"{name}_invalid_competitions")
        competitors = comps[0].get("competitors")
        if not isinstance(competitors, list) or len(competitors) != 2:
            raise ValueError(f"{name}_invalid_competitors")
        identities = []
        for comp in competitors:
            if not isinstance(comp, Mapping):
                raise ValueError(f"{name}_bad_competitor")
            role = comp.get("homeAway")
            if role not in ("home", "away"):
                raise ValueError(f"{name}_invalid_homeAway")
            team = comp.get("team")
            if not isinstance(team, Mapping):
                raise ValueError(f"{name}_bad_team_object")
            identities.append((role, _nonempty(team.get("id"), "team_id")))
        if {role for role, _ in identities} != {"home", "away"}:
            raise ValueError(f"{name}_duplicate_homeAway")
        if identities[0][1] == identities[1][1]:
            raise ValueError(f"{name}_duplicate_competitor")
        out[eid] = tuple(sorted(identities))
    return out


def _verify_census(census):
    if not isinstance(census, Mapping):
        raise ValueError("census_not_object")
    ids = census.get("event_ids")
    if not isinstance(ids, list) or not ids:
        raise ValueError("bad_census")
    parsed = [_nonempty(v, "census_event_id") for v in ids]
    if len(set(parsed)) != len(parsed):
        raise ValueError("duplicate_census_event_id")
    return set(parsed)


def _verify_metadata(metadata):
    if not isinstance(metadata, Mapping):
        raise ValueError("metadata_not_object")
    # A truthy string such as 'false' must never authorize a claimed census.
    if metadata.get("independent_census_verified") is not True:
        raise ValueError("unverified_census_boolean_required")
    urls = []
    for field in ("primary_url", "control_url", "independent_census_source_url"):
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"missing_{field}")
        u = urlsplit(value.strip())
        if u.scheme not in ("https", "http") or not u.netloc:
            raise ValueError(f"invalid_{field}")
        urls.append(value.strip())
    if len(set(urls)) != 3:
        raise ValueError("repeated_source_url")


def audit(primary, control, census, team_rows, metadata):
    """Research-only structural audit, always unauthenticated.

    Raises ValueError when malformed or inconsistent; R4/R5 catch it and
    serialize QUARANTINE. The explicit flag is a *claim*, not authentication.
    """
    _verify_metadata(metadata)
    a = _validated_payload(primary, "primary")
    b = _validated_payload(control, "control")
    expected = _verify_census(census)
    if set(a) != set(b) or set(a) != expected:
        raise ValueError("event_census_disagreement")
    if a != b:
        raise ValueError("competitor_identity_disagreement")
    if not isinstance(team_rows, list):
        raise ValueError("team_map_not_rows")
    # R2 owns verified timestamp syntax, census-before-capture ordering, and
    # duplicate/missing team-map ID checks. Its positive verdict is NEVER
    # relayed as source authentication.
    base = audit_r2(primary, control, census, team_rows, metadata)
    if base.get("status") != "CENSUS_VERIFIED_RESEARCH":
        return {"status": "QUARANTINE", "reason": "unmapped_teams",
                "event_count": len(a), "unmapped": base.get("unmapped", []),
                "release_status": "PAPER_0U", "source_admitted": False}
    return {"status": "STRUCTURAL_PASS_SOURCE_AUTH_PENDING", "event_count": len(a),
            "unmapped": [], "release_status": "PAPER_0U", "source_admitted": False,
            "note": "Structure only; event census independence and sources require independent authentication"}
