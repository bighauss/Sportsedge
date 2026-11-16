"""Read-only Hoop-Explorer export companion for CBB research (stdlib only).

No undocumented HTTP calls, credentials, betting prices, model-weight changes or
official market admission. A local manifest is NOT provider attestation: timestamps
are merely checked for self-consistency and source bytes are checksummed.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re

UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
HEX = re.compile(r"^[0-9a-fA-F]{64}$")
ID = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
REQUIRED = {
    "player": {"player_id", "team_id", "season", "minutes"},
    "lineup": {"lineup_id", "team_id", "season", "possessions", "net_rating", "player_ids"},
}
OPTIONAL = {
    "player": {"name", "rapm", "usage_pct", "turnover_pct", "three_rate_pct",
               "three_pct", "orb_pct", "assist_pct", "rim_rate_pct", "on_off"},
    "lineup": set(),
}
SCALES = {"rapm": 3.0, "usage_pct": 8.0, "turnover_pct": 7.0,
          "three_rate_pct": 20.0, "three_pct": 12.0, "orb_pct": 7.0,
          "assist_pct": 12.0, "rim_rate_pct": 20.0, "on_off": 8.0}
LIMITS = {"minutes": (0, 6000), "possessions": (1, 30000),
          "net_rating": (-100, 100), "rapm": (-30, 30), "on_off": (-100, 100),
          **{k: (0, 100) for k in SCALES if k not in ("rapm", "on_off")}}
MAX_BYTES = 20_000_000


class Blocked(ValueError):
    """Fail closed; never repair identifiers, missing values or clocks silently."""


def clock(value, name):
    if not isinstance(value, str) or not UTC.fullmatch(value):
        raise Blocked(f"{name}: UTC_Z_REQUIRED")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise Blocked(f"{name}: INVALID_UTC") from exc


def num(value, name, low, high):
    if value is None or value == "" or isinstance(value, bool):
        raise Blocked(f"{name}: MISSING_OR_INVALID_NUMBER")
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise Blocked(f"{name}: INVALID_NUMBER") from exc
    if not math.isfinite(number) or not low <= number <= high:
        raise Blocked(f"{name}: NUMBER_OUT_OF_RANGE")
    return number


def identity(value, name):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise Blocked(f"{name}: CANONICAL_ID_REQUIRED")
    return value


def season_year(value, name):
    if isinstance(value, bool) or str(value) not in {str(y) for y in range(2018, 2101)}:
        raise Blocked(f"{name}: INVALID_SEASON_END_YEAR")
    return int(value)


def metadata(manifest, raw, kind, freeze_utc, tipoff_utc, *, exploratory=False):
    if not isinstance(manifest, dict):
        raise Blocked("MANIFEST_REQUIRED")
    if manifest.get("provider") != "hoop_explorer":
        raise Blocked("PROVIDER_MISMATCH")
    if manifest.get("kind") != kind or manifest.get("format") not in ("csv", "json"):
        raise Blocked("EXPORT_KIND_OR_FORMAT_MISMATCH")
    if manifest.get("access_basis") not in ("manual_user_export", "creator_permission"):
        raise Blocked("AUTHORIZED_EXPORT_BASIS_REQUIRED")
    url = manifest.get("source_url")
    if not isinstance(url, str) or not url.startswith("https://hoop-explorer.com/"):
        raise Blocked("SOURCE_URL_REQUIRED")
    if not isinstance(manifest.get("scope_id"), str) or not manifest["scope_id"].strip():
        raise Blocked("SCOPE_ID_REQUIRED")
    sha = hashlib.sha256(raw).hexdigest()
    if not isinstance(manifest.get("sha256"), str) or not HEX.fullmatch(manifest["sha256"]):
        raise Blocked("SOURCE_SHA256_REQUIRED")
    if manifest["sha256"].lower() != sha:
        raise Blocked("EXPORT_HASH_MISMATCH")
    season = season_year(manifest.get("season"), "manifest.season")
    if exploratory is not True:
        freeze = clock(freeze_utc, "freeze_utc")
        tip = clock(tipoff_utc, "tipoff_utc")
        through = clock(manifest.get("data_through_utc"), "data_through_utc")
        published = clock(manifest.get("published_utc"), "published_utc")
        captured = clock(manifest.get("captured_utc"), "captured_utc")
        if not (through <= published <= captured <= freeze < tip):
            raise Blocked("LOOKAHEAD_OR_SOURCE_CLOCK_ORDER")
        # Prior-season player baselines are valid for a future matchup if
        # the actual source timestamps precede the freeze.
        if season > tip.year + int(tip.month >= 8):
            raise Blocked("SOURCE_SEASON_AFTER_GAME_SEASON")
    columns = manifest.get("columns")
    if not isinstance(columns, dict) or not REQUIRED[kind].issubset(columns):
        raise Blocked("REQUIRED_EXPLICIT_COLUMN_MAP_MISSING")
    if set(columns) - REQUIRED[kind] - OPTIONAL[kind]:
        raise Blocked("UNKNOWN_CANONICAL_FIELD")
    if any(not isinstance(v, str) or not v for v in columns.values()):
        raise Blocked("INVALID_COLUMN_MAP")
    if len(set(columns.values())) != len(columns):
        raise Blocked("REUSED_SOURCE_COLUMN")
    return sha, season, columns


def read_rows(raw, fmt):
    try:
        text = raw.decode("utf-8-sig")
        if fmt == "csv":
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise Blocked("INVALID_CSV_HEADER")
            return list(reader), set(reader.fieldnames)
        payload = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        raise Blocked("UNREADABLE_EXPORT") from exc
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not all(isinstance(x, dict) for x in rows):
        raise Blocked("JSON_ROWS_ARRAY_REQUIRED")
    return rows, set().union(*(set(x) for x in rows)) if rows else set()


def load_export(export_path, manifest_path, *, kind, freeze_utc=None, tipoff_utc=None,
                archive_dir=None, exploratory=False):
    raw = Path(export_path).read_bytes()
    if not raw or len(raw) > MAX_BYTES:
        raise Blocked("EXPORT_EMPTY_OR_TOO_LARGE")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    sha, season, columns = metadata(manifest, raw, kind, freeze_utc, tipoff_utc,
                                    exploratory=exploratory)
    rows, available = read_rows(raw, manifest["format"])
    if not rows or not set(columns.values()).issubset(available):
        raise Blocked("MISSING_MAPPED_EXPORT_FIELDS")
    seen = set()
    normalized = []
    for n, source in enumerate(rows):
        row = {}
        for canon, external in columns.items():
            if external not in source:
                raise Blocked(f"ROW_{n}: MAPPED_FIELD_MISSING")
            value = source[external]
            if canon in ("player_id", "team_id", "lineup_id"):
                row[canon] = identity(value, f"row_{n}.{canon}")
            elif canon == "season":
                row[canon] = season_year(value, f"row_{n}.season")
                if row[canon] != season:
                    raise Blocked(f"ROW_{n}: MIXED_SEASONS")
            elif canon == "player_ids":
                if not isinstance(value, str):
                    raise Blocked(f"ROW_{n}: PLAYER_IDS_NOT_STRING")
                members = [identity(x.strip(), "lineup_member") for x in value.split(";")]
                if len(members) != 5 or len(set(members)) != 5:
                    raise Blocked(f"ROW_{n}: FIVE_DISTINCT_LINEUP_MEMBERS_REQUIRED")
                row[canon] = sorted(members)
            elif canon == "name":
                row[canon] = str(value).strip()[:160] if value is not None else ""
            elif canon in LIMITS:
                row[canon] = None if value in (None, "") and canon in OPTIONAL[kind] else num(
                    value, f"row_{n}.{canon}", *LIMITS[canon])
        key = row["player_id"] if kind == "player" else row["lineup_id"]
        if key in seen:
            raise Blocked(f"ROW_{n}: DUPLICATE_ENTITY_ID")
        seen.add(key)
        normalized.append(row)
    archive = None
    if archive_dir is not None:
        folder = Path(archive_dir)
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / (sha + "." + manifest["format"])
        if destination.exists() and destination.read_bytes() != raw:
            raise Blocked("ARCHIVE_HASH_COLLISION")
        if not destination.exists():
            destination.write_bytes(raw)
        archive = str(destination)
    evidence = {"provider": "hoop_explorer", "scope_id": manifest["scope_id"],
                "season": season, "source_url": manifest["source_url"], "sha256": sha,
                "captured_utc": manifest.get("captured_utc"),
                "published_utc": manifest.get("published_utc"),
                "data_through_utc": manifest.get("data_through_utc"),
                "access_basis_user_asserted": manifest["access_basis"],
                "clock_consistent_not_source_authenticated": not exploratory,
                "point_in_time_admissible": False,
                "provenance_status": ("UNVERIFIED_EXPLORATORY_NO_PIT" if exploratory
                                      else "USER_CLOCK_COHERENT_NOT_AUTHENTICATED"),
                "archive_path": archive, "rows": len(normalized), "kind": kind}
    if kind == "lineup":
        evidence["disjoint_partition_user_asserted"] = (
            manifest.get("disjoint_partition") is True)
    return normalized, evidence


def _distance(a, b, features, min_fields):
    shared = [k for k in features if a.get(k) is not None and b.get(k) is not None]
    if len(shared) < min_fields:
        return None
    score = math.sqrt(sum(((a[k]-b[k])/SCALES[k])**2 for k in shared) / len(shared))
    return {"distance_unvalidated": round(score, 5), "fields": shared,
            "field_count": len(shared)}


def similar_players(players, player_id, *, limit=5):
    identity(player_id, "target_player_id")
    matches = [p for p in players if p["player_id"] == player_id]
    if len(matches) != 1:
        raise Blocked("TARGET_PLAYER_NOT_UNIQUELY_PRESENT")
    target = matches[0]
    results = []
    for p in players:
        if p["player_id"] == player_id:
            continue
        dist = _distance(target, p, SCALES, 4)
        if dist:
            results.append({"player_id": p["player_id"], "name": p.get("name", ""),
                            "team_id": p["team_id"], "minutes": p["minutes"],
                            "low_minutes_warning": p["minutes"] < 200, **dist})
    results.sort(key=lambda x: (x["distance_unvalidated"], x["player_id"]))
    return {"target_player_id": player_id, "target_minutes": target["minutes"],
            "target_low_minutes_warning": target["minutes"] < 200,
            "nearest": results[:limit], "description": "Descriptive distance; not win/EV prediction"}


def roster_fit(players, role_profile):
    if not isinstance(role_profile, dict) or not isinstance(role_profile.get("targets"), dict):
        raise Blocked("EXPLICIT_ROLE_TARGETS_REQUIRED")
    desired = role_profile["targets"]
    if len(desired) < 3 or not set(desired).issubset(SCALES):
        raise Blocked("ROLE_REQUIRES_THREE_VALID_FEATURES")
    desired = {k: num(v, f"target.{k}", *LIMITS[k]) for k, v in desired.items()}
    results = []
    for p in players:
        distance = _distance(p, desired, desired, len(desired))
        if distance:
            results.append({"player_id": p["player_id"], "team_id": p["team_id"],
                            "name": p.get("name", ""), "minutes": p["minutes"],
                            "low_minutes_warning": p["minutes"] < 200, **distance})
    results.sort(key=lambda x: (x["distance_unvalidated"], x["player_id"]))
    return {"profile": role_profile.get("name", "user_supplied_targets"),
            "ranked_descriptive_fit": results, "no_causal_or_betting_claim": True}


def pad_rate(observed, possessions, prior, k):
    """Explicit SportsEdge empirical-Bayes heuristic, NOT Hoop-Explorer's padding."""
    observed = num(observed, "net_rating", -100, 100)
    possessions = num(possessions, "possessions", 1, 30000)
    prior = num(prior, "prior_net_rating", -100, 100)
    k = num(k, "pad_k", 1, 100000)
    return prior + possessions / (possessions + k) * (observed-prior)


