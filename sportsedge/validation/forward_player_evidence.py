"""Prospective NFL player forecast freeze and final-result grading — PAPER/0u.

Freeze is CREATE-ONLY and requires event fixture, source files, original bytes
hashes, lineup file, and a model-produced player forecast CSV. A successful
file write is *tamper-evident*, not independent source/time authentication.
Grade reads exactly those frozen predictions and a separately hashed observed
final box-stat CSV. Missing player outcomes remain UNRESOLVED, never zero.

Never produces sportsbook prices, bets, bankroll allocations or official cards.
Historical reconstructed releases cannot be promoted by supplying early
timestamps in a self-authored JSON manifest.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
import argparse
import csv
import io
import json
import math
import os
import re

from sportsedge.markets.player_forecast_intake import (
    REQUIRED as FORECAST_FIELDS,
    FORBIDDEN as FORECAST_FORBIDDEN,
    ingest_player_forecast_csv,
)
from sportsedge.markets.ngs_public_research_smoke import NFL_TEAMS
from sportsedge.markets.source_ingestion import SOURCES, parse_snapshot_bytes
from sportsedge.markets.allmarkets_research import STAT_NAMES

SHA = re.compile(r"sha256:[a-f0-9]{64}\Z")
IDS = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
SOURCE_KEYS = frozenset({
    "source_id", "path", "raw_sha256", "data_through_utc",
    "observed_at_utc", "captured_at_utc",
})
FREEZE_KEYS = frozenset({
    "schema", "event_id", "home_id", "away_id", "start_utc", "forecast_asof_utc",
    "forecast_file", "model_artifact", "lineup_file", "source_files",
    "roster_player_ids", "odds_observed_at_utc", "season", "week",
})
RESULT_KEYS = frozenset({
    "schema", "frozen_capture_path", "frozen_capture_sha256",
    "event_id", "event_final_at_utc", "result_file",
})
FILE_KEYS = frozenset({"path", "raw_sha256"})
LINEUP_FILE_KEYS = FILE_KEYS | frozenset({
    "source_name", "observed_at_utc", "captured_at_utc",
})
RESULT_FILE_KEYS = frozenset({
    "path", "raw_sha256", "source_id", "observed_at_utc", "captured_at_utc",
})
LINEUP_KEYS = frozenset({"event_id", "player_id", "team_id", "status"})
RESULT_FIELDS = ("event_id", "player_id", "team_id", "stat", "actual")
RESEARCH_FREEZE = "sportsedge-nfl-player-forward-freeze-v2"
RESEARCH_GRADE = "sportsedge-nfl-player-forward-grade-v2"
LINEUP_STATES = {"ACTIVE", "INACTIVE", "UNCONFIRMED"}
# Source label policy, NOT authentication of the purported upstream publisher.
LINEUP_SOURCES = frozenset({"NFL_CLUB_INACTIVES_CLAIM"})
MAX_LINEUP_AGE = timedelta(hours=2)
ZERO_KEYS = {"approved_stake_u": 0, "official_counted": 0, "card": None}


def _exact(x, keys, label):
    if type(x) is not dict or set(x) != set(keys):
        raise ValueError("INVALID_FIELDS:" + label)
    return x


def _time(raw):
    if not isinstance(raw, str) or not raw or len(raw) > 65:
        raise ValueError("UTC_TIME_REQUIRED")
    try:
        t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_UTC_TIME") from exc
    if t.tzinfo is None or t.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_TIME_REQUIRED")
    return t.astimezone(timezone.utc)


def _clock(now):
    t = datetime.now(timezone.utc) if now is None else now
    if (not isinstance(t, datetime) or t.tzinfo is None or
            t.utcoffset().total_seconds() != 0):
        raise ValueError("UTC_CLOCK_REQUIRED")
    return t.astimezone(timezone.utc)


def _id(raw, label):
    if not isinstance(raw, str) or not IDS.fullmatch(raw):
        raise ValueError("INVALID_STABLE_ID:" + label)
    return raw


def _sha(raw):
    if not isinstance(raw, str) or not SHA.fullmatch(raw):
        raise ValueError("INVALID_SHA256")
    return raw


def _raw_file(info, *, fields=FILE_KEYS):
    _exact(info, fields, "file")
    path = Path(info["path"])
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 120_000_000:
        raise ValueError("MISSING_OVERSIZE_OR_SYMLINKED_ORIGINAL_FILE")
    raw = path.read_bytes()
    digest = "sha256:" + sha256(raw).hexdigest()
    if not raw or digest != _sha(info["raw_sha256"]):
        raise ValueError("ORIGINAL_FILE_HASH_MISMATCH")
    return raw, digest


def _csv(raw, mandatory):
    try:
        doc = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(doc, newline=""), strict=True)
        headers = reader.fieldnames or []
        if (not headers or len(headers) != len(set(headers)) or
                any(h is None or h != h.strip() for h in headers) or
                not set(mandatory).issubset(headers)):
            raise ValueError("INVALID_CSV_SCHEMA")
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError("RAGGED_CSV")
        return headers, rows
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("MALFORMED_CSV") from exc


def _bytes_one_row(columns, row):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    writer.writerow(row)
    return out.getvalue().encode("utf-8")


def _strict_json(raw):
    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError("DUPLICATE_JSON_KEY:" + k)
            d[k] = v
        return d
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique)


def _write_private_create_only(path, obj):
    destination = Path(path)
    cwd = Path.cwd().resolve()
    absolute = destination.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    if (absolute == cwd or cwd in absolute.parents or
            absolute == repo_root or repo_root in absolute.parents):
        raise ValueError("PRIVATE_EVIDENCE_MUST_BE_OUTSIDE_REPOSITORY")
    if destination.is_symlink():
        raise ValueError("SYMLINK_OUTPUT_REFUSED")
    if not destination.parent.is_dir():
        raise ValueError("PRIVATE_DESTINATION_DIRECTORY_MISSING")
    raw = (json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
           + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(destination, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return "sha256:" + sha256(raw).hexdigest()


def _sources(items, *, freeze_time, event_start, odds_observed,
             season: int, week: int):
    if not isinstance(items, list) or not items or len(items) > 15:
        raise ValueError("SOURCE_RECEIPTS_REQUIRED")
    parsed = []
    seen = set()
    for row in items:
        _exact(row, SOURCE_KEYS, "source_receipt")
        source_id = _id(row["source_id"], "source_id")
        if source_id not in ("NFLVERSE_WEEKLY", "NFLVERSE_NGS"):
            raise ValueError("NFL_PLAYER_SOURCE_NOT_ALLOWLISTED")
        if (source_id, row["raw_sha256"]) in seen:
            raise ValueError("DUPLICATE_SOURCE_SNAPSHOT")
        seen.add((source_id, row["raw_sha256"]))
        raw, digest = _raw_file(row, fields=SOURCE_KEYS)
        observed = _time(row["observed_at_utc"])
        captured = _time(row["captured_at_utc"])
        through = _time(row["data_through_utc"])
        receipt, snapshots = parse_snapshot_bytes(
            source_id, raw, observed, captured)
        if not snapshots:
            raise ValueError("EMPTY_REGISTERED_SOURCE_ROWS")
        if source_id == "NFLVERSE_NGS":
            ngs_fields = {"season", "week", "season_type",
                          "player_gsis_id", "team_abbr"}
            if not ngs_fields.issubset(receipt.schema_columns):
                raise ValueError("NFL_NGS_SOURCE_ID_OR_WEEK_COLUMNS_MISSING")
        # A source's declared data-through timestamp alone is not proof of
        # its historical rows. Reject any current/future event-week row,
        # including the week=0 season-to-date NGS aggregate.
        for record in snapshots:
            try:
                y = int(record["season"])
                w = int(record["week"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("SOURCE_YEAR_OR_WEEK_INVALID") from exc
            if w < 0 or y > season or (y == season and
                    (w == 0 or w >= week)):
                raise ValueError("SOURCE_ROW_SAME_OR_FUTURE_GAME_WEEK")
        if not (through <= observed <= captured <= freeze_time < event_start):
            raise ValueError("SOURCE_CAPTURE_OR_PUBLICATION_TOO_LATE")
        if odds_observed is not None and captured > odds_observed:
            raise ValueError("SOURCE_AFTER_ODDS_QUOTE")
        parsed.append({
            "source_id": source_id, "sha256": digest,
            "observed_at_utc": observed.isoformat(),
            "captured_at_utc": captured.isoformat(),
            "data_through_utc": through.isoformat(),
        })
    return parsed


def freeze_player_forecasts(request, *, now=None):
    """Freeze every submitted row, including BLOCK rows, before kickoff.

    The returned dict always has zero stakes and never asserts source
    authentication. The caller must create-only persist before kickoff.
    """
    r = _exact(request, FREEZE_KEYS, "forward_freeze")
    if r["schema"] != RESEARCH_FREEZE:
        raise ValueError("INVALID_FREEZE_SCHEMA")
    event = _id(r["event_id"], "event_id")
    home, away = _id(r["home_id"], "home_id"), _id(r["away_id"], "away_id")
    if home not in NFL_TEAMS or away not in NFL_TEAMS or home == away:
        raise ValueError("INVALID_NFL_MATCHUP")
    if (type(r["season"]) is not int or type(r["week"]) is not int
            or not 2000 <= r["season"] <= 2100
            or not 1 <= r["week"] <= 22):
        raise ValueError("INVALID_NFL_EVENT_SEASON_WEEK")
    start = _time(r["start_utc"])
    asof = _time(r["forecast_asof_utc"])
    now_utc = _clock(now)
    if not asof <= now_utc < start:
        raise ValueError("FREEZE_IS_LATE_OR_IN_FUTURE")
    quote = _time(r["odds_observed_at_utc"]) if r["odds_observed_at_utc"] else None
    if quote is not None and not asof <= quote <= now_utc:
        raise ValueError("INVALID_ODDS_OBSERVATION_ORDER")
    _, model_hash = _raw_file(r["model_artifact"])
    sources = _sources(r["source_files"], freeze_time=asof,
                       event_start=start, odds_observed=quote,
                       season=r["season"], week=r["week"])
    sources_by_id = {(s["source_id"], s["sha256"]) for s in sources}
    raw_forecast, forecast_hash = _raw_file(r["forecast_file"])
    headers, rows = _csv(raw_forecast, FORECAST_FIELDS)
    if FORECAST_FORBIDDEN & set(headers):
        raise ValueError("BOOKMAKER_DERIVED_PROJECTION_FIELDS")
    if not rows or len(rows) > 1500:
        raise ValueError("EMPTY_OR_EXCESSIVE_PLAYER_FORECASTS")
    raw_lineup, lineup_hash = _raw_file(
        r["lineup_file"], fields=LINEUP_FILE_KEYS)
    lineup_source = _id(r["lineup_file"]["source_name"], "lineup_source_name")
    if lineup_source not in LINEUP_SOURCES:
        raise ValueError("UNREGISTERED_LINEUP_SOURCE")
    lineup_observed = _time(r["lineup_file"]["observed_at_utc"])
    lineup_captured = _time(r["lineup_file"]["captured_at_utc"])
    if not lineup_observed <= lineup_captured <= asof:
        raise ValueError("LINEUP_CAPTURE_TOO_LATE_FOR_FORECAST")
    if start - lineup_observed > MAX_LINEUP_AGE:
        raise ValueError("STALE_LINEUP_OBSERVATION")
    if quote is not None and lineup_captured > quote:
        raise ValueError("LINEUP_CAPTURE_AFTER_ODDS")
    _, lineup_rows = _csv(raw_lineup, LINEUP_KEYS)
    roster = r["roster_player_ids"]
    if (not isinstance(roster, list) or len(roster) > 400 or
            not roster or len(set(roster)) != len(roster)):
        raise ValueError("INVALID_FROZEN_ROSTER")
    ids = frozenset(_id(v, "roster_id") for v in roster)
    lineup = {}
    for row in lineup_rows:
        if row["event_id"] != event:
            raise ValueError("LINEUP_EVENT_MISMATCH")
        pid = _id(row["player_id"], "lineup_player")
        if pid in lineup or pid not in ids:
            raise ValueError("LINEUP_DUPLICATE_OR_UNBOUND_ID")
        if row["team_id"] not in (home, away) or row["status"] not in LINEUP_STATES:
            raise ValueError("LINEUP_TEAM_OR_STATUS_INVALID")
        lineup[pid] = (row["team_id"], row["status"])
    if len(ids) < len(lineup):
        raise ValueError("ROSTER_COVERAGE_INVALID")
    entries = []
    seen = set()
    for row in rows:
        reasons = []
        pid, team, stat = row["player_id"].strip(), row["team_id"].strip(), row["stat"].strip().upper()
        key = (pid, stat)
        if key in seen:
            raise ValueError("DUPLICATE_PLAYER_STAT_ON_FROZEN_EVENT")
        seen.add(key)
        if row["sport"] != "NFL" or row["event_id"] != event or stat not in STAT_NAMES["NFL"]:
            reasons.append("FORECAST_SCOPE_OR_STAT_MISMATCH")
        if not pid or pid not in ids or team not in (home, away):
            reasons.append("UNBOUND_PLAYER_OR_TEAM")
        if pid not in lineup:
            reasons.append("LINEUP_PLAYER_MISSING")
        elif lineup[pid] != (team, "ACTIVE"):
            reasons.append("LINEUP_NOT_CONFIRMED_ACTIVE")
        if (row["source_id"], row["source_snapshot_sha256"]) not in sources_by_id:
            reasons.append("MODEL_FEATURE_SOURCE_NOT_IN_PREGAME_ARCHIVE")
        forecast_asof = _time(row["asof_utc"])
        if forecast_asof > asof:
            reasons.append("FORECAST_ROW_AFTER_FREEZE")
        # Leverage the existing, independently developed player-stat identity,
        # role, minimum opportunity and chronology contract on every row.
        one = _bytes_one_row(headers, row)
        try:
            ingest_player_forecast_csv(
                one, sport="NFL", event_id=event,
                game_roster_ids=ids, event_team_ids=frozenset({home, away}),
                forecast_freeze_utc=asof,
                odds_observed_at_utc=quote or now_utc,
                expected_file_sha256="sha256:" + sha256(one).hexdigest(),
            )
        except (ValueError, KeyError, TypeError) as exc:
            reasons.append("PROP_INPUT_REJECTED:" + str(exc))
        reasons = sorted(set(reasons))
        accepted = not reasons
        def _value(k):
            try:
                v = float(row[k])
                return v if math.isfinite(v) else None
            except (ValueError, TypeError):
                return None
        entries.append({
            "player_id": pid, "team_id": team, "stat": stat,
            "forecast_mean": _value("mean") if accepted else None,
            "forecast_sd_unverified": _value("sd") if accepted else None,
            "state": "PAPER_0U_FROZEN_UNVERIFIED" if accepted else "BLOCK",
            "reasons": reasons,
            "asof_utc": row["asof_utc"],
            "source_snapshot_sha256": row["source_snapshot_sha256"],
        })
    # Detect a file swapped between initial intake and evidence construction.
    _raw_file(r["forecast_file"])
    _raw_file(r["model_artifact"])
    _raw_file(r["lineup_file"], fields=LINEUP_FILE_KEYS)
    for source in r["source_files"]:
        _raw_file(source, fields=SOURCE_KEYS)
    # Input cannot assert a trusted provider, clock, author or lineup signature.
    return {
        "schema": RESEARCH_FREEZE, "state": "PAPER_0U_FORWARD_CAPTURE_ONLY",
        "event_id": event, "home_id": home, "away_id": away,
        "season": r["season"], "week": r["week"],
        "start_utc": start.isoformat(), "forecast_asof_utc": asof.isoformat(),
        "locally_written_at_utc": now_utc.isoformat(),
        "forecast_csv_sha256": forecast_hash,
        "model_artifact_sha256": model_hash,
        "lineup_csv_sha256": lineup_hash,
        "lineup_source_name": r["lineup_file"]["source_name"],
        "lineup_observed_at_utc": lineup_observed.isoformat(),
        "lineup_captured_at_utc": lineup_captured.isoformat(),
        "source_receipts": sources, "forecast_rows": entries,
        "frozen_rows": sum(x["state"] != "BLOCK" for x in entries),
        "blocked_rows": sum(x["state"] == "BLOCK" for x in entries),
        "source_authenticated_independently": False,
        "lineup_authenticated_independently": False,
        "time_existence_cryptographically_attested": False,
        "model_probabilities_calibrated": False,
        "no_official_promotion": True, **ZERO_KEYS,
    }


def grade_frozen_capture(request, *, now=None):
    """Never change original capture: grade only with separate post-final bytes."""
    r = _exact(request, RESULT_KEYS, "result_grade")
    if r["schema"] != RESEARCH_GRADE:
        raise ValueError("INVALID_GRADE_SCHEMA")
    now_utc = _clock(now)
    capture_bytes, capture_sha = _raw_file({
        "path": r["frozen_capture_path"],
        "raw_sha256": r["frozen_capture_sha256"],
    })
    capture = _strict_json(capture_bytes)
    if (capture.get("schema") != RESEARCH_FREEZE or
            capture.get("official_counted") != 0 or
            capture.get("approved_stake_u") != 0):
        raise ValueError("FORECAST_ARCHIVE_INVALID_OR_PROMOTED")
    event = _id(r["event_id"], "result_event")
    if event != capture["event_id"]:
        raise ValueError("GRADE_EVENT_DOES_NOT_MATCH_CAPTURE")
    start = _time(capture["start_utc"])
    frozen = _time(capture["locally_written_at_utc"])
    ended = _time(r["event_final_at_utc"])
    if not frozen < start < ended <= now_utc:
        raise ValueError("INVALID_FINAL_GAME_CHRONOLOGY")
    raw_results, result_sha = _raw_file(r["result_file"], fields=RESULT_FILE_KEYS)
    source = r["result_file"]
    if source["source_id"] not in SOURCES or SOURCES[source["source_id"]].sport != "NFL":
        raise ValueError("UNREGISTERED_RESULT_SOURCE")
    observed = _time(source["observed_at_utc"])
    captured_at = _time(source["captured_at_utc"])
    if not ended <= observed <= captured_at <= now_utc:
        raise ValueError("RESULT_OBSERVATION_BEFORE_FINAL_OR_IN_FUTURE")
    archive_rows = capture.get("forecast_rows")
    if (not isinstance(archive_rows, list) or
            type(capture.get("frozen_rows")) is not int or
            type(capture.get("blocked_rows")) is not int or
            capture["frozen_rows"] < 0 or capture["blocked_rows"] < 0 or
            capture["frozen_rows"] + capture["blocked_rows"] != len(archive_rows)):
        raise ValueError("FROZEN_ARCHIVE_DENOMINATOR_INVALID")
    counted_frozen = 0
    for record in archive_rows:
        if not isinstance(record, dict) or record.get("state") not in (
                "BLOCK", "PAPER_0U_FROZEN_UNVERIFIED"):
            raise ValueError("FROZEN_ROW_STATE_INVALID")
        if record["state"] != "BLOCK":
            counted_frozen += 1
            mean = record.get("forecast_mean")
            if type(mean) not in (int, float) or not math.isfinite(mean):
                raise ValueError("FROZEN_ACCEPTED_MEAN_INVALID")
    if counted_frozen != capture["frozen_rows"]:
        raise ValueError("FROZEN_ARCHIVE_DENOMINATOR_INVALID")
    headers, rows = _csv(raw_results, RESULT_FIELDS)
    if set(headers) != set(RESULT_FIELDS):
        raise ValueError("UNEXPECTED_RESULT_COLUMNS")
    results = {}
    for row in rows:
        if row["event_id"] != event:
            raise ValueError("RESULT_EVENT_MISMATCH")
        key = (row["player_id"].strip(), row["team_id"].strip(),
               row["stat"].strip().upper())
        if key in results:
            raise ValueError("DUPLICATE_PLAYER_STAT_FINAL")
        try:
            n = float(row["actual"])
        except ValueError as exc:
            raise ValueError("INVALID_FINAL_STAT") from exc
        if not math.isfinite(n) or (n < 0 and key[2] not in
                    ("PASS_YDS", "REC_YDS", "RUSH_YDS")):
            raise ValueError("INVALID_FINAL_STAT")
        results[key] = n
    graded = []
    for row in archive_rows:
        key = row["player_id"], row["team_id"], row["stat"]
        outcome = results.get(key)
        status = ("NOT_GRADED_BLOCKED" if row["state"] == "BLOCK" else
                  "UNRESOLVED_MISSING_FINAL_STAT" if outcome is None else
                  "GRADED_RESEARCH_ONLY")
        err = (outcome - row["forecast_mean"]
               if status == "GRADED_RESEARCH_ONLY" else None)
        graded.append({
            "player_id": key[0], "team_id": key[1], "stat": key[2],
            "state": status, "forecast_mean": row["forecast_mean"],
            "actual": outcome if status == "GRADED_RESEARCH_ONLY" else None,
            "actual_minus_prediction": round(err, 6) if err is not None else None,
        })
    n = sum(x["state"] == "GRADED_RESEARCH_ONLY" for x in graded)
    if (n + sum(x["state"] == "UNRESOLVED_MISSING_FINAL_STAT" for x in graded)
           + sum(x["state"] == "NOT_GRADED_BLOCKED" for x in graded) != len(archive_rows)):
        raise ValueError("GRADE_DENOMINATOR_MISMATCH")
    return {
        "schema": RESEARCH_GRADE, "state": "PAPER_0U_GRADED_NOT_CERTIFIED",
        "event_id": event, "frozen_archive_sha256": capture_sha,
        "final_result_sha256": result_sha,
        "observed_at_utc": observed.isoformat(),
        "graded_at_utc": now_utc.isoformat(),
        "graded_rows": n, "unresolved_rows": sum(
            x["state"] == "UNRESOLVED_MISSING_FINAL_STAT" for x in graded),
        "blocked_rows": sum(x["state"] == "NOT_GRADED_BLOCKED" for x in graded),
        "results": graded,
        "independent_source_authentication": False,
        "actual_game_box_verified_independently": False,
        "frozen_source_existence_externally_attested": False,
        "official_clv_eligible": False, **ZERO_KEYS,
    }


def _json_file(path):
    raw = Path(path).read_bytes()
    if len(raw) > 8_000_000:
        raise ValueError("MANIFEST_TOO_LARGE")
    return _strict_json(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("freeze", "grade"):
        sub = commands.add_parser(command)
        sub.add_argument("request_json")
        sub.add_argument("private_output_json")
    args = parser.parse_args(argv)
    data = _json_file(args.request_json)
    result = (freeze_player_forecasts(data) if args.command == "freeze"
              else grade_frozen_capture(data))
    if args.command == "freeze" and datetime.now(timezone.utc) >= _time(
            result["start_utc"]):
        raise ValueError("FREEZE_OUTPUT_WOULD_BE_WRITTEN_AFTER_KICKOFF")
    sha = _write_private_create_only(args.private_output_json, result)
    print(json.dumps({
        "state": result["state"], "output_sha256": sha,
        "approved_stake_u": 0, "official_counted": 0,
        "rows": len(result.get("forecast_rows", result.get("results", []))),
        "source_authenticated_independently": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
