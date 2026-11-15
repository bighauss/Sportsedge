"""Raw-stat NFL game-log reader for SportsEdge DFS research.

Example data: xtheredshirtx/fanduel-player-data NFL offense game logs.
Provider fantasy points (FD Pts), DK AvgPointsPerGame, and last-five FP
averages are deliberately IGNORED. Only raw box-score stats become features.
This module is NOT a projection model and does not modify the current card.

The source lacks attempts, targets, snaps, routes and injuries. Obtain those
separately before changing showdown simulation parameters. Records dated
on or after game day are excluded to prevent lookahead.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path

FIELDS = ("Receptions", "Rec Yards", "Rec TD", "Rush Yards", "Rush TD",
          "Pass Yards", "Pass TD", "INT Thrown", "Fumbles Lost", "2-Pt Conversions")
IDENTITY = ("Date", "Player", "Team", "Opp", "Pos", "Season")
MAX_BYTES = 2_000_000


class SourceError(ValueError):
    pass


def parse_records(csv_bytes: bytes, *, kickoff_date: str, teams=("PIT", "CIN")) -> list[dict]:
    try:
        cutoff = date.fromisoformat(kickoff_date)
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    except (UnicodeDecodeError, ValueError) as ex:
        raise SourceError(f"Invalid UTF-8 CSV or kickoff date: {ex}") from ex
    if not reader.fieldnames or any(k not in reader.fieldnames for k in (*IDENTITY, *FIELDS)):
        raise SourceError("Missing raw player box-score columns")
    seen, out = set(), []
    for raw in reader:
        if not all(raw.get(key) for key in ("Date", "Player", "Team", "Pos")):
            raise SourceError("Missing date/player/team/position")
        try:
            game_date = date.fromisoformat(raw["Date"])
        except ValueError as ex:
            raise SourceError(f"Invalid game date {raw['Date']!r}") from ex
        if game_date >= cutoff or raw["Team"] not in teams:
            continue
        key = (raw["Date"], raw["Player"], raw["Team"])
        if key in seen:
            raise SourceError(f"Duplicate game log {key}")
        seen.add(key)
        entry = {k: raw[k] for k in IDENTITY}
        for key in FIELDS:
            try:
                value = float(raw[key])
            except (ValueError, TypeError) as ex:
                raise SourceError(f"Invalid raw stat {key} for {raw['Player']!r}") from ex
            if value != value or abs(value) > 10000 or (value < 0 and key not in ("Rec Yards", "Rush Yards", "Pass Yards")):
                raise SourceError(f"Out-of-range {key} for {raw['Player']!r}")
            entry[key] = value
        out.append(entry)
    return out


def player_features(rows: list[dict], *, max_games=5) -> dict[str, dict]:
    if max_games < 1:
        raise SourceError("max_games must be positive")
    groups = {}
    for row in rows:
        groups.setdefault((row["Player"], row["Team"]), []).append(row)
    result = {}
    for (player, team), history in sorted(groups.items()):
        if player in result:
            raise SourceError(f"Ambiguous player name on multiple teams: {player}")
        games = sorted(history, key=lambda x: x["Date"], reverse=True)[:max_games]
        f = {"team": team, "games": len(games), "last_game": games[0]["Date"]}
        for stat in FIELDS:
            f[stat] = round(sum(r[stat] for r in games) / len(games), 3)
        # No provider FP or simple fantasy-point mean becomes a model input.
        result[player] = f
    return result


def load_file(path: str | Path, kickoff_date: str, teams=("PIT", "CIN"), max_games=5) -> dict:
    source = Path(path)
    data = source.read_bytes()
    if len(data) > MAX_BYTES:
        raise SourceError("Source too large")
    rows = parse_records(data, kickoff_date=kickoff_date, teams=teams)
    if not rows:
        raise SourceError("No pre-kickoff rows for requested teams")
    return {"status": "RESEARCH_ONLY", "source": str(source),
            "sha256": hashlib.sha256(data).hexdigest(), "cutoff_exclusive": kickoff_date,
            "raw_rows": len(rows), "features": player_features(rows, max_games=max_games),
            "limitations": ["no carries", "no targets", "no pass attempts", "no snaps/routes",
                            "no injuries", "does not update model projections"]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("csv_file", type=Path, help="Local raw offense game-log CSV")
    p.add_argument("--kickoff-date", default="2026-11-15")
    p.add_argument("--teams", nargs="+", default=["PIT", "CIN"])
    p.add_argument("--recent-games", type=int, default=5)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    report = load_file(args.csv_file, args.kickoff_date, args.teams, args.recent_games)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
