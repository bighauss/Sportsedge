"""Chronological matchup-aware player mean challenger, research only.

Inputs are externally verified, timestamped final player/team boxes and explicit
pregame roster candidates. Never synthesize observation timestamps. Historical
replay uses only finals observed before each forecast cutoff. No odds enter model.
"""
from collections import defaultdict
from statistics import mean
from cbb_player_residual_pricing import clock, vector, STATS, Forecast, validate_forecast
import math

VERSION = "CBB_PLAYER_MATCHUP_V1_RESEARCH"
MIN_APPEARANCES = 5
MIN_TEAM_GAMES = 5
SHRINK = 10.0


def valid_id(value):
    return isinstance(value, str) and bool(value.strip())


def admit(rows):
    result, seen = [], set()
    for r in rows:
        gid, home, away = (r[k] for k in ("event_id", "home_id", "away_id"))
        if not all(map(valid_id, (gid, home, away))) or home == away or gid in seen:
            raise ValueError("DUPLICATE_OR_INVALID_GAME")
        seen.add(gid)
        if clock(r["observed_final_utc"]) <= clock(r["tip_utc"]):
            raise ValueError("FINAL_NOT_AFTER_TIP")
        pace = r["possessions"]
        if type(pace) not in (int, float) or not math.isfinite(pace) or not 30 <= pace <= 150:
            raise ValueError("INVALID_POSSESSIONS")
        if set(r["team_stats"]) != {home, away}:
            raise ValueError("TEAM_STATS_IDENTITY")
        for stats in r["team_stats"].values():
            vector(stats, actual=True)
        ids, totals = set(), defaultdict(lambda: [0, 0, 0, 0])
        for p in r["players"]:
            tid, pid = p["team_id"], p["player_id"]
            if tid not in (home, away) or not valid_id(pid) or pid in ids:
                raise ValueError("DUPLICATE_OR_INVALID_PLAYER")
            ids.add(pid)
            minutes = p["minutes"]
            if type(minutes) not in (int, float) or not math.isfinite(minutes) or not 0 < minutes <= 100:
                raise ValueError("INVALID_PARTICIPATION_MINUTES")
            vals = vector(p["stats"], actual=True)
            totals[tid] = [a+b for a,b in zip(totals[tid], vals)]
        for tid, vals in totals.items():
            if any(a > b for a,b in zip(vals, vector(r["team_stats"][tid], actual=True))):
                raise ValueError("PLAYER_TOTAL_EXCEEDS_TEAM")
        result.append(r)
    return sorted(result, key=lambda r: (clock(r["observed_final_utc"]), r["event_id"]))


def forecast(target, admitted):
    gid, tid, pid, opp = (target[k] for k in ("event_id", "team_id", "player_id", "opponent_id"))
    if not all(map(valid_id, (gid, tid, pid, opp))) or tid == opp:
        raise ValueError("INVALID_TARGET_ID")
    cutoff = clock(target["frozen_utc"])
    if not cutoff < clock(target["tip_utc"]):
        raise ValueError("TARGET_NOT_PREGAME")
    prior = [r for r in admitted if r["event_id"] != gid and clock(r["observed_final_utc"]) < cutoff]
    team_games, def_allowed, league, appearances = defaultdict(list), defaultdict(list), [], []
    for r in prior:
        h, a, pace = r["home_id"], r["away_id"], r["possessions"]
        for team, other in ((h,a),(a,h)):
            team_games[team].append(pace)
            vals = vector(r["team_stats"][other], actual=True)
            rate = tuple(v / pace for v in vals)
            def_allowed[team].append(rate)
            league.append(rate)
        for p in r["players"]:
            if p["player_id"] == pid and p["team_id"] == tid:
                appearances.append((r, p))
    if len(appearances) < MIN_APPEARANCES or min(len(team_games[tid]),len(team_games[opp])) < MIN_TEAM_GAMES:
        raise ValueError("INSUFFICIENT_MATCHUP_HISTORY")
    # Latest 10 by game tip, not order received. No inferred availability or minutes cap.
    recent = sorted(appearances, key=lambda rp: clock(rp[0]["tip_utc"]))[-10:]
    minutes = mean(p["minutes"] for _,p in recent)
    pace = (mean(team_games[tid][-10:]) + mean(team_games[opp][-10:])) / 2
    player_pace = mean(r["possessions"] for r,_ in recent)
    lg = [mean(v[i] for v in league) for i in range(4)]
    opp_rows = def_allowed[opp]
    n = len(opp_rows)
    # Shrink opponent allowed per possession toward prior-only league baseline.
    factors = [((sum(v[i] for v in opp_rows)+SHRINK*lg[i])/(n+SHRINK))/lg[i]
               if lg[i] > 0 else 1.0 for i in range(4)]
    means = {}
    for i, stat in enumerate(STATS):
        rate = sum(p["stats"][stat] for _,p in recent)/sum(p["minutes"] for _,p in recent)
        means[stat] = rate * minutes * pace/player_pace * factors[i]
    means["3PM"] = min(means["3PM"], means["PTS"]/3)
    f = Forecast(gid, tid, pid, target["tip_utc"], target["frozen_utc"], means, VERSION)
    validate_forecast(f)
    return f, {"minutes_if_participating": minutes, "pace": pace,
               "opponent_factors": dict(zip(STATS,factors)),
               "appearances": len(recent), "opponent_games": n,
               "prior_games": len(prior), "max_observed_final_utc": prior[-1]["observed_final_utc"]}


