"""Prospective, offline Torvik-to-CBBD ID bridge (RESEARCH PAPER / 0u).

Accepts locally archived, exact-byte CSV exports and original CBBD game response.
NO automatic name matching. NO claims of externally attested publisher dates.
NO prices, model fitting, or production betting admission.
"""
from __future__ import annotations

from collections import Counter
import argparse
import csv
from datetime import datetime, timezone, timedelta, date
import hashlib
import io
import json
import math
from pathlib import Path

from cbbd_prospective_capture import (
    safe_path, iso, utc, decoded, Hold
)
from torvik_point_in_time_baseline import project, Blocked

ROOT = Path(__file__).resolve().parents[2]
KINDS = {
    "TORVIK_RATINGS": {"team", "adj_o", "adj_d", "adj_tempo"},
    "CBBD_ID_CROSSWALK": {"cbbd_id", "torvik_team"},
    "HCA_RESEARCH": {"cbbd_id", "home_court_points"},
}


def _csv_rows(raw, kind):
    if kind not in KINDS:
        raise Hold("SOURCE_KIND_NOT_ALLOWED")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or any(not h or h.strip() != h for h in headers):
            raise Hold("DUPLICATE_OR_INVALID_CSV_HEADERS")
        if not KINDS[kind].issubset(headers):
            raise Hold("SOURCE_CSV_MISSING_REQUIRED_HEADERS")
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise Hold("INVALID_SOURCE_CSV") from exc
    if not rows or any(None in r for r in rows):
        raise Hold("EMPTY_CSV_OR_TOO_MANY_FIELDS")
    return rows


def _float(value, name, lo, hi):
    if not isinstance(value, str) or not value.strip():
        raise Hold(name + ": MISSING_VALUE")
    try:
        val = float(value)
    except ValueError as exc:
        raise Hold(name + ": NOT_NUMBER") from exc
    if not math.isfinite(val) or not lo <= val <= hi:
        raise Hold(name + ": OUT_OF_RANGE")
    return val


def _team_id(s):
    if type(s) is not str or not s.isascii() or not s.isdecimal():
        raise Hold("CBBD_TEAM_ID_MUST_BE_EXACT_INTEGER_STRING")
    i = int(s)
    if i < 1 or str(i) != s:
        raise Hold("CBBD_TEAM_ID_NONCANONICAL")
    return s


def archive_csv(*, source_path, private_dir, kind, season, clock=None):
    """Record first local observation of an existing file; never backdate."""
    if kind not in KINDS:
        raise Hold("SOURCE_KIND_NOT_ALLOWED")
    if type(season) is not int or not 2000 <= season <= 2100:
        raise Hold("INVALID_SEASON")
    source = safe_path(source_path)
    destination = safe_path(private_dir)
    if destination.exists() and not destination.is_dir():
        raise Hold("DESTINATION_NOT_DIRECTORY")
    raw = source.read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        raise Hold("CSV_TOO_LARGE")
    records = _csv_rows(raw, kind)
    seen = set()
    for row in records:
        if kind == "TORVIK_RATINGS":
            team = row["team"]
            if not team or team.strip() != team:
                raise Hold("TORVIK_NAME_MISSING_OR_PADDED")
            key = team
            for column in ("adj_o", "adj_d", "adj_tempo"):
                _float(row[column], column, 15 if column == "adj_tempo" else 1,
                       120 if column == "adj_tempo" else 250)
        else:
            key = _team_id(row["cbbd_id"])
            if kind == "CBBD_ID_CROSSWALK" and not row["torvik_team"].strip():
                raise Hold("CROSSWALK_NAME_REQUIRED")
            if kind == "HCA_RESEARCH":
                _float(row["home_court_points"], "home_court_points", -20, 20)
        if key in seen:
            raise Hold("DUPLICATE_SOURCE_ID_OR_TEAM")
        seen.add(key)
    if kind == "TORVIK_RATINGS" and len(records) < 300:
        raise Hold("INCOMPLETE_TORVIK_D1_TEAM_UNIVERSE")
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if not isinstance(now, datetime) or now.utcoffset() != timedelta(0):
        raise Hold("ARCHIVE_CLOCK_NOT_UTC")
    # If toRvik's day label exists, it cannot be in the future relative to
    # this observation, even though it does NOT certify publisher hour.
    if kind == "TORVIK_RATINGS" and "date" in records[0]:
        for row in records:
            label = row.get("date", "")
            try:
                parsed = (date.fromisoformat(label) if "-" in label else
                          datetime.strptime(label, "%Y%m%d").date())
            except (TypeError, ValueError) as exc:
                raise Hold("INVALID_TORVIK_ARCHIVE_DATE") from exc
            if parsed > now.date() or parsed.year + (parsed.month >= 8) != season:
                raise Hold("TORVIK_DATE_AFTER_CAPTURE_OR_WRONG_SEASON")
    when = iso(now)
    digest = hashlib.sha256(raw).hexdigest()
    stem = kind.lower() + "_" + str(season) + "_" + now.strftime("%Y%m%dT%H%M%S%fZ")
    original = destination / (stem + ".csv")
    receipt = destination / (stem + ".manifest.json")
    if original.exists() or receipt.exists():
        raise FileExistsError("ARCHIVE_ALREADY_EXISTS")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {"format": "CBB_LOCAL_CSV_RECEIPT_V1", "kind": kind,
                "season": season, "source_sha256": digest,
                "source_bytes": len(raw), "rows": len(records),
                "local_observed_utc": when,
                "publication_basis": "LOCAL_FILE_OBSERVATION_NOT_PUBLISHER_ATTESTATION",
                "status": "RESEARCH_ONLY_PAPER_0U"}
    with original.open("xb") as f:
        f.write(raw)
        f.flush()
    with receipt.open("x", encoding="utf-8") as f:
        json.dump(manifest, f, sort_keys=True, indent=2)
        f.write("\n")
    return {"raw_path": str(original), "manifest_path": str(receipt),
            "sha256": digest, "rows": len(records),
            "observed_utc": when, "status": manifest["status"]}