def lineup_context(lineups, team_id, player_id, *, prior_net, pad_k,
                   partition_verified=False):
    identity(team_id, "team_id")
    identity(player_id, "player_id")
    if partition_verified is not True:
        raise Blocked("WOWY_REQUIRES_DISJOINT_FULL_LINEUP_PARTITION")
    selected = [x for x in lineups if x["team_id"] == team_id]
    if not selected:
        raise Blocked("NO_LINEUPS_FOR_TEAM")
    on = [x for x in selected if player_id in x["player_ids"]]
    off = [x for x in selected if player_id not in x["player_ids"]]
    if not on or not off:
        raise Blocked("WOWY_REQUIRES_BOTH_ON_AND_OFF_LINEUPS")

    def summarize(group):
        possessions = sum(x["possessions"] for x in group)
        raw = sum(x["possessions"]*x["net_rating"] for x in group) / possessions
        return {"lineup_rows": len(group), "possessions": possessions,
                "net_rating_raw": round(raw, 4),
                "net_rating_padded": round(pad_rate(raw, possessions, prior_net, pad_k), 4),
                "low_sample_warning": possessions < 200}
    on_sum, off_sum = summarize(on), summarize(off)
    return {"player_id": player_id, "team_id": team_id,
            "on": on_sum, "off": off_sum,
            "raw_on_minus_off": round(on_sum["net_rating_raw"]-off_sum["net_rating_raw"], 4),
            "padded_on_minus_off": round(
                on_sum["net_rating_padded"]-off_sum["net_rating_padded"], 4),
            "prior_net_rating_user_supplied": prior_net,
            "pad_k_heuristic_not_fitted": pad_k,
            "method": "Possession weighted disjoint five-player lineups; shrink each arm to same team prior",
            "causal_effect_estimated": False}


