"""Research-only baseline from SportsDataverse team box scores (PAPER/0u).

Derives estimated possessions, offensive efficiency, and defensive efficiency
from acquired team box scores. Does not fetch, invent event IDs, or promote
coefficients. All outputs are research artifacts.
"""
from __future__ import annotations
import math
from pathlib import Path
from typing import Dict, List

import pandas as pd

def estimate_possessions(row) -> float | None:
    """Standard possessions estimate. Reject if any required input is missing."""
    for col in ("field_goals_attempted", "free_throws_attempted", "offensive_rebounds", "turnovers"):
        v = row.get(col)
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            return None
    return (row["field_goals_attempted"]
            - row["offensive_rebounds"]
            + row["turnovers"]
            + 0.475 * row["free_throws_attempted"])

def build_team_season_summary(box: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-team offensive and defensive efficiency and pace."""
    rows = []
    for team, g in box.groupby("team_display_name"):
        poss = g.apply(estimate_possessions, axis=1)
        valid = poss.notna()
        poss = poss[valid]
        if len(poss) < 3 or poss.sum() <= 0:
            continue
        pts = g.loc[valid, "team_score"]
        opp_pts = g.loc[valid, "opponent_team_score"]
        rows.append({
            "team": team,
            "games": len(poss),
            "possessions_per_game": poss.mean(),
            "off_efficiency": 100 * pts.sum() / poss.sum(),
            "def_efficiency": 100 * opp_pts.sum() / poss.sum(),
            "net_efficiency": 100 * (pts.sum() - opp_pts.sum()) / poss.sum(),
        })
    return pd.DataFrame(rows).sort_values("net_efficiency", ascending=False)

def project_matchup(summary: pd.DataFrame, home: str, away: str) -> Dict:
    """Research projection using both offensive and defensive efficiency.

    Expected points = (team_off * opp_def / league_avg) * pace / 100.
    Requires both teams to have measured defense. PAPER/0u research only.
    """
    h = summary[summary["team"] == home]
    a = summary[summary["team"] == away]
    if h.empty or a.empty:
        return {"status": "MISSING_TEAM"}
    h, a = h.iloc[0], a.iloc[0]
    league_avg = summary["off_efficiency"].mean()
    if not math.isfinite(league_avg) or league_avg <= 0:
        return {"status": "INVALID_LEAGUE_AVG"}
    pace = (h["possessions_per_game"] + a["possessions_per_game"]) / 2
    home_pts = (h["off_efficiency"] * a["def_efficiency"] / league_avg) * pace / 100
    away_pts = (a["off_efficiency"] * h["def_efficiency"] / league_avg) * pace / 100
    return {
        "status": "RESEARCH_PROJECTION",
        "home": home,
        "away": away,
        "expected_home": round(home_pts, 1),
        "expected_away": round(away_pts, 1),
        "expected_margin": round(home_pts - away_pts, 1),
        "expected_total": round(home_pts + away_pts, 1),
        "pace": round(pace, 1),
        "games_home": int(h["games"]),
        "games_away": int(a["games"]),
        "league_avg_used": round(league_avg, 1),
        "label": "PAPER_0U_RESEARCH_BASELINE_BOTH_SIDES",
    }

if __name__ == "__main__":
    box = pd.read_parquet("/tmp/sdv/mbb_team_box_2027.parquet")
    summary = build_team_season_summary(box)
    print(summary.head(10).to_string(index=False))
    print("---")
    proj = project_matchup(summary, "Belmont Bruins", "St. Bonaventure Bonnies")
    print(proj)