def _read_local(raw_path, receipt_path, kind, season):
    rawp, recp = safe_path(raw_path), safe_path(receipt_path)
    raw = rawp.read_bytes()
    manifest = json.loads(recp.read_text("utf-8"))
    if manifest.get("format") != "CBB_LOCAL_CSV_RECEIPT_V1" or \
       manifest.get("kind") != kind or manifest.get("season") != season:
        raise Hold("CSV_MANIFEST_IDENTITY_MISMATCH")
    if hashlib.sha256(raw).hexdigest() != manifest.get("source_sha256") or \
       len(raw) != manifest.get("source_bytes"):
        raise Hold("CSV_ORIGINAL_BYTE_HASH_MISMATCH")
    records = _csv_rows(raw, kind)
    if len(records) != manifest.get("rows"):
        raise Hold("CSV_MANIFEST_ROW_COUNT_MISMATCH")
    return records, manifest


def _source(rec, id_value, season):
    asof = utc(rec["local_observed_utc"], "local_observed_utc")
    return {"team_id": id_value, "season": season,
            "data_through_utc": iso(asof),
            "published_utc": iso(asof),
            "captured_utc": iso(asof),
            "source_sha256": rec["source_sha256"]}


def _game_id(x):
    if type(x) is not int or x < 1:
        raise Hold("CBBD_GAME_ID_INVALID")
    return str(x)


def _lookups(rating_rows, map_rows, hca_rows):
    ratings = {}
    for r in rating_rows:
        name = r["team"]
        if name in ratings:
            raise Hold("TORVIK_DUPLICATE_TEAM")
        ratings[name] = {n: _float(r[n], n, 15 if n == "adj_tempo" else 1,
                                     120 if n == "adj_tempo" else 250)
                         for n in ("adj_o", "adj_d", "adj_tempo")}
    if len(ratings) < 300:
        raise Hold("TORVIK_UNIVERSE_INCOMPLETE")
    crosswalk, targets = {}, set()
    for r in map_rows:
        ident, name = _team_id(r["cbbd_id"]), r["torvik_team"]
        if ident in crosswalk or name in targets:
            raise Hold("CROSSWALK_NOT_BIJECTIVE")
        if name not in ratings:
            raise Hold("CROSSWALK_TARGET_NOT_IN_FROZEN_RATINGS")
        crosswalk[ident] = name
        targets.add(name)
    hca = {}
    for r in hca_rows:
        ident = _team_id(r["cbbd_id"])
        if ident in hca:
            raise Hold("HCA_DUPLICATE_TEAM")
        hca[ident] = _float(r["home_court_points"], "home_court_points", -20, 20)
    return ratings, crosswalk, hca


