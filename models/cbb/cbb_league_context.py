"""Run the frozen incumbent CBB projection with current-season league constants, plus a research margin variant.

PAPER / research only. The incumbent file is never edited. Module globals are overridden for one call and
restored; NOT thread-safe, so do not use concurrently in production.

project_ratings_anchored is an UNVALIDATED research variant: ratings_ppp + w*(matchup_ppp - league baseline).
It exists because the incumbent's 50/50 blend with a league-anchored, K=12-regressed four-factor leg halves
early-season mismatch margins. It must pass a check against real final scores before any use.
"""
from __future__ import annotations
import contextlib
import sportsedge_cbb_model as M

@contextlib.contextmanager
def league_context(league):
    saved = dict(M.LEAGUE)
    try:
        M.LEAGUE.update(oe=league["oe"], tempo=league["tempo"], efg=league["efg"], tov=league["tov"],
                        orb=league["orb"], ftr=league["ftr"], three_p=league["three_p"])
        yield
    finally:
        M.LEAGUE.clear(); M.LEAGUE.update(saved)

def project(game, teams, league=None):
    if league is None: return M.project_game(game, teams, {}, {})
    with league_context(league): return M.project_game(game, teams, {}, {})

def _anchored(game, teams, w):
    h, a = teams[game["home"]], teams[game["away"]]
    poss = M.possessions(h, a); base = M.LEAGUE["oe"] / 100
    ph = M.ratings_ppp(h, a) + w * (M.matchup_ppp(h, a) - base); pa = M.ratings_ppp(a, h) + w * (M.matchup_ppp(a, h) - base)
    adj, notes = M.adjustments(game, h, a, {}, {})
    hp, ap = ph * poss + adj["home"], pa * poss + adj["away"]
    gap = (M.ratings_ppp(h, a) - M.ratings_ppp(a, h)) * poss + adj["home"] - adj["away"]
    return dict(home_pts=hp, away_pts=ap, margin=hp - ap, total=hp + ap, poss=poss, notes=notes, ratings_margin=gap)

def project_ratings_anchored(game, teams, league=None, w=0.5):
    if not 0.0 <= w <= 1.0: raise ValueError("w must be in [0,1]")
    if league is None: return _anchored(game, teams, w)
    with league_context(league): return _anchored(game, teams, w)

def ratings_gap_margin(game, teams, league=None):
    return project_ratings_anchored(game, teams, league, w=0.0)["margin"]
