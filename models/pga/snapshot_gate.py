"""Fail-closed PGA pregame data snapshot adapter; no network or invented provider claims."""
from datetime import datetime, timezone
import hashlib
import json
import math

REQUIRED = ("provider", "event_id", "captured_utc", "event_start_utc",
            "source_sha256", "players")


def _utc(v):
    if not isinstance(v, str) or not v.endswith("Z"):
        raise ValueError("UTC_Z_REQUIRED")
    dt = datetime.fromisoformat(v[:-1] + "+00:00")
    if dt.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_REQUIRED")
    return dt


def validate_snapshot(snapshot, source_bytes, *, provider_verified=False):
    """No accepted feed unless external provenance is independently attested.

    source_sha256 is a byte-integrity check, NOT proof of provider identity or time.
    """
    reasons = []
    if not isinstance(snapshot, dict):
        return {"status": "BLOCKED", "reasons": ["INVALID_SNAPSHOT"]}
    for key in REQUIRED:
        if key not in snapshot or snapshot[key] in (None, "", []):
            reasons.append("MISSING_" + key.upper())
    if not provider_verified:
        reasons.append("PROVIDER_NOT_VERIFIED")
    if not isinstance(source_bytes, bytes):
        reasons.append("SOURCE_BYTES_REQUIRED")
    else:
        digest = hashlib.sha256(source_bytes).hexdigest()
        if snapshot.get("source_sha256") != digest:
            reasons.append("SOURCE_HASH_MISMATCH")
    try:
        if _utc(snapshot["captured_utc"]) >= _utc(snapshot["event_start_utc"]):
            reasons.append("POST_START_CAPTURE")
    except (KeyError, ValueError, TypeError, OverflowError):
        reasons.append("INVALID_CLOCK")
    players = snapshot.get("players")
    if not isinstance(players, list) or len(players) < 2:
        reasons.append("FIELD_REQUIRED")
    else:
        seen = set()
        for i, p in enumerate(players):
            if not isinstance(p, dict):
                reasons.append("INVALID_PLAYER_ROW")
                continue
            pid = p.get("player_id")
            if not isinstance(pid, str) or not pid.strip():
                reasons.append("PLAYER_ID_REQUIRED")
            elif pid in seen:
                reasons.append("DUPLICATE_PLAYER")
            else:
                seen.add(pid)
            if p.get("identity_verified") is not True:
                reasons.append("PLAYER_ID_NOT_VERIFIED")
            for k in ("sg_ott", "sg_app", "sg_arg", "sg_putt", "round_sd"):
                v = p.get(k)
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                    reasons.append("INVALID_" + k.upper())
            if isinstance(p.get("round_sd"), (int, float)) and p["round_sd"] <= 0:
                reasons.append("INVALID_ROUND_SD")
    if reasons:
        return {"status": "BLOCKED", "reasons": sorted(set(reasons))}
    return {"status": "PREGAME_EVIDENCE_ONLY_UNCALIBRATED",
            "players": [{**p, "source_status": "PREGAME_VERIFIED"} for p in players],
            "source_sha256": snapshot["source_sha256"],
            "betting_status": "PAPER_0U"}
