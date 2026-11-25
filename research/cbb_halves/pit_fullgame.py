"""Point-in-time (pregame-only) full-game CBB projections for the halves research (PAPER/0u).

This is a deliberately simple, transparent sequential efficiency model whose only job is to
supply honest *pregame* full-game projections for every historical game so the H1/H2 mapping
and its residual distributions can be fitted on chronological out-of-sample errors. It is not
the production full-game model (that is a separate workstream) and it never reads a game's own
result or any later game before projecting it.

State per team: offensive and defensive efficiency offsets (points per 100 possessions vs the
league mean) and a pace offset. All games on the same local (CT) date are projected first, then
the state is updated with those games' results (no same-day leakage). Between seasons team
offsets are shrunk toward zero.

Projection for home team h vs away team a:
    poss   = P + p_h + p_a
    eff_h  = E + o_h + d_a + (H/2 unless neutral)
    eff_a  = E + o_a + d_h - (H/2 unless neutral)
    pts_h  = eff_h * poss / 100,  pts_a = eff_a * poss / 100
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULTS = dict(k0=0.20, k_min=0.045, n_half=6.0, carry=0.65, k_league=0.002, k_hca=0.002,
                E0=103.0, P0=69.0, H0=3.5, k_pace_scale=1.0)


def team_possessions(cache: Path, seasons) -> pd.DataFrame:
    """Game-level possessions (mean of both teams' box estimates) from ESPN team box files."""
    out = []
    for y in seasons:
        tb = pd.read_parquet(cache / f"team_box_{y}.parquet",
                             columns=["game_id", "team_id", "field_goals_attempted",
                                      "offensive_rebounds", "turnovers", "total_turnovers",
                                      "free_throws_attempted"])
        to = pd.to_numeric(tb.total_turnovers, errors="coerce").fillna(
            pd.to_numeric(tb.turnovers, errors="coerce"))
        poss = (pd.to_numeric(tb.field_goals_attempted, errors="coerce")
                - pd.to_numeric(tb.offensive_rebounds, errors="coerce") + to
                + 0.475 * pd.to_numeric(tb.free_throws_attempted, errors="coerce"))
        g = pd.DataFrame({"game_id": tb.game_id.astype(int), "poss": poss}).groupby("game_id").poss.agg(["mean", "count"])
        g = g[(g["count"] == 2) & g["mean"].between(45, 110)]
        out.append(g["mean"].rename("fg_poss"))
    return pd.concat(out).reset_index()


def project(games: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """Return games with pregame projections. ``games`` must hold final scores and fg_poss
    (NaN allowed; then the pace state is not updated for that game)."""
    p = {**DEFAULTS, **(params or {})}
    g = games.copy()
    ts = pd.to_datetime(g.start_utc, utc=True)
    g["local_date"] = (ts - pd.Timedelta(hours=6)).dt.date
    g = g.sort_values(["local_date", "start_utc", "game_id"]).reset_index(drop=True)
    o = defaultdict(float); d = defaultdict(float); pc = defaultdict(float); n = defaultdict(int)
    E, P, H = p["E0"], p["P0"], p["H0"]
    season_prev = None
    out = np.full((len(g), 6), np.nan)
    for date, idx in g.groupby("local_date", sort=True).indices.items():
        blk = g.iloc[idx]
        season = int(blk.season.iloc[0])
        if season_prev is not None and season != season_prev:
            for dct in (o, d, pc):
                for k in list(dct):
                    dct[k] *= p["carry"]
            for k in list(n):
                n[k] = 0
        season_prev = season
        # 1) project every game of the day from the pre-day state
        for j, r in zip(idx, blk.itertuples(index=False)):
            hh = 0.0 if r.neutral_site else H / 2
            poss = P + pc[r.home_id] + pc[r.away_id]
            eh = E + o[r.home_id] + d[r.away_id] + hh
            ea = E + o[r.away_id] + d[r.home_id] - hh
            out[j] = (eh * poss / 100, ea * poss / 100, poss,
                      min(n[r.home_id], n[r.away_id]), n[r.home_id], n[r.away_id])
        # 2) update state with the day's results
        for j, r in zip(idx, blk.itertuples(index=False)):
            hh = 0.0 if r.neutral_site else H / 2
            poss_hat = out[j, 2]
            poss = r.fg_poss if np.isfinite(r.fg_poss) else poss_hat
            act_h = 100 * r.final_home / poss
            act_a = 100 * r.final_away / poss
            eh = E + o[r.home_id] + d[r.away_id] + hh
            ea = E + o[r.away_id] + d[r.home_id] - hh
            kh = max(p["k_min"], p["k0"] / (1 + n[r.home_id] / p["n_half"]))
            ka = max(p["k_min"], p["k0"] / (1 + n[r.away_id] / p["n_half"]))
            rh, ra = act_h - eh, act_a - ea
            o[r.home_id] += kh * rh; d[r.away_id] += ka * rh
            o[r.away_id] += ka * ra; d[r.home_id] += kh * ra
            if np.isfinite(r.fg_poss):
                rp = r.fg_poss - poss_hat
                pc[r.home_id] += p["k_pace_scale"] * kh * rp / 2
                pc[r.away_id] += p["k_pace_scale"] * ka * rp / 2
                P += p["k_league"] * rp
            E += p["k_league"] * (rh + ra) / 2
            if not r.neutral_site:
                H += p["k_hca"] * (rh - ra)
            n[r.home_id] += 1; n[r.away_id] += 1
    g[["proj_home", "proj_away", "proj_poss", "min_games", "n_home", "n_away"]] = out
    g["proj_margin"] = g.proj_home - g.proj_away
    g["proj_total"] = g.proj_home + g.proj_away
    return g
