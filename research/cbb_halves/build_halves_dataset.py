"""Build the per-game CBB halves dataset from public sportsdataverse ESPN files (PAPER/0u).

Input: the cache directory written by ``fetch_sdv.py`` (with its manifest.json).
Output: ``halves_games_<season>.csv`` (one row per admitted game), ``halves_rejections.csv`` (one
row per rejected game with a reason code) and ``halves_dataset_manifest.json`` (source hashes,
output hash, counts by season).

H1 score = cumulative score on the last play-by-play row of period 1. Final score = cumulative
score on the last row of the game. Regulation H2 = score at end of period 2 minus H1; OT points
are kept separately. Every admitted game must agree with the ESPN schedule final score, and
(where the schedule carries linescores) with the schedule's period-1 linescore.

Reason codes: NO_SCHEDULE_ROW, NOT_COMPLETED, NO_PERIOD_1, NO_PERIOD_2, FINAL_MISMATCH_SCHEDULE,
H1_MISMATCH_LINESCORE, SCORE_NOT_MONOTONE, TIED_FINAL, OT_WITHOUT_TIED_REGULATION,
IMPLAUSIBLE_SCORE, DUPLICATE_GAME_ID.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

PBP_COLS = ["game_id", "sequence_number", "game_play_number", "period_number", "home_score",
            "away_score", "type_text", "shooting_play", "team_id", "home_team_id", "away_team_id"]
SCHED_COLS = ["game_id", "season", "season_type", "start_date", "neutral_site",
              "conference_competition", "status_type_completed", "home_id", "away_id",
              "home_location", "away_location", "home_score", "away_score"]


def _linescore_first(v):
    """Period-1 value from an ESPN linescore cell (list of dicts, ndarray or string)."""
    if v is None:
        return None
    try:
        if isinstance(v, str):
            v = ast.literal_eval(v.replace("}\n {", "}, {").replace("} {", "}, {"))
        seq = list(v)
        if not seq:
            return None
        first = seq[0]
        val = first.get("value") if isinstance(first, dict) else None
        return None if val is None or (isinstance(val, float) and np.isnan(val)) else int(val)
    except Exception:
        return None


def half_possessions(p1: pd.DataFrame) -> pd.Series:
    """Estimated possessions in period 1 per game (mean of both teams' estimates)."""
    t = p1["type_text"].fillna("")
    is_fga = p1["shooting_play"].fillna(False).astype(bool) & ~t.str.contains("FreeThrow")
    is_fta = t.str.contains("FreeThrow")
    is_to = t.str.contains("Turnover")
    is_or = t.eq("Offensive Rebound")
    x = pd.DataFrame({"game_id": p1["game_id"], "team_id": p1["team_id"],
                      "fga": is_fga, "fta": is_fta, "to": is_to, "orb": is_or})
    x = x[x.team_id.notna()]
    g = x.groupby(["game_id", "team_id"])[["fga", "fta", "to", "orb"]].sum()
    poss = g.fga - g.orb + g.to + 0.475 * g.fta
    return poss.groupby("game_id").mean()


def build_season(cache: Path, season: int):
    pbp = pd.read_parquet(cache / f"play_by_play_{season}.parquet", columns=PBP_COLS)
    sched = pd.read_parquet(cache / f"mbb_schedule_{season}.parquet")
    lines = "home_linescores" in sched.columns
    sched = sched[SCHED_COLS + (["home_linescores", "away_linescores"] if lines else [])]
    # ESPN sequence_number is not chronological in 2025-26 files; game_play_number is.
    pbp = pbp.sort_values(["game_id", "period_number", "game_play_number"],
                          kind="mergesort")
    rej = []
    dup = sched.game_id.duplicated(keep=False)
    for gid in sched.loc[dup, "game_id"].unique():
        rej.append((season, gid, "DUPLICATE_GAME_ID"))
    sched = sched[~dup].set_index("game_id")
    pbp["home_score"] = pd.to_numeric(pbp.home_score, errors="coerce")
    pbp["away_score"] = pd.to_numeric(pbp.away_score, errors="coerce")
    grp = pbp.groupby("game_id")
    mono = grp.apply(lambda d: bool((d.home_score.diff().fillna(0) >= 0).all()
                                    and (d.away_score.diff().fillna(0) >= 0).all()),
                     include_groups=False)
    last = grp.tail(1).set_index("game_id")
    p1 = pbp[pbp.period_number == 1]
    end1 = p1.groupby("game_id").tail(1).set_index("game_id")
    end2 = pbp[pbp.period_number == 2].groupby("game_id").tail(1).set_index("game_id")
    nper = grp.period_number.max()
    h1poss = half_possessions(p1)
    rows = []
    for gid in pbp.game_id.unique():
        if gid not in sched.index:
            rej.append((season, gid, "NO_SCHEDULE_ROW")); continue
        s = sched.loc[gid]
        if not bool(s.status_type_completed):
            rej.append((season, gid, "NOT_COMPLETED")); continue
        if gid not in end1.index:
            rej.append((season, gid, "NO_PERIOD_1")); continue
        if gid not in end2.index:
            rej.append((season, gid, "NO_PERIOD_2")); continue
        if not mono.get(gid, False):
            rej.append((season, gid, "SCORE_NOT_MONOTONE")); continue
        fh, fa = last.loc[gid, "home_score"], last.loc[gid, "away_score"]
        h1h, h1a = end1.loc[gid, "home_score"], end1.loc[gid, "away_score"]
        r2h, r2a = end2.loc[gid, "home_score"], end2.loc[gid, "away_score"]
        if any(pd.isna(v) for v in (fh, fa, h1h, h1a, r2h, r2a)):
            rej.append((season, gid, "IMPLAUSIBLE_SCORE")); continue
        try:
            sh, sa = int(s.home_score), int(s.away_score)
        except (TypeError, ValueError):
            rej.append((season, gid, "FINAL_MISMATCH_SCHEDULE")); continue
        if (int(fh), int(fa)) != (sh, sa):
            rej.append((season, gid, "FINAL_MISMATCH_SCHEDULE")); continue
        if fh == fa:
            rej.append((season, gid, "TIED_FINAL")); continue
        n = int(nper[gid])
        if n > 2 and r2h != r2a:
            rej.append((season, gid, "OT_WITHOUT_TIED_REGULATION")); continue
        if n == 2 and (r2h, r2a) != (fh, fa):
            rej.append((season, gid, "FINAL_MISMATCH_SCHEDULE")); continue
        if not (10 <= h1h + h1a <= 150 and 60 <= fh + fa <= 300 and h1h <= fh and h1a <= fa):
            rej.append((season, gid, "IMPLAUSIBLE_SCORE")); continue
        ls_h = _linescore_first(s.home_linescores) if lines else None
        ls_a = _linescore_first(s.away_linescores) if lines else None
        if ls_h is not None and ls_a is not None and (ls_h, ls_a) != (int(h1h), int(h1a)):
            rej.append((season, gid, "H1_MISMATCH_LINESCORE")); continue
        rows.append({
            "season": season, "game_id": int(gid), "start_utc": str(s.start_date),
            "season_type": int(s.season_type), "neutral_site": bool(s.neutral_site),
            "conference_game": bool(s.conference_competition),
            "home_id": int(s.home_id), "away_id": int(s.away_id),
            "home": s.home_location, "away": s.away_location,
            "h1_home": int(h1h), "h1_away": int(h1a),
            "reg_home": int(r2h), "reg_away": int(r2a),
            "final_home": int(fh), "final_away": int(fa), "periods": n,
            "h1_poss_est": round(float(h1poss.get(gid, np.nan)), 2),
            "linescore_checked": ls_h is not None,
        })
    games = pd.DataFrame(rows)
    # Schedule games with no PBP at all
    no_pbp = set(sched.index) - set(pbp.game_id.unique())
    for gid in no_pbp:
        rej.append((season, gid, "NO_PBP" if bool(sched.loc[gid].status_type_completed) else "NOT_COMPLETED"))
    return games, pd.DataFrame(rej, columns=["season", "game_id", "reason"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seasons", default="2019-2026")
    a = ap.parse_args(argv)
    cache, out = Path(a.cache), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lo, hi = (int(x) for x in a.seasons.split("-"))
    src = json.loads((cache / "manifest.json").read_text())["files"]
    all_g, all_r = [], []
    for y in range(lo, hi + 1):
        g, r = build_season(cache, y)
        all_g.append(g); all_r.append(r)
        print(y, "admitted", len(g), "rejected", len(r), flush=True)
    games = pd.concat(all_g).sort_values(["start_utc", "game_id"]).reset_index(drop=True)
    rej = pd.concat(all_r).sort_values(["season", "game_id"]).reset_index(drop=True)
    files = {}
    for y, part in games.groupby("season"):
        b = part.to_csv(index=False, lineterminator="\n").encode()
        name = f"halves_games_{int(y)}.csv"
        (out / name).write_bytes(b)
        files[name] = {"rows": int(len(part)), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
    rej.to_csv(out / "halves_rejections.csv", index=False, lineterminator="\n")
    man = {
        "label": "PAPER_0U_NON_COUNTED_RESEARCH",
        "builder": "research/cbb_halves/build_halves_dataset.py",
        "sources": {k: {kk: v[kk] for kk in ("url", "bytes", "sha256")}
                    for k, v in sorted(src.items())
                    if v["season"] in range(lo, hi + 1) and v["kind"] in ("pbp", "schedule")},
        "outputs": files,
        "admitted_games": int(len(games)),
        "rejected_games": int(len(rej)),
        "by_season": {int(y): {"admitted": int((games.season == y).sum()),
                               "rejected": int((rej.season == y).sum()),
                               "linescore_checked": int(games.loc[games.season == y, "linescore_checked"].sum()),
                               "overtime": int((games.loc[games.season == y, "periods"] > 2).sum()),
                               "first_utc": games.loc[games.season == y, "start_utc"].min(),
                               "last_utc": games.loc[games.season == y, "start_utc"].max()}
                      for y in range(lo, hi + 1)},
        "rejections_by_reason": {k: int(v) for k, v in rej.reason.value_counts().items()},
    }
    (out / "halves_dataset_manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: man[k] for k in ("admitted_games", "rejected_games", "rejections_by_reason")}))


if __name__ == "__main__":
    main()
