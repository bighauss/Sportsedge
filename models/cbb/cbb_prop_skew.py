"""Versioned CBB player-prop challenger: market-blind mean + CBB skew distribution (opt-in).

The pinned model (sportsedge_cbb_model.py, unchanged) prices props with a symmetric normal
around 0.7*model + 0.3*market-implied mean, then blends probability 30/70 with the market.
On the untouched 2023-25 holdout (PR #576 / research/prop_variance/cbb_prop_skew_v1_validation.json)
that normal overstates P(over) by +2 to +17 pts. This challenger:
  * uses the pinned project_prop mean ONLY (no quote input, no market blend),
  * prices over/push/under with the CBB-only skew table (fitted on 2021-22, 2022-23),
  * computes push-aware EV on both captured sides,
  * keeps EVERY evaluated prop (coverage) and marks eligibility separately; no stars.
PAPER / 0u / NON_COUNTED.
"""
from __future__ import annotations
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(os.path.dirname(HERE))]
import sportsedge_cbb_model as M  # noqa: E402
from sportsedge.markets import prop_skew as PS  # noqa: E402

DISTRIBUTION = "cbb-prop-skew-v1"
TABLE = os.path.join(HERE, "prop_skew_cbb_v1_table.json")


def _dec(price):
    v = float(price)
    if not math.isfinite(v) or v != int(v) or abs(v) < 100:
        raise ValueError("INVALID_AMERICAN_PRICE")
    return M.am_to_dec(int(v))


def price_props_skew(inputs):
    """Return {'distribution', 'rows', 'withheld'} for every captured prop in inputs."""
    teams = M.load_teams(inputs["teams"]); players = M.load_players(inputs.get("players"))
    games = M.read_csv(inputs["games"]); inj = {}
    for r in M.read_csv(inputs.get("injuries")):
        inj.setdefault(r["team"], []).append(r)
    projs = {g["game_id"]: (g, M.project_game(g, teams, inj, players)) for g in games}
    tab = PS.load(TABLE)
    rows, withheld = [], []
    for p in M.read_csv(inputs.get("props")):
        tag = {"game_id": p.get("game_id"), "player": p.get("player"), "stat": p.get("stat"), "line": p.get("line")}
        if p.get("game_id") not in projs:
            withheld.append({**tag, "reason": "PROP_EVENT_NOT_FOUND"}); continue
        g, pj = projs[p["game_id"]]
        pl, reason = M.resolve_prop_player(g, p, players)
        if reason:
            withheld.append({**tag, "reason": reason}); continue
        out = {i["player"] for i in inj.get(pl["team"], []) if i.get("status", "").lower() == "out"}
        if pl["player"] in out:
            withheld.append({**tag, "reason": "PLAYER_OUT"}); continue
        home = pl["team"] == g["home"]
        tp = pj["home_pts"] if home else pj["away_pts"]
        opp = teams[g["away"] if home else g["home"]]
        o_, _, _, _ = M.team_eff(teams[pl["team"]])
        mean = M.project_prop(pl, p["stat"], tp, o_ / 100 * pj["poss"], opp, players.get(pl["team"]))
        try:
            line = float(p["line"])
            po, pp, pu = PS.three_way(tab, p["stat"], mean, line)
            d_over, d_under = _dec(p["over_price"]), _dec(p["under_price"])
        except (KeyError, TypeError, ValueError) as exc:
            withheld.append({**tag, "reason": "NOT_PRICED", "detail": str(exc)}); continue
        nv = M.novig(p["over_price"], p["under_price"])
        for side, prob, opp_prob, dec in (("over", po, pu, d_over), ("under", pu, po, d_under)):
            ev = prob * (dec - 1) - opp_prob
            rows.append({"distribution": DISTRIBUTION, "game_id": p["game_id"], "player": p["player"],
                         "team": pl["team"], "stat": p["stat"], "line": line, "side": side,
                         "price": int(float(p[side + "_price"])), "model_mean": mean,
                         "p_win": prob, "p_push": pp, "p_loss": opp_prob,
                         "market_novig_p": nv if side == "over" else 1 - nv, "raw_ev": ev,
                         "eligible": ev > 0, "stars": None, "state": "PAPER_0U_NON_COUNTED",
                         "approved_stake_u": 0})
    return {"distribution": DISTRIBUTION, "rows": rows, "withheld": withheld}
