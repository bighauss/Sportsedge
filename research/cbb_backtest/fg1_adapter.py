"""Adapter: plug the full-game stream's FG1 engine into this harness (research only).

FG1 lives in models/cbb/fullgame/ratings.py on branch grok-cbb/fullgame-ev-20261125
(head 3003e772 when this adapter was written). It is imported, never copied or
edited; when that package is not importable the adapter raises and the harness
records the model as unavailable.

Usage:
  PYTHONPATH=<checkout containing models/cbb/fullgame>:. python -m research.cbb_backtest.harness \
      --model FG1=research.cbb_backtest.fg1_adapter:build_fg1 ...

Protocol differences vs. that branch's own driver (documented, deliberate):
  * Fits at this harness's WEEKLY origins (games with day < origin), not daily.
  * D1 membership: teams with >= 15 finals in the PREVIOUS completed season
    (leak-free). The branch's driver uses the evaluated season's own end-of-season
    game counts for completed seasons, which is a population look-ahead.
  * HCA prior = mean of season-final h over all earlier seasons loaded here
    (2018 onward), with the branch's DEFAULT_FG1 hyper-parameters, which that
    branch chose on its TUNE seasons 2020-2022 (overlaps this harness's
    validation season 2022 - stated, not hidden).
"""
from datetime import date, timedelta

_CACHE = {}


def _fg():
    from models.cbb.fullgame import ratings as R, backtest as B
    return R, B


def _convert(games, d1):
    out = []
    for g in games:
        if g.get("possessions") is None:
            continue
        out.append({"game_id": g["event_id"], "date": g["day"].isoformat(), "season": g["season"],
                    "home": g["home"], "away": g["away"], "neutral": g["neutral"], "site": g["site"],
                    "home_points": g["home_points"], "away_points": g["away_points"],
                    "possessions": g["possessions"], "home_d1": g["home"] in d1, "away_d1": g["away"] in d1})
    return out


def _final(season, history):
    """Season-final FG fit for a completed season, D1 = teams with >=15 finals in that season."""
    key = ("final", season)
    if key not in _CACHE:
        from .models import d1_set
        R, B = _fg()
        games = history[season]
        _CACHE[key] = B.season_final(_convert(games, d1_set(games)))
    return _CACHE[key]


def build_fg1(prior, carry):
    R, B = _fg()
    from .models import d1_set
    hist = carry.get("_history") or {}
    season = carry.get("_season")
    if season is None or season - 1 not in hist:
        raise ValueError("FG1_NO_PREVIOUS_SEASON")
    prev = _final(season - 1, hist)
    hs = [_final(s, hist)[3] for s in sorted(hist) if s < season]
    cfg = B.fg1_config(prev, sum(hs) / len(hs), B.DEFAULT_FG1)
    d1 = d1_set(hist[season - 1])
    games = [g for g in _convert(prior, d1) if R.usable(g)]
    if not games:
        raise ValueError("FG1_NO_USABLE_PRIOR")
    origin = carry.get("_origin") or (max(date.fromisoformat(g["date"]) for g in games) + timedelta(days=1))
    f = R.AdjustedFit(lam=cfg["lam"], lam_pace=cfg["lam_pace"], half_life=cfg.get("half_life"),
                      prior=cfg["prior"], hca_prior=cfg["hca_prior"], hca_lam=cfg["hca_lam"],
                      mu0=cfg.get("mu0", 103.0), pi0=cfg.get("pi0", 68.0))
    f.default_prior = cfg["new_team"]
    f.fit(games, origin)
    site_of = {}

    def project(home, away, neutral, site=None):
        if not (f.has(home) and f.has(away)):
            raise ValueError("FG1_TEAM_UNRATED")
        st = site or ("NEUTRAL" if neutral else "HOME_VERIFIED")
        hp, ap, poss = f.project(home, away, st)
        return {"home_points": hp, "away_points": ap, "margin": hp - ap, "total": hp + ap, "possessions": poss,
                "hca_applied": f.h * poss / 100 if st == R.HOME else 0.0}
    project.wants_site = True
    project.fit = f
    return project
