"""Convert existing NFL DFS joint simulations into X+ research scenarios.

Does NOT invent touchdown order. FIRST_TD and SGPs containing FIRST_TD
must stay blocked until an independently validated ordered scoring feed exists.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path

DFS = Path(__file__).resolve().parents[1] / "models" / "nfl_dfs"


def generate(cfg, n=20000, seed=7, event_id=None):
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("EVENT_ID_REQUIRED")
    if type(n) is not int or n < 1000:
        raise ValueError("INSUFFICIENT_SIMS")
    import sys
    sys.path.insert(0, str(DFS))
    import showdown_mc as mc
    raw = []
    mc.run(cfg, n, seed=seed, raw=raw)
    teams = list(cfg["teams"])
    if len(teams) != 2:
        raise ValueError("TWO_TEAMS_REQUIRED")
    scenarios = []
    for sample in raw:
        players = {}
        for team in teams:
            for player, stats in sample[team][0].items():
                if player in players:
                    raise ValueError("PLAYER_ID_COLLISION")
                players[player] = dict(pass_yds=stats["py"], rush_yds=stats["ry"],
                                       rec_yds=stats["rcy"], receptions=stats["rec"])
        scenarios.append(dict(event_id=event_id, players=players))
    return scenarios