def project_scheduled(*, schedule_raw, schedule_manifest,
                      ratings_raw, ratings_manifest,
                      map_raw, map_manifest,
                      hca_raw, hca_manifest, output_path,
                      now=None, max_source_age_hours=24):
    """One immutable PAPER projection or explicit blocked reason per CBBD event."""
    target = safe_path(output_path)
    if target.exists():
        raise FileExistsError("CREATE_ONLY_PREGAME_BOARD")
    if type(max_source_age_hours) not in (int, float) or \
       not math.isfinite(max_source_age_hours) or not 0 < max_source_age_hours <= 168:
        raise Hold("INVALID_MAX_SOURCE_AGE")
    import cbbd_prospective_capture as cbbd
    sr, sm = safe_path(schedule_raw).read_bytes(), \
             json.loads(safe_path(schedule_manifest).read_text("utf-8"))
    if sm.get("format") != "CBBD_GAMES_CAPTURE_V1" or \
       sm.get("documented_endpoint") != cbbd.BASE or \
       sm.get("source_sha256") != hashlib.sha256(sr).hexdigest() or \
       sm.get("source_bytes") != len(sr):
        raise Hold("SCHEDULE_SOURCE_RECEIPT_MISMATCH")
    schedule = decoded(sr)
    if len(schedule) != sm.get("returned_rows"):
        raise Hold("SCHEDULE_ROW_COUNT_MISMATCH")
    season = sm.get("season")
    if type(season) is not int:
        raise Hold("SCHEDULE_SEASON_INVALID")
    collections = (
        _read_local(ratings_raw, ratings_manifest, "TORVIK_RATINGS", season),
        _read_local(map_raw, map_manifest, "CBBD_ID_CROSSWALK", season),
        _read_local(hca_raw, hca_manifest, "HCA_RESEARCH", season),
    )
    (rating_rows, rm), (map_rows, mm), (hca_rows, hm) = collections
    ratings, crosswalk, hca = _lookups(rating_rows, map_rows, hca_rows)
    clock = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(clock, datetime) or clock.utcoffset() != timedelta(0):
        raise Hold("MODEL_CLOCK_NOT_UTC")
    freeze = iso(clock)
    # Current observations only. Historical scheduled games fetched today cannot
    # be relabeled as historical pre-tip forecasts.
    for receipt in (sm, rm, mm, hm):
        captured = utc(receipt.get("local_observed_utc"), "local_observed_utc")
        if captured > clock:
            raise Hold("SOURCE_CAPTURE_IS_AFTER_MODEL_FREEZE")
    if (clock - utc(sm["local_observed_utc"], "schedule_capture")).total_seconds() > max_source_age_hours * 3600 or \
       (clock - utc(rm["local_observed_utc"], "rating_capture")).total_seconds() > max_source_age_hours * 3600:
        raise Hold("SCHEDULE_OR_RATINGS_TOO_STALE")
    league_off = sum(x["adj_o"] for x in ratings.values()) / len(ratings)
    league_tempo = sum(x["adj_tempo"] for x in ratings.values()) / len(ratings)
    model_hash = hashlib.sha256((ROOT / "models/cbb/torvik_point_in_time_baseline.py").read_bytes()).hexdigest()
    ids = Counter(x.get("id") for x in schedule if isinstance(x, dict) and type(x.get("id")) is int)
    results = []
    for index, g in enumerate(schedule):
        row = {"input_index": index, "status": "BLOCKED", "official": False,
               "stake_u": 0, "expected_value": None}
        try:
            if not isinstance(g, dict):
                raise Hold("SCHEDULE_ROW_INVALID")
            ident = _game_id(g.get("id"))
            row["game_id"] = ident
            if ids[g["id"]] > 1:
                raise Hold("DUPLICATE_CBBD_EVENT_ALL_COPIES")
            if g.get("season") != season or g.get("startTimeTbd") is not False:
                raise Hold("SEASON_OR_UNCONFIRMED_TIPOFF")
            if g.get("status") != "scheduled":
                raise Hold("NOT_PREGAME_SCHEDULED")
            if type(g.get("neutralSite")) is not bool:
                raise Hold("MISSING_NEUTRAL_SITE")
            tip = utc(g.get("startDate"), "game.startDate")
            if tip <= clock:
                raise Hold("PREGAME_FREEZE_TOO_LATE")
            if tip.year + (tip.month >= 8) != season:
                raise Hold("TIPOFF_SEASON_MISMATCH")
            hid = _team_id(str(g["homeTeamId"])) if type(g.get("homeTeamId")) is int else ""
            aid = _team_id(str(g["awayTeamId"])) if type(g.get("awayTeamId")) is int else ""
            if hid == aid:
                raise Hold("HOME_AWAY_ID_SAME")
            if hid not in crosswalk or aid not in crosswalk:
                raise Hold("EXACT_CBBD_TO_TORVIK_MAPPING_MISSING")
            if not g["neutralSite"] and hid not in hca:
                raise Hold("HCA_INPUT_MISSING_NO_DEFAULT")
            entry = {"game_id": ident, "season": season,
                     "home_team_id": hid, "away_team_id": aid,
                     "neutral": g["neutralSite"],
                     "freeze_utc": freeze, "tipoff_utc": iso(tip),
                     "model_sha256": model_hash}
            def team_features(cbbd_id):
                source = _source(rm, cbbd_id, season)
                return {**source, **ratings[crosswalk[cbbd_id]]}
            league = {**_source(rm, "LEAGUE", season),
                      "league_adj_o": league_off,
                      "league_tempo": league_tempo}
            bonus = None if g["neutralSite"] else {
                **_source(hm, hid, season),
                "home_court_points": hca[hid],
            }
            output = project(entry, team_features(hid), team_features(aid),
                             league, bonus)
            row.update(output)
        except (Hold, Blocked, TypeError, ValueError, KeyError) as exc:
            row["reason"] = str(exc)
        results.append(row)
    report = {"status": "CBB_POINT_IN_TIME_RESEARCH_ONLY_UNAUTHENTICATED_PAPER_0U",
              "official": False, "stake_u": 0,
              "season": season, "freeze_utc": freeze,
              "input_rows": len(schedule),
              "projected_rows": sum(x["status"] == "PAPER_NON_COUNTED_UNCALIBRATED" for x in results),
              "source_sha256": {"schedule": sm["source_sha256"],
                                "torvik": rm["source_sha256"],
                                "crosswalk": mm["source_sha256"],
                                "hca": hm["source_sha256"]},
              "results": results,
              "warnings": [
                "LOCAL_CSV_OBSERVATION_NOT_AUTHENTICATED_PROVIDER_PUBLISH_TIME",
                "NO_FUZZY_TEAM_NAMES_OR_FREE_HCA_DEFAULT",
                "NO_ODDS_CALIBRATION_WIN_PROBABILITY_OR_STAKES",
                "LATE_OR_MISSING_PROVIDERS_BLOCK_INSTEAD_OF_RECONSTRUCTING_HISTORY",
              ]}
    with target.open("x", encoding="utf-8") as f:
        json.dump(report, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    return report



def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest="action", required=True)
    arc = subs.add_parser("archive-csv")
    arc.add_argument("--source", required=True)
    arc.add_argument("--private-dir", required=True)
    arc.add_argument("--kind", required=True, choices=tuple(KINDS))
    arc.add_argument("--season", required=True, type=int)
    gen = subs.add_parser("project")
    for name in ("schedule_raw", "schedule_manifest",
                 "ratings_raw", "ratings_manifest",
                 "map_raw", "map_manifest",
                 "hca_raw", "hca_manifest", "output_path"):
        gen.add_argument("--" + name.replace("_", "-"), required=True)
    gen.add_argument("--max-source-age-hours", type=float, default=24)
    args = p.parse_args(argv)
    if args.action == "archive-csv":
        result = archive_csv(source_path=args.source, private_dir=args.private_dir,
                             kind=args.kind, season=args.season)
    else:
        result = project_scheduled(
            **{name: getattr(args, name) for name in (
                "schedule_raw","schedule_manifest","ratings_raw","ratings_manifest",
                "map_raw","map_manifest","hca_raw","hca_manifest","output_path")},
            max_source_age_hours=args.max_source_age_hours)
        result = {"status": result["status"], "input_rows": result["input_rows"],
                  "projected_rows": result["projected_rows"],
                  "output_path": str(safe_path(args.output_path))}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
