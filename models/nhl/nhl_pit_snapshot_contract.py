"""Fail-closed NHL pregame source-byte/time contract; PAPER / 0u only.

Original bytes and timestamps can be validated for internal consistency, but
operator-supplied publication/provider claims are NOT external authentication.
Does not change or certify NHL model coefficients, odds, EV, or eligibility.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import re

SCHEMA = "sportsedge-nhl-pit-snapshot-v1"
ROLES = frozenset(("MODEL", "TEAM_XG", "GOALIE_STATS", "SKATER_STATS", "LINEUP"))
ROOT = Path(__file__).resolve().parents[2]
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_-]{1,79}$")
EVENT_FIELDS = frozenset(("event_id", "home_team_id", "away_team_id",
                          "home_goalie_id", "away_goalie_id",
                          "freeze_utc", "kickoff_utc"))
SOURCE_FIELDS = frozenset(("role", "path", "sha256", "provider",
                           "data_through_utc", "published_utc",
                           "observed_utc", "captured_utc"))
LINEUP_FIELDS = frozenset(("event_id", "home_team_id", "away_team_id",
                           "home_goalie_id", "away_goalie_id",
                           "home_confirmed", "away_confirmed", "observed_utc"))


class Blocked(ValueError):
    """Invalid or non-reproducible point-in-time evidence."""


def _strict_object(obj, required, label):
    if not isinstance(obj, dict) or set(obj) != required:
        raise Blocked("INVALID_FIELDS:" + label)
    return obj


def _unique_pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise Blocked("DUPLICATE_JSON_KEY:" + k)
        out[k] = v
    return out


def _invalid_constant(value):
    raise Blocked("NONFINITE_JSON:" + value)


def _json(original, label):
    try:
        return json.loads(original.decode("utf-8"), object_pairs_hook=_unique_pairs,
                          parse_constant=_invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Blocked("INVALID_UTF8_JSON:" + label) from exc


def _utc(value, label):
    if type(value) is not str:
        raise Blocked("INVALID_UTC:" + label)
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Blocked("INVALID_UTC:" + label) from exc
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise Blocked("UTC_REQUIRED:" + label)
    return stamp.astimezone(timezone.utc)


def _id(value, label):
    if type(value) is not str or not IDENTITY.fullmatch(value):
        raise Blocked("UNBOUND_ID:" + label)
    return value


def _path(raw, label, *, allow_model=False):
    if type(raw) is not str or not raw.strip():
        raise Blocked("MISSING_PATH:" + label)
    lexical = Path(os.path.abspath(raw))
    resolved = lexical.resolve()
    if not allow_model and (lexical == ROOT or ROOT in lexical.parents
                            or resolved == ROOT or ROOT in resolved.parents):
        raise Blocked("SOURCE_INSIDE_PUBLIC_REPOSITORY:" + label)
    return resolved


def _bytes(path, label):
    if not path.is_file():
        raise Blocked("SOURCE_NOT_A_FILE:" + label)
    if path.stat().st_size == 0 or path.stat().st_size > 20_000_000:
        raise Blocked("SOURCE_EMPTY_OR_TOO_LARGE:" + label)
    data = path.read_bytes()
    if not data or len(data) > 20_000_000:
        raise Blocked("SOURCE_EMPTY_OR_TOO_LARGE:" + label)
    return data


def assess(manifest):
    _strict_object(manifest, frozenset(("schema", "event", "sources")), "manifest")
    if manifest["schema"] != SCHEMA:
        raise Blocked("UNSUPPORTED_NHL_FREEZE_SCHEMA")
    event = _strict_object(manifest["event"], EVENT_FIELDS, "event")
    for name in ("event_id", "home_team_id", "away_team_id",
                 "home_goalie_id", "away_goalie_id"):
        _id(event[name], name)
    if event["home_team_id"] == event["away_team_id"]:
        raise Blocked("DUPLICATE_TEAM_ID")
    if event["home_goalie_id"] == event["away_goalie_id"]:
        raise Blocked("DUPLICATE_GOALIE_ID")
    freeze = _utc(event["freeze_utc"], "freeze_utc")
    kickoff = _utc(event["kickoff_utc"], "kickoff_utc")
    if freeze >= kickoff:
        raise Blocked("FREEZE_NOT_BEFORE_PUCK_DROP")

    sources = manifest["sources"]
    if not isinstance(sources, list) or len(sources) != len(ROLES):
        raise Blocked("REQUIRED_ROLE_CENSUS_MISSING")
    seen_roles, seen_paths, verified = set(), set(), []
    saved_bytes = {}
    for row in sources:
        _strict_object(row, SOURCE_FIELDS, "source")
        role = row["role"]
        if type(role) is not str or role not in ROLES or role in seen_roles:
            raise Blocked("UNKNOWN_OR_DUPLICATE_ROLE")
        seen_roles.add(role)
        _id(row["provider"], "provider")
        path = _path(row["path"], role, allow_model=role == "MODEL")
        if str(path) in seen_paths:
            raise Blocked("SAME_RAW_FILE_REUSED_ACROSS_ROLES")
        seen_paths.add(str(path))
        required_hash = row["sha256"]
        if type(required_hash) is not str or not DIGEST.fullmatch(required_hash):
            raise Blocked("INVALID_SOURCE_HASH:" + role)

        through = _utc(row["data_through_utc"], role + ".data_through")
        published = _utc(row["published_utc"], role + ".published")
        observed = _utc(row["observed_utc"], role + ".observed")
        captured = _utc(row["captured_utc"], role + ".captured")
        if not (through <= published <= observed <= captured <= freeze):
            raise Blocked("LATE_OR_CONTRADICTORY_SOURCE_CLOCK:" + role)

        raw = _bytes(path, role)
        actual_hash = "sha256:" + sha256(raw).hexdigest()
        if actual_hash != required_hash:
            raise Blocked("SOURCE_BYTES_HASH_MISMATCH:" + role)
        saved_bytes[role] = (path, required_hash, raw)
        verified.append({
            "role": role, "sha256": actual_hash, "provider_claim": row["provider"],
            "data_through_utc": row["data_through_utc"],
            "published_utc_claim": row["published_utc"],
            "observed_utc_claim": row["observed_utc"],
            "captured_utc_claim": row["captured_utc"],
            "provider_authenticated": False,
        })

    if seen_roles != ROLES:
        raise Blocked("REQUIRED_ROLE_CENSUS_MISSING")
    lineup = _strict_object(_json(saved_bytes["LINEUP"][2], "LINEUP"),
                            LINEUP_FIELDS, "lineup")
    for name in ("event_id", "home_team_id", "away_team_id",
                 "home_goalie_id", "away_goalie_id"):
        if lineup[name] != event[name]:
            raise Blocked("LINEUP_" + name.upper() + "_MISMATCH")
    if lineup["home_confirmed"] is not True or lineup["away_confirmed"] is not True:
        raise Blocked("STARTING_GOALIE_NOT_CONFIRMED")
    if (_utc(lineup["observed_utc"], "lineup.observed") !=
            _utc(next(row["observed_utc"] for row in sources
                      if row["role"] == "LINEUP"), "LINEUP.observed")):
        raise Blocked("LINEUP_ORIGINAL_OBSERVATION_MISMATCH")

    # A second complete read protects against silent local file substitution
    # during validation. This does not authenticate provider authorship.
    for role, (path, required_hash, original) in saved_bytes.items():
        if _bytes(path, role) != original:
            raise Blocked("SOURCE_CHANGED_DURING_FREEZE:" + role)

    return {
        "schema": SCHEMA, "event_id": event["event_id"],
        "home_team_id": event["home_team_id"],
        "away_team_id": event["away_team_id"],
        "freeze_utc": event["freeze_utc"], "kickoff_utc": event["kickoff_utc"],
        "roles_present": sorted(seen_roles),
        "source_receipts": sorted(verified, key=lambda r: r["role"]),
        "status": "PAPER_0U_SOURCE_CLAIMS_UNAUTHENTICATED",
        "official_market_count": 0, "approved_stake_u": 0,
        "external_provider_authentication": False,
        "release_certified": False,
        "missing_proof": [
            "INDEPENDENT_PROVIDER_PUBLICATION_AND_OBSERVATION_AUTHENTICATION",
            "CANONICAL_ROSTER_GOALIE_ID_CROSSWALK_AT_FREEZE",
            "PROSPECTIVE_SOURCE_CAPTURE_AND_WORM_STORAGE",
            "AUTHENTIC_DK_AND_INDEPENDENT_BOOK_OFFERS",
            "CHRONOLOGICAL_MARKET_CALIBRATION_AND_CLV",
        ],
    }


def report_file(manifest_path, report_path):
    source = _path(manifest_path, "MANIFEST")
    dest = _path(report_path, "REPORT")
    if source == dest:
        raise Blocked("MANIFEST_EQUALS_OUTPUT")
    original = _bytes(source, "MANIFEST")
    report = assess(_json(original, "MANIFEST"))
    report["manifest_sha256"] = "sha256:" + sha256(original).hexdigest()
    payload = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False)
               + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(dest, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest_json")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    report = report_file(args.manifest_json, args.report)
    print(json.dumps({"status": report["status"], "release_certified": False,
                      "approved_stake_u": 0, "event_id": report["event_id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
