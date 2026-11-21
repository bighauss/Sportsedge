#!/usr/bin/env python3
"""Stage SportsDataverse cfb_ratings_weekly data, offline and fail-closed.

No CFBD API key. Read an already exported, frozen cfbfastR weekly-ratings
CSV, exact team-ID crosswalk, schedule and custody manifest. Does NOT derive
point ratings, price odds or import the SportsEdge model. Research/PAPER 0u.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path


class Rejected(ValueError):
    """Unverifiable input: never recover with defaults."""


def clock(value, name):
    if not value:
        raise Rejected(f"{name}: MISSING_CLOCK")
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise Rejected(f"{name}: INVALID_CLOCK") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise Rejected(f"{name}: CLOCK_NEEDS_OFFSET")
    return dt.astimezone(timezone.utc)


def read_csv(path, required, label):
    raw = Path(path).read_bytes()
    try:
        content = raw.decode("utf-8-sig", errors="strict")
        reader = csv.reader(io.StringIO(content, newline=""), strict=True)
        head = next(reader, [])
        if not head:
            raise Rejected(f"{label}: EMPTY_HEADER")
        names = [x.strip().lower() for x in head]
        if not all(names) or len(set(names)) != len(names):
            raise Rejected(f"{label}: AMBIGUOUS_HEADERS")
        if set(required) - set(names):
            raise Rejected(f"{label}: MISSING_COLUMNS:{','.join(sorted(set(required)-set(names)))}")
        rows = []
        for n, vals in enumerate(reader, 2):
            if len(vals) != len(names) or not any(v.strip() for v in vals):
                raise Rejected(f"{label}: BAD_RECORD_{n}")
            rows.append(dict(zip(names, [v.strip() for v in vals])))
    except (UnicodeError, csv.Error) as exc:
        raise Rejected(f"{label}: MALFORMED_CSV") from exc
    return rows, hashlib.sha256(raw).hexdigest()


def number(text, field, low, high):
    try:
        v = float(text)
    except (TypeError, ValueError) as exc:
        raise Rejected(f"{field}: MISSING_OR_INVALID") from exc
    if not math.isfinite(v) or not (low <= v <= high):
        raise Rejected(f"{field}: NONFINITE_OR_OUT_OF_RANGE")
    return v


def stage(ratings_path, crosswalk_path, games_path, manifest_path):
    ratings, digest = read_csv(ratings_path,
        ("season", "through_week", "team_id", "games", "adj_off_epa", "adj_def_epa", "off_pace"), "RATINGS")
    crosswalk, cw_digest = read_csv(crosswalk_path, ("team_id", "team"), "CROSSWALK")
    games, games_digest = read_csv(games_path,
        ("game_id", "season", "week", "kickoff_utc", "home_team_id", "away_team_id", "home", "away"), "GAMES")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("source_kind") != "sportsdataverse_cfb_ratings_weekly":
        raise Rejected("SOURCE_KIND_UNRECOGNIZED")
    source_url = str(manifest.get("source_url") or "")
    if not (source_url.startswith("https://github.com/sportsdataverse/") or
            source_url.startswith("https://raw.githubusercontent.com/sportsdataverse/")):
        raise Rejected("UNRECOGNIZED_SOURCE_URL")
    if manifest.get("source_sha256") != digest:
        raise Rejected("RATINGS_SHA256_MISMATCH")
    publication = clock(manifest.get("published_utc"), "PUBLISHED")
    capture = clock(manifest.get("captured_utc"), "CAPTURED")
    through = clock(manifest.get("data_through_utc"), "DATA_THROUGH")
    asof = clock(manifest.get("model_asof_utc"), "MODEL_ASOF")
    if not through <= publication <= capture <= asof:
        raise Rejected("SOURCE_CLOCKS_OUT_OF_ORDER")
    if not ratings or not games or not crosswalk:
        raise Rejected("EMPTY_SOURCE_OR_CROSSWALK_OR_SLATE")
    identities = {}
    for r in crosswalk:
        tid, name = r["team_id"], r["team"]
        if not tid or not name or tid in identities or name in identities.values():
            raise Rejected("DUPLICATE_OR_BLANK_CROSSWALK")
        identities[tid] = name
    by_key = {}
    for r in ratings:
        key = (r["season"], r["through_week"], r["team_id"])
        if key in by_key:
            raise Rejected("DUPLICATE_TEAM_WEEK_RATING")
        if not all(key):
            raise Rejected("BLANK_RATING_IDENTITY")
        # Parse every source row, even those not on the user's slate.
        off = number(r["adj_off_epa"], "ADJ_OFF_EPA", -3.0, 3.0)
        de = number(r["adj_def_epa"], "ADJ_DEF_EPA", -3.0, 3.0)
        pace = number(r["off_pace"], "OFF_PACE", 20.0, 130.0)
        n_games = int(number(r["games"], "GAMES_PLAYED", 0, 25))
        if int(float(r["games"])) != float(r["games"]):
            raise Rejected("GAMES_PLAYED_NOT_INTEGER")
        week = int(number(r["through_week"], "THROUGH_WEEK", 0, 30))
        if week != float(r["through_week"]):
            raise Rejected("THROUGH_WEEK_NOT_INTEGER")
        by_key[key] = {"adj_off_epa": off, "adj_def_epa": de,
                       "off_pace": pace, "games": n_games, "through_week": week}
    results, seen_games = [], set()
    for g in games:
        gid = g["game_id"]
        if not gid or gid in seen_games:
            raise Rejected("DUPLICATE_OR_BLANK_GAME_ID")
        seen_games.add(gid)
        ko = clock(g["kickoff_utc"], "KICKOFF")
        reasons = []
        if ko <= asof:
            reasons.append("ASOF_NOT_BEFORE_KICKOFF")
        if ko <= through:
            reasons.append("SOURCE_DATA_NOT_PREGAME")
        if g["home_team_id"] == g["away_team_id"]:
            reasons.append("SAME_TEAM_BOTH_SIDES")
        for side in ("home", "away"):
            tid = g[f"{side}_team_id"]
            if identities.get(tid) != g[side]:
                reasons.append(f"{side.upper()}_IDENTITY_UNVERIFIED")
        try:
            target_week = int(number(g["week"], "GAME_WEEK", 1, 30))
            target_year = int(number(g["season"], "SEASON", 2000, 2100))
        except Rejected:
            reasons.append("BAD_GAME_SEASON_WEEK")
            target_week, target_year = 0, 0
        match = {}
        if target_week:
            for side in ("home", "away"):
                tid = g[f"{side}_team_id"]
                choices = [v for (year, wk, team), v in by_key.items()
                           if year == str(target_year) and team == tid and v["through_week"] < target_week]
                if not choices:
                    reasons.append(f"{side.upper()}_NO_PRIOR_WEEK_RATING")
                else:
                    v = max(choices, key=lambda x: x["through_week"])
                    if v["games"] < 1:
                        reasons.append(f"{side.upper()}_NO_GAMES_PLAYED")
                    match[side] = v
        record = {"game_id": gid, "home": g["home"], "away": g["away"],
                  "kickoff_utc": ko.isoformat(), "asof_utc": asof.isoformat(),
                  "rating_inputs": match if not reasons else None,
                  "status": "STAGED_RESEARCH_ONLY" if not reasons else "BLOCKED",
                  "reason_codes": sorted(set(reasons + (["EPA_TO_POINTS_MAPPING_UNVALIDATED",
                     "CFB_ADVANCED_MATCHUP_INPUTS_UNVERIFIED", "PUBLICATION_CUSTODY_SELF_ASSERTED"] if not reasons else []))),
                  "stake_u": 0, "wager_eligible": False}
        results.append(record)
    return {"source_kind": "sportsdataverse_cfb_ratings_weekly",
            "source_url": source_url, "source_sha256": digest,
            "crosswalk_sha256": cw_digest, "games_sha256": games_digest,
            "published_utc": publication.isoformat(), "captured_utc": capture.isoformat(),
            "data_through_utc": through.isoformat(), "model_asof_utc": asof.isoformat(),
            "n_ratings": len(ratings), "n_games": len(games),
            "n_staged": sum(r["status"] == "STAGED_RESEARCH_ONLY" for r in results),
            "n_blocked": sum(r["status"] == "BLOCKED" for r in results),
            "all_wagers_blocked": True, "rows": results}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("ratings", "crosswalk", "games", "manifest", "out"):
        p.add_argument("--" + key, required=True)
    a = p.parse_args()
    report = stage(a.ratings, a.crosswalk, a.games, a.manifest)
    # Create-only report; no overwrites of historical audit files or model state.
    with open(a.out, "x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"STAGED={report['n_staged']} BLOCKED={report['n_blocked']} PAPER/0u; {a.out}")


if __name__ == "__main__":
    main()