def research_report(players, player_evidence, *, target_player_id,
                    lineups=None, lineup_evidence=None, team_id=None,
                    role_profile=None, prior_net=None, pad_k=None):
    if lineups is not None and (lineup_evidence is None or team_id is None
                                or prior_net is None or pad_k is None):
        raise Blocked("LINEUP_EVIDENCE_TEAM_PRIOR_AND_K_REQUIRED")
    if lineups is not None:
        target = [p for p in players if p["player_id"] == target_player_id]
        if len(target) != 1 or target[0]["team_id"] != team_id:
            raise Blocked("LINEUP_TARGET_PLAYER_TEAM_IDENTITY_MISMATCH")
    return {
        "status": "PAPER_NON_COUNTED_RESEARCH_ONLY", "sport": "CBB",
        "official": False, "stake_u": 0, "pricing_enabled": False,
        "model_weights_modified": False,
        "source_authenticated": False,
        "caveat": "User export and manifest do not prove historical point-in-time availability; exploratory mode cannot be used for pregame or historical pricing",
        "evidence": [player_evidence] + ([lineup_evidence] if lineup_evidence else []),
        "similar_players": similar_players(players, target_player_id),
        "roster_fit": roster_fit(players, role_profile) if role_profile else None,
        "lineup_wowy": lineup_context(
            lineups, team_id, target_player_id, prior_net=prior_net,
            pad_k=pad_k,
            partition_verified=lineup_evidence["disjoint_partition_user_asserted"]
        ) if lineups is not None else None,
        "ai_context_contract": {
            "use_only_evidence_in_this_report": True,
            "state_uncertainty_and_missingness": True,
            "do_not_invent_stats_predictions_or_betting_edges": True,
        },
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--players-export", required=True)
    p.add_argument("--players-manifest", required=True)
    p.add_argument("--lineups-export")
    p.add_argument("--lineups-manifest")
    p.add_argument("--target-player-id", required=True)
    p.add_argument("--team-id")
    p.add_argument("--role-profile", help="JSON with explicit target statistical profile")
    p.add_argument("--prior-net", type=float)
    p.add_argument("--pad-k", type=float)
    p.add_argument("--freeze-utc")
    p.add_argument("--tipoff-utc")
    p.add_argument("--exploratory", action="store_true",
                   help="No historical as-of assertion: unverified data, descriptive research only")
    p.add_argument("--archive-dir")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    if bool(args.lineups_export) != bool(args.lineups_manifest):
        p.error("lineups export and manifest must be supplied together")
    if args.lineups_export and not args.team_id:
        p.error("lineup analysis requires --team-id")
    if not args.exploratory and (not args.freeze_utc or not args.tipoff_utc):
        p.error("pregame research requires --freeze-utc and --tipoff-utc")
    players, pe = load_export(
        args.players_export, args.players_manifest, kind="player",
        freeze_utc=args.freeze_utc, tipoff_utc=args.tipoff_utc,
        archive_dir=args.archive_dir, exploratory=args.exploratory)
    lineups, le = None, None
    if args.lineups_export:
        lineups, le = load_export(
            args.lineups_export, args.lineups_manifest, kind="lineup",
            freeze_utc=args.freeze_utc, tipoff_utc=args.tipoff_utc,
            archive_dir=args.archive_dir, exploratory=args.exploratory)
        if le["scope_id"] != pe["scope_id"] or le["season"] != pe["season"]:
            raise Blocked("LINEUP_AND_PLAYER_SOURCE_SCOPE_OR_SEASON_DIFFER")
    profile = json.loads(Path(args.role_profile).read_text()) if args.role_profile else None
    report = research_report(
        players, pe, target_player_id=args.target_player_id,
        lineups=lineups, lineup_evidence=le, team_id=args.team_id,
        role_profile=profile, prior_net=args.prior_net, pad_k=args.pad_k)
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"RESEARCH_ONLY / 0u: {destination}")


if __name__ == "__main__":
    main()
