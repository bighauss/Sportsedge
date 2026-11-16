"""Future-only observability run-manifest verifier; no model or betting authorization."""
import hashlib
import json
import math
from datetime import datetime, timezone

class Hold(ValueError):
    pass

def utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise Hold("UTC_Z_REQUIRED")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise Hold("UTC_INVALID") from exc
    if dt.utcoffset().total_seconds() != 0:
        raise Hold("UTC_REQUIRED")
    return dt.astimezone(timezone.utc)

def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise Hold("DUPLICATE_JSON_KEY")
        out[k] = v
    return out

def _finite_original_json(value):
    # json.loads accepts numeric exponent overflow (1e999 -> float('inf'))
    # even when parse_constant rejects NaN and Infinity spellings.
    if isinstance(value, float) and not math.isfinite(value):
        raise Hold("NONFINITE_JSON")
    if isinstance(value, dict):
        for child in value.values():
            _finite_original_json(child)
    elif isinstance(value, list):
        for child in value:
            _finite_original_json(child)


def verify(manifest_bytes: bytes, source_bytes: dict[str, bytes]):
    """Validate original bytes, identity, clocks and exact source denominator.

    Only local consistency: does NOT attest provider timestamps or authenticate odds.
    """
    if not isinstance(manifest_bytes, bytes) or not 0 < len(manifest_bytes) <= 1_000_000:
        raise Hold("MANIFEST_BYTES_INVALID")
    try:
        m = json.loads(manifest_bytes, object_pairs_hook=_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(Hold("NONFINITE_JSON")))
        _finite_original_json(m)
    except Hold:
        raise
    except (UnicodeError, ValueError, TypeError) as exc:
        raise Hold("MANIFEST_JSON_INVALID") from exc
    if not isinstance(m, dict) or m.get("schema") != "SPORTSEDGE_OBSERVABILITY_PIT_V1":
        raise Hold("MANIFEST_SCHEMA_INVALID")
    if m.get("official") is not False or type(m.get("stake_u")) not in (int, float) or m["stake_u"] != 0:
        raise Hold("PAPER_ONLY")
    if type(m.get("seed")) is not int or m["seed"] < 0:
        raise Hold("SEED_REQUIRED")
    if not isinstance(m.get("model_sha256"), str) or len(m["model_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in m["model_sha256"]):
        raise Hold("MODEL_SHA_INVALID")
    freeze, kickoff = utc(m.get("freeze_utc")), utc(m.get("kickoff_utc"))
    if freeze >= kickoff:
        raise Hold("FREEZE_NOT_PREGAME")
    sources = m.get("sources")
    if not isinstance(sources, list) or not sources or not isinstance(source_bytes, dict):
        raise Hold("SOURCES_REQUIRED")
    ids = []
    for s in sources:
        if not isinstance(s, dict):
            raise Hold("SOURCE_INVALID")
        sid = s.get("id")
        if not isinstance(sid, str) or not sid.strip() or "/" in sid or "\\" in sid:
            raise Hold("SOURCE_ID_INVALID")
        ids.append(sid)
        raw = source_bytes.get(sid)
        if not isinstance(raw, bytes) or not raw or len(raw) > 50_000_000:
            raise Hold("SOURCE_BYTES_MISSING")
        if hashlib.sha256(raw).hexdigest() != s.get("sha256"):
            raise Hold("SOURCE_SHA_MISMATCH")
        if not isinstance(s.get("provider"), str) or not s["provider"].strip():
            raise Hold("SOURCE_PROVIDER_MISSING")
        published, observed, captured = (utc(s.get(k)) for k in ("published_utc", "observed_utc", "captured_utc"))
        if not (published <= observed <= captured <= freeze):
            raise Hold("SOURCE_CLOCK_INVALID")
    if len(set(ids)) != len(ids) or set(ids) != set(source_bytes):
        raise Hold("SOURCE_DENOMINATOR_MISMATCH")
    return {"status": "PAPER_0U_LOCAL_LINEAGE_ONLY", "official": False,
            "stake_u": 0, "source_count": len(ids),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "model_sha256": m["model_sha256"], "seed": m["seed"]}