def build(rows, targets):
    """Bundle of replay residuals plus current forecasts. Replay is NOT prospective evidence."""
    from dataclasses import asdict
    admitted = admit(rows)
    history, forecasts, diagnostics, rejects = [], [], [], []
    for r in admitted:
        for p in r["players"]:
            tid = p["team_id"]
            # Historical cutoff is game tip minus one second, not a claim of original capture.
            from datetime import timedelta
            cutoff = (clock(r["tip_utc"])-timedelta(seconds=1)).isoformat()
            target = {"event_id": r["event_id"], "team_id": tid, "player_id": p["player_id"],
                      "opponent_id": r["away_id"] if tid == r["home_id"] else r["home_id"],
                      "tip_utc": r["tip_utc"], "frozen_utc": cutoff}
            try:
                f, _ = forecast(target, admitted)
                history.append({"forecast": asdict(f), "observed_final_utc": r["observed_final_utc"],
                                "actual": p["stats"], "participated": True})
            except ValueError as exc:
                rejects.append({"stage": "historical", "event_id": r["event_id"], "player_id": p["player_id"], "reason": str(exc)})
    seen = set()
    for t in targets:
        key = tuple(t[k] for k in ("event_id","team_id","player_id"))
        if key in seen:
            raise ValueError("DUPLICATE_TARGET")
        seen.add(key)
        if any(r["event_id"] == t["event_id"] for r in admitted):
            raise ValueError("TARGET_ALREADY_IN_FINALS")
        try:
            f, diag = forecast(t, admitted)
            forecasts.append(asdict(f)); diagnostics.append({"key": key, **diag})
        except ValueError as exc:
            rejects.append({"stage": "target", "event_id": key[0], "player_id": key[2], "reason": str(exc)})
    return {"schema": "CBB_PLAYER_RESIDUAL_BUNDLE_V1", "targets": forecasts, "history": history,
            "evidence_class": "CHRONOLOGICAL_REPLAY_NOT_PROSPECTIVE", "diagnostics": diagnostics,
            "rejections": rejects, "approved_stake_u": 0}


def main():
    import argparse, json, hashlib
    from pathlib import Path
    p = argparse.ArgumentParser()
    p.add_argument("--finals", required=True)
    p.add_argument("--targets", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    raw, target_raw = Path(args.finals).read_bytes(), Path(args.targets).read_bytes()
    result = build(json.loads(raw), json.loads(target_raw))
    result["input_sha256"] = {"finals": hashlib.sha256(raw).hexdigest(),
                              "targets": hashlib.sha256(target_raw).hexdigest()}
    Path(args.out).write_text(json.dumps(result, sort_keys=True, indent=1, allow_nan=False))


if __name__ == "__main__":
    main()
