#!/usr/bin/env python3
"""Research-only, point-in-time-gated opponent-adjusted NFL EPA ratings.

Inputs are a PBP CSV exported from nflreadpy and an independently maintained
per-game UTC availability manifest. A current download CANNOT be replayed as
a historical pregame snapshot. No points, probabilities, EV or stakes.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import exp, isfinite, log
from pathlib import Path


def utc(value):
    if not isinstance(value, str):
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("UTC_TIMESTAMP_INVALID") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return stamp.astimezone(timezone.utc)


def number(value, label):
    try:
        x = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("INVALID_" + label) from exc
    if not isfinite(x):
        raise ValueError("NONFINITE_" + label)
    return x


def solve(a, b):
    """Solve positive-definite ridge normal equations, with pivot checking."""
    n = len(b)
    a = [r[:] + [y] for r, y in zip(a, b)]
    for k in range(n):
        best = max(range(k, n), key=lambda i: abs(a[i][k]))
        if abs(a[best][k]) < 1e-10:
            raise ValueError("SINGULAR_RIDGE_SYSTEM")
        a[k], a[best] = a[best], a[k]
        pivot = a[k][k]
        for j in range(k, n + 1):
            a[k][j] /= pivot
        for i in range(k + 1, n):
            scale = a[i][k]
            if scale:
                for j in range(k, n + 1):
                    a[i][j] -= scale * a[k][j]
    result = [0.0] * n
    for i in range(n - 1, -1, -1):
        result[i] = a[i][n] - sum(a[i][j] * result[j]
                                   for j in range(i + 1, n))
    return result


def fit_unit(observations, teams, ridge):
    """EPA/play = league mean + offensive-team effect + defense-allowed effect."""
    n = len(teams)
    index = {team: i for i, team in enumerate(teams)}
    p = 1 + 2 * n
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for offense, defense, epa, weight in observations:
        idx = (0, 1 + index[offense], 1 + n + index[defense])
        for i in idx:
            xty[i] += weight * epa
            for j in idx:
                xtx[i][j] += weight
    for i in range(1, p):
        xtx[i][i] += ridge
    coeff = solve(xtx, xty)
    off = coeff[1:1 + n]
    defense = coeff[1 + n:]
    mo = sum(off) / n
    md = sum(defense) / n
    return {
        "league_mean_epa_per_play": round(coeff[0] + mo + md, 6),
        "offense_above_average_epa": {
            team: round(off[i] - mo, 6) for i, team in enumerate(teams)
        },
        # Positive = permits MORE EPA/play; negative is better defense.
        "defense_allowed_above_average_epa": {
            team: round(defense[i] - md, 6) for i, team in enumerate(teams)
        },
        "play_count": len(observations),
        "effective_weighted_plays": round(sum(x[3] for x in observations), 3),
    }


def build_ratings(plays, games, *, asof_utc, source_observed_utc,
                  half_life_days=21.0, ridge=30.0, wp_limits=None):
    """Build research features; returns audited exclusions and zero stake.

    games[game_id] requires kickoff_utc, final_utc, data_available_utc.
    All these timestamps are assertions supplied by caller, NOT authenticated.
    Any game without a complete manifest is refused rather than inferred.
    """
    asof = utc(asof_utc)
    observed = utc(source_observed_utc)
    if observed > asof:
        raise ValueError("SOURCE_OBSERVED_AFTER_FORECAST")
    half_life_days = number(half_life_days, "HALF_LIFE")
    ridge = number(ridge, "RIDGE")
    if half_life_days <= 0 or ridge <= 0:
        raise ValueError("HYPERPARAMETER_MUST_BE_POSITIVE")
    if wp_limits is not None:
        lo, hi = wp_limits
        lo, hi = number(lo, "WP_LO"), number(hi, "WP_HI")
        if not 0 <= lo < hi <= 1:
            raise ValueError("BAD_WP_LIMITS")

    info = {}
    for game_id, metadata in games.items():
        if not isinstance(metadata, dict):
            raise ValueError("GAME_MANIFEST_INVALID")
        try:
            start = utc(metadata["kickoff_utc"])
            final = utc(metadata["final_utc"])
            available = utc(metadata["data_available_utc"])
        except KeyError as exc:
            raise ValueError("INCOMPLETE_GAME_MANIFEST") from exc
        if not start < final <= available:
            raise ValueError("GAME_TIME_ORDER_INVALID")
        info[str(game_id)] = (start, final, available)

    data = {"pass": [], "rush": []}
    counts = {"source_rows": 0, "excluded_not_available_asof": 0,
              "excluded_no_offense": 0, "excluded_non_scrimmage": 0,
              "excluded_missing_epa": 0, "excluded_wp_filter": 0}
    teams = set()
    used_games = set()
    seen_plays = set()
    for row in plays:
        counts["source_rows"] += 1
        if not isinstance(row, dict) or not str(row.get("game_id") or ""):
            raise ValueError("PBP_GAME_ID_MISSING")
        game_id = str(row["game_id"])
        if game_id not in info:
            raise ValueError("PBP_GAME_MANIFEST_MISSING:" + game_id)
        start, final, available = info[game_id]
        if available > asof or final >= asof:
            counts["excluded_not_available_asof"] += 1
            continue
        if available > observed:
            raise ValueError("GAME_DATA_NOT_YET_AVAILABLE_AT_SOURCE_OBSERVATION")
        offense, defense = row.get("posteam"), row.get("defteam")
        if not offense or not defense:
            counts["excluded_no_offense"] += 1
            continue
        offense, defense = str(offense).strip(), str(defense).strip()
        if not offense or not defense or offense == defense:
            raise ValueError("BAD_TEAM_ID")
        passed, rushed = str(row.get("pass") or "0"), str(row.get("rush") or "0")
        if passed not in ("0", "1") or rushed not in ("0", "1"):
            raise ValueError("INVALID_PASS_RUSH_FLAG")
        if (passed == "1") == (rushed == "1"):
            counts["excluded_non_scrimmage"] += 1
            continue
        # nflfastR identifies a play by the (game_id, drive, play_id)
        # composite. Non-scrimmage rows can lack these values and are
        # excluded first, but every eligible pass/rush requires them.
        play_id = row.get("play_id")
        drive = row.get("drive")
        if play_id is None or not str(play_id).strip():
            raise ValueError("PBP_PLAY_ID_MISSING")
        if drive is None or not str(drive).strip():
            raise ValueError("PBP_DRIVE_MISSING")
        source_key = (game_id, str(drive).strip(), str(play_id).strip())
        if source_key in seen_plays:
            raise ValueError("DUPLICATE_PBP_PLAY_ID")
        seen_plays.add(source_key)
        if row.get("epa") in (None, ""):
            counts["excluded_missing_epa"] += 1
            continue
        epa = number(row["epa"], "EPA")
        if wp_limits is not None:
            if row.get("wp") in (None, ""):
                raise ValueError("WP_REQUIRED_BY_SELECTED_ABLATION")
            wp = number(row["wp"], "WP")
            if not lo <= wp <= hi:
                counts["excluded_wp_filter"] += 1
                continue
        days_old = (asof - final).total_seconds() / 86400.0
        weight = exp(-log(2.0) * days_old / half_life_days)
        unit = "pass" if passed == "1" else "rush"
        data[unit].append((offense, defense, epa, weight))
        teams.update((offense, defense))
        used_games.add(game_id)

    if not all(data.values()) or len(teams) < 2:
        raise ValueError("INSUFFICIENT_PASS_RUSH_HISTORY_FOR_RATINGS")
    ordered = sorted(teams)
    return {
        "status": "PAPER_HOLD_0U",
        "source_authentication": "CALLER_ASSERTED_TIMES_NOT_INDEPENDENTLY_VERIFIED",
        "asof_utc": asof.isoformat(),
        "source_observed_utc": observed.isoformat(),
        "half_life_days": half_life_days,
        "ridge": ridge,
        "wp_limits": list(wp_limits) if wp_limits is not None else None,
        "games_used": len(used_games),
        "teams_used": ordered,
        "census": counts,
        "units": {kind: fit_unit(obs, ordered, ridge)
                  for kind, obs in data.items()},
        "projected_points": None,
        "win_probability": None,
        "market_ev": None,
        "approved_stake_u": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plays", required=True, help="CSV with nflverse fields")
    parser.add_argument("--game-manifest", required=True, help="JSON game times and availability")
    parser.add_argument("--asof-utc", required=True)
    parser.add_argument("--source-observed-utc", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--half-life-days", type=float, default=21)
    parser.add_argument("--ridge", type=float, default=30)
    parser.add_argument("--wp-filter", action="store_true",
                        help="Ablation: retain only WP 0.10..0.90; not proven better")
    args = parser.parse_args()
    raw = Path(args.plays)
    with open(args.game_manifest, encoding="utf-8") as f:
        manifest = json.load(f)
    with raw.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"game_id", "drive", "play_id", "posteam", "defteam", "pass", "rush", "epa"}
        if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
                or not required.issubset(reader.fieldnames)):
            raise ValueError("MISSING_OR_DUPLICATE_PBP_COLUMNS")
        result = build_ratings(
            reader, manifest, asof_utc=args.asof_utc,
            source_observed_utc=args.source_observed_utc,
            half_life_days=args.half_life_days, ridge=args.ridge,
            wp_limits=(0.1, 0.9) if args.wp_filter else None,
        )
    result["local_input_sha256"] = "sha256:" + sha256(raw.read_bytes()).hexdigest()
    result["manifest_sha256"] = "sha256:" + sha256(
        Path(args.game_manifest).read_bytes()).hexdigest()
    target = Path(args.out)
    with target.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps({"status": result["status"], "out": str(target),
                      "games_used": result["games_used"],
                      "census": result["census"]}, sort_keys=True))


if __name__ == "__main__":
    main()
