"""Inputs for the CBB rolling-origin backtest: SDV/ESPN finals + ESPN historical odds.

Finals: sportsdataverse-data releases mbb_schedule_{season}.parquet and
team_box_{season}.parquet, admitted with the repo's own
research.cbb_hca.public_factorial_backtest.schedule_games (read-only reuse).

Odds: compact ESPN core-API odds records collected by espn_odds_collect.py.
One market row per game is selected by a FIXED provider preference (sportsbooks
only; model "providers" and live odds are excluded). The provider used is
recorded on every row. Nothing is imputed: a missing price stays missing.
"""
import gzip
import json
from pathlib import Path

SCHED_URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_mens_college_basketball_schedules/mbb_schedule_{s}.parquet"
BOX_URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_mens_college_basketball_team_boxscores/team_box_{s}.parquet"
ODDS_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/events/{id}/competitions/{id}/odds"

# Fixed before evaluation: DraftKings first (the book the card prices against),
# then other US books by typical availability. Excluded: numberfire(1003),
# teamrankings(1002), accuscore(1001) = models/aggregators; 59/200 = live odds.
# DraftKings appears as provider 40 (through 2024-25) and 100 (2025-26).
EXCLUDED_PROVIDERS = {"1001", "1002", "1003", "59", "200"}  # models + live-odds feeds (59 ESPN BET live, 200 DraftKings live)
PROVIDER_PREFERENCE = ("100", "40", "58", "45", "52", "57", "47", "41", "36", "50", "53",
                       "1004")


# Market data-quality quarantine (season -> families). Decided from integrity checks
# documented in RESULTS.md; independently matches the full-game stream ("2023 ML only").
# 2023 close spread/total come from ESPN 'current' fallback and are inconsistent with
# finals (spread residual mean -5.63, MAE 14.3 vs 8.6-9.1 in every other season;
# 6.8% of totals outside [110,190] vs <=0.2% elsewhere). ML 2023 passes.
MARKET_QUARANTINE = {2023: ("spread", "total")}
# ESPN 'open' nodes fail validation (37% of open totals differ from close by >15 points,
# decimal prices in total fields, spread sign flips) -> no open-price ROI or CLV.
OPEN_LINES_STATUS = "BLOCKED_OPEN_LINES_FAIL_VALIDATION"


def quarantine(m, season):
    if not m:
        return m
    fams = MARKET_QUARANTINE.get(season, ())
    m = dict(m)
    if "spread" in fams:
        for k in ("close_spread_home", "close_spread_price_home", "close_spread_price_away"):
            m[k] = None
    if "total" in fams:
        for k in ("close_total", "close_over_price", "close_under_price"):
            m[k] = None
    for k in list(m):
        if k.startswith("open_"):
            m[k] = None
    m["quarantined_families"] = ",".join(fams)
    return m


def site_class(neutral, venue_id, home_venue_id):
    """Same rule as models/cbb/fullgame/sdv_loader.site_class (re-implemented, not imported)."""
    def vid(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return str(int(f)) if f == f and f > 0 and f.is_integer() else None
    if neutral is True:
        return "NEUTRAL"
    v, hv = vid(venue_id), vid(home_venue_id)
    if neutral is False and v is not None and v == hv:
        return "HOME_VERIFIED"
    return "UNVERIFIED"


def load_games(root, season):
    import pyarrow.parquet as pq
    from research.cbb_hca.public_factorial_backtest import schedule_games, SCHED, BOX
    root = Path(root)
    s = pq.read_table(root / f"mbb_schedule_{season}.parquet", columns=list(SCHED)).to_pylist()
    b = pq.read_table(root / f"team_box_{season}.parquet", columns=list(BOX)).to_pylist()
    games, census, rejects = schedule_games(s, b, season)
    venue = {str(r["game_id"]): (r.get("venue_id"), r.get("home_venue_id")) for r in
             pq.read_table(root / f"mbb_schedule_{season}.parquet", columns=["game_id", "venue_id", "home_venue_id"]).to_pylist()}
    for g in games:
        g["season"] = season
        v = venue.get(g["event_id"], (None, None))
        g["site"] = site_class(g["neutral"], *v)
    return games, census


def _price_ok(x):
    return isinstance(x, (int, float)) and abs(x) >= 100


def select_market(items):
    """Pick one sportsbook record; return compact market dict or None.

    Close fields fall back to ESPN's top-level 'current' fields only when the
    explicit close node is absent (ESPN's current == last pregame for finals);
    the fallback is flagged on the row.
    """
    by = {it["provider_id"]: it for it in items if it["provider_id"] not in EXCLUDED_PROVIDERS}
    for pid in PROVIDER_PREFERENCE:
        it = by.get(pid)
        if not it:
            continue
        m = {"provider_id": pid, "provider": it["provider"]}
        fb = False
        def pick(close_key, cur_key):
            nonlocal fb
            v = it.get(close_key)
            if v is None and it.get(cur_key) is not None:
                fb = True
                return it.get(cur_key)
            return v
        m["close_spread_home"] = pick("close_spread_home", "current_spread_home")
        m["close_spread_price_home"] = pick("close_spread_price_home", "current_spread_price_home")
        m["close_spread_price_away"] = pick("close_spread_price_away", "current_spread_price_away")
        m["close_total"] = pick("close_total", "current_total")
        m["close_over_price"] = pick("close_over_price", "current_over_price")
        m["close_under_price"] = pick("close_under_price", "current_under_price")
        m["close_ml_home"] = pick("close_ml_home", "current_ml_home")
        m["close_ml_away"] = pick("close_ml_away", "current_ml_away")
        for k in ("open_spread_home", "open_spread_price_home", "open_spread_price_away", "open_total",
                  "open_over_price", "open_under_price", "open_ml_home", "open_ml_away"):
            m[k] = it.get(k)
        for k in list(m):
            if "price" in k or "_ml_" in k:
                v = m[k]
                m[k] = int(v) if _price_ok(v) else None
        m["close_from_current_fallback"] = fb
        if m["close_spread_home"] is None and m["close_total"] is None and m["close_ml_home"] is None:
            continue
        return m
    return None


def load_odds(path):
    out, census = {}, {"games": 0, "http_404": 0, "fetch_failed": 0, "no_items": 0, "no_book": 0, "selected": 0}
    with gzip.open(path, "rt") as f:
        for line in f:
            d = json.loads(line)
            census["games"] += 1
            if d["http"] == 404:
                census["http_404"] += 1; continue
            if d["http"] != 200:
                census["fetch_failed"] += 1; continue
            if not d["items"]:
                census["no_items"] += 1; continue
            m = select_market(d["items"])
            if m is None:
                census["no_book"] += 1; continue
            census["selected"] += 1
            out[str(d["game_id"])] = m
    return out, census
