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

def estimate_possessions(row) -> float:
    """Standard possessions estimate. Use 'turnovers' not 'team_turnovers'."""
    fga = row.get("field_goals_attempted") or 0
    fta = row.get("free_throws_attempted") or 0
    orb = row.get("offensive_rebounds") or 0
    tov = row.get("turnovers") or 0  # not team_turnovers
    return fga - orb + tov + 0.475 * fta

def build_team_season_summary(box: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-team offensive and defensive efficiency and pace."""
    rows = []
    for team, g in box.groupby("team_display_name"):
        poss = g.apply(estimate_possessions, axis=1)
        pts = g["team_score"]
        opp_pts = g["opponent_team_score"]
        n = len(g)
        if n < 3 or poss.sum() <= 0:
            continue
        rows.append({
            "team": team,
            "games": n,
            "possessions_per_game": poss.mean(),
            "off_efficiency": 100 * pts.sum() / poss.sum(),
            "def_efficiency": 100 * opp_pts.sum() / poss.sum(),
            "net_efficiency": 100 * (pts.sum() - opp_pts.sum()) / poss.sum(),
        })
    return pd.DataFrame(rows).sort_values("net_efficiency", ascending=False)

def project_matchup(summary: pd.DataFrame, home: str, away: str) -> Dict:
    """Simple research projection using team efficiencies and average pace."""
    h = summary[summary["team"] == home]
    a = summary[summary["team"] == away]
    if h.empty or a.empty:
        return {"status": "MISSING_TEAM"}
    h, a = h.iloc[0], a.iloc[0]
    pace = (h["possessions_per_game"] + a["possessions_per_game"]) / 2
    home_pts = h["off_efficiency"] * pace / 100
    away_pts = a["off_efficiency"] * pace / 100
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
        "label": "PAPER_0U_RESEARCH_BASELINE",
    }

if __name__ == "__main__":
    box = pd.read_parquet("/tmp/sdv/mbb_team_box_2027.parquet")
    summary = build_team_season_summary(box)
    print(summary.head(10).to_string(index=False))
    print("---")
    proj = project_matchup(summary, "Belmont Bruins", "St. Bonaventure Bonnies")
    print(proj)
