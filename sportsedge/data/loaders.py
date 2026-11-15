"""SportsEdge unified free-data loaders (all six sports).

Each loader returns (data, meta). meta records source, package version, pull time (UTC) and
any error. A failed source returns data=None with the error. The loaders never invent or
zero-fill numbers (RUN IT v2.1: missing -> fallback with lower confidence, or skip).

Install: pip install -r requirements.txt
"""
from __future__ import annotations

import datetime as _dt
import importlib
import io
import urllib.request


def _meta(source: str, package: str | None = None, error: str | None = None) -> dict:
    version = None
    if package:
        try:
            version = importlib.import_module(package).__version__
        except Exception:  # package missing or no __version__
            version = None
    return {
        "source": source,
        "package": package,
        "package_version": version,
        "pulled_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "error": error,
    }


def _safe(source, package, fn):
    try:
        return fn(), _meta(source, package)
    except Exception as exc:  # report, never fabricate
        return None, _meta(source, package, f"{type(exc).__name__}: {exc}")


# ---------------- NFL (nflverse via nflreadpy) ----------------
def nfl_pbp(seasons):
    import nflreadpy as nfl
    return _safe("nflverse pbp", "nflreadpy", lambda: nfl.load_pbp(seasons))


def nfl_nextgen(stat_type, seasons=None):
    """stat_type: 'passing' | 'receiving' | 'rushing'."""
    import nflreadpy as nfl
    if seasons is None:
        return _safe(f"nflverse ngs {stat_type}", "nflreadpy",
                     lambda: nfl.load_nextgen_stats(stat_type=stat_type))
    return _safe(f"nflverse ngs {stat_type}", "nflreadpy",
                 lambda: nfl.load_nextgen_stats(seasons, stat_type=stat_type))


def nfl_core(seasons):
    """Everything the NFL RUN IT standard + NGS addendum uses."""
    import nflreadpy as nfl
    out = {
        "pbp": nfl_pbp(seasons),
        "ngs_passing": nfl_nextgen("passing"),
        "ngs_receiving": nfl_nextgen("receiving"),
        "ngs_rushing": nfl_nextgen("rushing"),
    }
    for name, fn in {
        "player_stats": nfl.load_player_stats,
        "injuries": nfl.load_injuries,
        "snap_counts": nfl.load_snap_counts,
        "depth_charts": nfl.load_depth_charts,
        "schedules": nfl.load_schedules,
    }.items():
        out[name] = _safe(f"nflverse {name}", "nflreadpy", lambda fn=fn: fn(seasons))
    return out


# ---------------- CFB ----------------
def cfb_pbp(seasons):
    def _f():
        from sportsdataverse.cfb import load_cfb_pbp
        return load_cfb_pbp(seasons=seasons)
    return _safe("sportsdataverse cfb pbp", "sportsdataverse", _f)


def cfbd_get(path: str, api_key: str, **params):
    """CollegeFootballData API (free key). path e.g. '/stats/season/advanced'."""
    import json
    import urllib.parse

    def _f():
        q = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"https://api.collegefootballdata.com{path}?{q}",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    return _safe(f"CFBD {path}", None, _f)


# ---------------- CBB (BartTorvik) ----------------
def barttorvik_teams(season_end_year: int):
    """Nov 2026 games belong to the 2027 season. Check the header row on first use."""
    import pandas as pd

    def _f():
        url = f"https://barttorvik.com/{season_end_year}_team_results.csv"
        with urllib.request.urlopen(url, timeout=30) as r:
            return pd.read_csv(io.BytesIO(r.read()))
    return _safe(f"barttorvik {season_end_year}_team_results", "pandas", _f)


# ---------------- NBA ----------------
def nba_team_advanced(season: str = "2026-27", last_n_games: int = 0):
    def _f():
        from nba_api.stats.endpoints import leaguedashteamstats
        return leaguedashteamstats.LeagueDashTeamStats(
            season=season, measure_type_detailed_defense="Advanced",
            last_n_games=last_n_games,
        ).get_data_frames()[0]
    return _safe(f"nba_api team advanced L{last_n_games}", "nba_api", _f)


def nba_team_four_factors(season: str = "2026-27"):
    def _f():
        from nba_api.stats.endpoints import leaguedashteamstats
        return leaguedashteamstats.LeagueDashTeamStats(
            season=season, measure_type_detailed_defense="Four Factors",
        ).get_data_frames()[0]
    return _safe("nba_api team four factors", "nba_api", _f)


# ---------------- NHL (MoneyPuck) ----------------
def moneypuck(kind: str = "teams", season_start_year: int = 2026):
    """kind: 'teams' | 'goalies' | 'skaters'. Confirm column meanings against the data dictionary."""
    import pandas as pd

    def _f():
        url = (f"https://moneypuck.com/moneypuck/playerData/seasonSummary/"
               f"{season_start_year}/regular/{kind}.csv")
        with urllib.request.urlopen(url, timeout=30) as r:
            return pd.read_csv(io.BytesIO(r.read()))
    return _safe(f"moneypuck {kind} {season_start_year}", "pandas", _f)


# ---------------- MLB (Statcast) ----------------
def statcast_range(start_dt: str, end_dt: str):
    def _f():
        from pybaseball import statcast
        return statcast(start_dt=start_dt, end_dt=end_dt)
    return _safe(f"statcast {start_dt}..{end_dt}", "pybaseball", _f)


def fangraphs_tables(season: int):
    def _f():
        from pybaseball import batting_stats, pitching_stats
        return {"batting": batting_stats(season), "pitching": pitching_stats(season)}
    return _safe(f"fangraphs {season}", "pybaseball", _f)


if __name__ == "__main__":
    import sys
    data, meta = nfl_nextgen("receiving")
    print(meta)
    sys.exit(0 if meta["error"] is None else 1)
