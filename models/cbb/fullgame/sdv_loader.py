"""Load public sportsdataverse (ESPN) CBB schedule + team-box parquet into plain game dicts.

RESEARCH ONLY (PAPER / 0u, NON_COUNTED). Retrospective public releases, not archived pre-tip
receipts. pandas/pyarrow are imported lazily so the pure-python model modules and their
stdlib unittest suite do not need them.

Site classes (home-court is applied ONLY to HOME_VERIFIED):
  NEUTRAL        schedule neutral_site is True
  HOME_VERIFIED  neutral_site is False AND the game venue_id equals the home team's ESPN home venue_id
  UNVERIFIED     neutral_site is False but venue missing or different from the home team's venue
Possessions = mean over both teams of FGA - OREB + TO + 0.475 * FTA (rows lacking a two-team box
keep possessions None and are never estimated).
"""
from __future__ import annotations
import csv
import math
from pathlib import Path

URL = ("https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
       "espn_mens_college_basketball_{kind}/{name}")
FIELDS = ("game_id", "season", "date", "tip_utc", "home", "away", "home_name", "away_name",
          "site", "neutral", "venue_id", "home_venue_id", "home_points", "away_points",
          "possessions", "season_type", "home_d1", "away_d1")
D1_MIN_GAMES = 15   # season membership proxy: a team with >= 15 finals in the season file


def _vid(v):
    """Canonical venue id string ('3604.0' and 3604 are the same id); None if missing."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f <= 0 or not f.is_integer():
        return None
    return str(int(f))


def site_class(neutral, venue_id, home_venue_id):
    if neutral is True:
        return "NEUTRAL"
    v, hv = _vid(venue_id), _vid(home_venue_id)
    if neutral is False and v is not None and v == hv:
        return "HOME_VERIFIED"
    return "UNVERIFIED"


def possessions(fga, oreb, tov, fta):
    vals = (fga, oreb, tov, fta)
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals):
        return None
    p = float(fga) - float(oreb) + float(tov) + 0.475 * float(fta)
    return p if 40 <= p <= 110 else None


def load_season(root, season, d1_set=None):
    """``d1_set``: explicit D1 team ids (used for an in-progress season, e.g. the previous season's set)."""
    import pandas as pd  # lazy
    root = Path(root)
    s = pd.read_parquet(root / f"mbb_schedule_{season}.parquet")
    b = pd.read_parquet(root / f"team_box_{season}.parquet")
    s = s[(s.status_type_completed == True) & (s.status_type_name == "STATUS_FINAL")]  # noqa: E712
    tov_col = "total_turnovers" if "total_turnovers" in b.columns else "turnovers"
    poss = {}
    for gid, grp in b.groupby("game_id"):
        if len(grp) != 2:
            continue
        ps = [possessions(r.field_goals_attempted, r.offensive_rebounds, getattr(r, tov_col),
                          r.free_throws_attempted) for r in grp.itertuples()]
        if all(p is not None for p in ps):
            poss[int(gid)] = sum(ps) / 2
    out = []
    dup = s.game_id.value_counts()
    for r in s.itertuples():
        gid = int(r.game_id)
        if dup[r.game_id] != 1:
            continue
        try:
            hp, ap = int(r.home_score), int(r.away_score)
        except (TypeError, ValueError):
            continue
        if hp == ap or r.home_id == r.away_id:
            continue
        neutral = bool(r.neutral_site) if r.neutral_site in (True, False) else None
        out.append({
            "game_id": str(gid), "season": int(season), "date": str(r.game_date)[:10],
            "tip_utc": str(r.date), "home": str(r.home_id), "away": str(r.away_id),
            "home_name": r.home_display_name, "away_name": r.away_display_name,
            "site": site_class(neutral, r.venue_id, r.home_venue_id), "neutral": neutral,
            "venue_id": _vid(r.venue_id), "home_venue_id": _vid(r.home_venue_id),
            "home_points": hp, "away_points": ap, "possessions": poss.get(gid),
            "season_type": int(r.season_type) if r.season_type == r.season_type else None})
    cnt = {}
    for g in out:
        for t in (g["home"], g["away"]):
            cnt[t] = cnt.get(t, 0) + 1
    for g in out:
        g["home_d1"] = (g["home"] in d1_set) if d1_set is not None else cnt[g["home"]] >= D1_MIN_GAMES
        g["away_d1"] = (g["away"] in d1_set) if d1_set is not None else cnt[g["away"]] >= D1_MIN_GAMES
    out.sort(key=lambda g: (g["tip_utc"], g["game_id"]))
    return out


def write_csv(rows, path):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in FIELDS})


def read_csv(path):
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            r["season"] = int(r["season"])
            r["home_points"], r["away_points"] = int(r["home_points"]), int(r["away_points"])
            r["possessions"] = float(r["possessions"]) if r["possessions"] not in ("", "None") else None
            r["neutral"] = {"True": True, "False": False}.get(r["neutral"])
            for k in ("home_d1", "away_d1"):
                r[k] = r.get(k) == "True"
            rows.append(r)
    return rows


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seasons", nargs="+", type=int, required=True)
    ap.add_argument("--in-progress-last", action="store_true",
                    help="last season is in progress: D1 membership = previous season's D1 set")
    a = ap.parse_args()
    ap2 = None
    for s in a.seasons:
        prev = Path(a.out) / f"games_{s - 1}.csv"
        d1 = None
        if s == max(a.seasons) and a.in_progress_last and prev.exists():
            d1 = {t for r in read_csv(prev) for t, k in ((r["home"], "home_d1"), (r["away"], "away_d1")) if r[k]}
        rows = load_season(a.root, s, d1)
        write_csv(rows, Path(a.out) / f"games_{s}.csv")
        print(s, len(rows), sum(r["possessions"] is not None for r in rows),
              {k: sum(r["site"] == k for r in rows) for k in ("HOME_VERIFIED", "NEUTRAL", "UNVERIFIED")})
