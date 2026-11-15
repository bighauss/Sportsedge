#!/usr/bin/env python3
"""Build PAPER-ONLY observed NFL offensive-TD shares from nflverse weekly player stats.

Inputs: nflverse stats_player_week_2026.csv, saved before the slate.
Outputs: td_shares.csv (team,player,share) and a full audit CSV.
This is a descriptive baseline, NOT a validated ATTD probability model.
"""
import argparse
import csv
import gzip
import hashlib
import math
from collections import defaultdict
from pathlib import Path

TEAMS = set("""ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC
LV LAC LAR MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS""".split())


def parse_count(v, label, row):
    if v is None or str(v).strip() == "":
        raise ValueError(f"Missing {label} in input row {row}")
    n = float(v)
    if not math.isfinite(n) or n < 0 or not n.is_integer():
        raise ValueError(f"Invalid {label}: {v!r} in row {row}")
    return int(n)


def build(src, *, season=2026, through_week=9, min_team_tds=1, require_32=True):
    path = Path(src)
    data = path.read_bytes()
    fingerprint = hashlib.sha256(data).hexdigest()
    totals = defaultdict(int)
    weeks = defaultdict(set)
    unique_rows = set()
    seen_players = {}
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or ())
        required = {"season", "week", "rushing_tds", "receiving_tds"}
        if not required.issubset(cols):
            raise ValueError(f"Missing required columns: {sorted(required - cols)}")
        team_col = "team" if "team" in cols else "recent_team"
        player_col = "player_display_name" if "player_display_name" in cols else "player_name"
        id_col = "player_id" if "player_id" in cols else ("player_gsis_id" if "player_gsis_id" in cols else None)
        if team_col not in cols or player_col not in cols or not id_col:
            raise ValueError("Need team/recent_team, player name and player_id/player_gsis_id")
        for rownum, r in enumerate(reader, start=2):
            if not r["season"] or not r["week"]:
                raise ValueError(f"Missing season/week at row {rownum}")
            year, week = parse_count(r["season"], "season", rownum), parse_count(r["week"], "week", rownum)
            if year != season or week > through_week:
                continue
            if "season_type" in cols and r["season_type"] not in ("REG", "Regular", "regular"):
                continue
            team = (r[team_col] or "").strip().upper()
            player = (r[player_col] or "").strip()
            pid = (r[id_col] or "").strip()
            if team not in TEAMS or not player or not pid:
                raise ValueError(f"Bad team/player at row {rownum}: {team!r}, {player!r}")
            key = (year, week, team, pid)
            if key in unique_rows:
                raise ValueError(f"Duplicate player/team/week at row {rownum}: {key}")
            unique_rows.add(key)
            td = parse_count(r["rushing_tds"], "rushing_tds", rownum) + parse_count(r["receiving_tds"], "receiving_tds", rownum)
            totals[(team, pid)] += td
            weeks[team].add(week)
            if (team, pid) in seen_players and seen_players[(team, pid)] != player:
                raise ValueError(f"Name changed for player {pid} on {team}")
            seen_players[(team, pid)] = player

    teams = set(weeks)
    if require_32 and teams != TEAMS:
        raise ValueError(f"Missing NFL teams: {sorted(TEAMS - teams)}, unexpected: {sorted(teams - TEAMS)}")
    team_tds = {t: sum(v for (team, _), v in totals.items() if team == t) for t in teams}
    weak = {t: k for t, k in team_tds.items() if k < min_team_tds}
    if weak:
        raise ValueError(f"Not enough recorded offensive TDs: {weak}")
    output, audit = [], []
    for (team, pid), td in sorted(totals.items()):
        player = seen_players[(team, pid)]
        share = td / team_tds[team]
        audit.append(dict(team=team, player=player, player_id=pid, observed_offensive_tds=td,
                          team_offensive_tds=team_tds[team], share=f"{share:.10f}",
                          games_weeks_seen=len(weeks[team]), through_week=through_week,
                          source_sha256=fingerprint))
        if td:
            output.append(dict(team=team, player=player, share=f"{share:.10f}"))
    return output, audit, fingerprint


def write_csv(filename, rows, fields):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("weekly_stats", help="nflverse 2026 weekly player statistics .csv or .csv.gz")
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("--through-week", type=int, default=9)
    p.add_argument("--min-team-tds", type=int, default=1)
    p.add_argument("--allow-partial-teams", action="store_true", help="Fixture/testing only")
    p.add_argument("--out", default="td_shares.csv")
    args = p.parse_args()
    shares, audit, sha = build(args.weekly_stats, season=args.season,
                               through_week=args.through_week, min_team_tds=args.min_team_tds,
                               require_32=not args.allow_partial_teams)
    write_csv(args.out, shares, ("team", "player", "share"))
    audit_path = str(Path(args.out).with_suffix("")) + "_audit.csv"
    write_csv(audit_path, audit, ("team", "player", "player_id", "observed_offensive_tds",
                                 "team_offensive_tds", "share", "games_weeks_seen",
                                 "through_week", "source_sha256"))
    print(f"Wrote {len(shares)} player shares to {args.out}; audit={audit_path}; input sha256={sha}")
    print("PAPER / 0u. Historical offensive TD share is not a validated ATTD forecast.")

if __name__ == "__main__":
    main()
