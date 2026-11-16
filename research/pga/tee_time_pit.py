"""PGA tee-time research preflight. Never authenticates a provider or authorizes bets."""
import hashlib
import json
import math
from datetime import datetime, timezone

def utc(value):
    if not isinstance(value, str):
        raise ValueError("UTC_REQUIRED")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("UTC_REQUIRED") from None
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_REQUIRED")
    return dt.astimezone(timezone.utc)

def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("ORIGINAL_DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _require_finite_json(value):
    # Python's JSON decoder can parse a syntactically valid 1e999 into inf.
    # Reject it recursively, including unknown nested provider fields.
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("ORIGINAL_NONFINITE_NUMBER")
    if isinstance(value, dict):
        for part in value.values():
            _require_finite_json(part)
    elif isinstance(value, list):
        for part in value:
            _require_finite_json(part)


def audit(raw: bytes, manifest: dict, *, frozen_utc: str, expected_player_ids: list[str]):
    """All offered field entries must be retained; no inferred withdrawals or odds."""
    if not isinstance(raw, bytes) or not raw or len(raw) > 5_000_000:
        raise ValueError("RAW_BYTES_INVALID")
    if not isinstance(manifest, dict) or manifest.get("sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("ORIGINAL_SHA_MISMATCH")
    if any(not isinstance(manifest.get(k), str) or not manifest[k].strip()
           for k in ("source", "source_receipt_id")):
        raise ValueError("SOURCE_PROVENANCE_MISSING")
    observed, captured, frozen = (utc(manifest.get(k)) for k in ("observed_utc", "captured_utc", "frozen_utc"))
    if frozen != utc(frozen_utc) or observed > captured or captured > frozen:
        raise ValueError("SOURCE_CLOCK_INVALID")
    try:
        data = json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE")))
        _require_finite_json(data)
    except (UnicodeError, ValueError, TypeError, OverflowError) as exc:
        raise ValueError("ORIGINAL_JSON_INVALID") from exc
    if not isinstance(data, list) or not data:
        raise ValueError("FIELD_CENSUS_EMPTY")
    if not isinstance(expected_player_ids, list) or not expected_player_ids or any(not isinstance(x, str) or not x for x in expected_player_ids):
        raise ValueError("EXPECTED_FIELD_INVALID")
    if len(set(expected_player_ids)) != len(expected_player_ids):
        raise ValueError("EXPECTED_FIELD_DUPLICATE")
    ids = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("player_id"), str) or not item["player_id"]:
            raise ValueError("PLAYER_ID_MISSING")
        status = item.get("status")
        if status not in ("ENTERED", "WITHDRAWN", "UNKNOWN"):
            raise ValueError("FIELD_STATUS_INVALID")
        # A golfer withdrawn before round assignments or with an unknown
        # status may legitimately have NO scheduled tee slot. Keep the player
        # in the census rather than synthesizing a tee time. ENTERED always
        # requires a genuine future slot; any supplied slot must be future.
        slot = item.get("tee_time_utc")
        if slot is None or slot == "":
            if status == "ENTERED":
                raise ValueError("TEE_TIME_REQUIRED_FOR_ENTERED")
        elif not isinstance(slot, str) or utc(slot) <= frozen:
            raise ValueError("TEE_TIME_NOT_FUTURE")
        ids.append(item["player_id"])
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_PLAYER")
    if set(ids) != set(expected_player_ids):
        raise ValueError("FIELD_DENOMINATOR_MISMATCH")
    return {"state": "PAPER_0U_SOURCE_CLAIMS_UNAUTHENTICATED", "approved_stake_u": 0,
            "source_sha256": manifest["sha256"], "field_rows": len(ids),
            "withdrawn_rows": sum(r["status"] == "WITHDRAWN" for r in data),
            "missing_rows": 0,
            "unassigned_tee_time_rows": sum(
                r.get("tee_time_utc") in (None, "") for r in data),
            "expected_field_independently_authenticated": False,
            "provider_authentication_attested": False,
            "observed_utc": manifest["observed_utc"],
            "captured_utc": manifest["captured_utc"], "frozen_utc": frozen_utc}
