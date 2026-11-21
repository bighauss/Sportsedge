"""Regression tests for the 2026-11-21 CBB fixes (stdlib only, network off).

Run: python3 test_cbb_league_fix.py
"""
import os, socket, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
socket.socket = None
import sportsedge_cbb_model as m


def team(name, oe, de, t, games=5, ff=True):
    r = dict(team=name, games=games, adjoe=oe, adjde=de, adj_t=t)
    if ff:
        r.update(efg_o=52.0, efg_d=49.0, tov_o=17.0, tov_d=18.5, orb_o=30.0, orb_d=28.0, ftr_o=33.0, ftr_d=31.0)
    return r


def main():
    # 1. league constants match the current Torvik D-I scale
    assert m.LEAGUE["oe"] == 107.0 and m.LEAGUE["tempo"] == 69.0

    # 2. two exactly-average teams on a neutral floor project the league-average total
    avg = team("A", 107.0, 107.0, 69.0, ff=False)
    avg2 = team("B", 107.0, 107.0, 69.0, ff=False)
    p = m.project_game({"home": "A", "away": "B", "neutral": 1}, {"A": avg, "B": avg2}, {}, {})
    assert abs(p["total"] - 2 * 1.07 * 69.0) < 1e-9, p
    assert abs(p["margin"]) < 1e-9

    # 3. without four factors the ratings leg is used alone (no silent drag to average)
    strong = team("S", 120.0, 95.0, 70.0, ff=False)
    weak = team("W", 98.0, 112.0, 68.0, ff=False)
    teams = {"S": strong, "W": weak}
    p = m.project_game({"home": "S", "away": "W", "neutral": 1}, teams, {}, {})
    poss = m.possessions(strong, weak)
    assert abs(p["home_pts"] - m.ratings_ppp(strong, weak) * poss) < 1e-9
    assert "ratings-only (no four factors)" in p["notes"]

    # 4. with four factors the original 50/50 ratings/matchup blend is kept
    s2, w2 = team("S", 120.0, 95.0, 70.0), team("W", 98.0, 112.0, 68.0)
    p2 = m.project_game({"home": "S", "away": "W", "neutral": 1}, {"S": s2, "W": w2}, {}, {})
    poss2 = m.possessions(s2, w2)
    exp = (0.5 * m.ratings_ppp(s2, w2) + 0.5 * m.matchup_ppp(s2, w2)) * poss2
    assert abs(p2["home_pts"] - exp) < 1e-9
    assert "ratings-only (no four factors)" not in p2["notes"]

    # 5. league override + full-file estimate guard
    try:
        m.league_from_teams({"A": avg})
        raise AssertionError("league_from_teams must refuse a partial team file")
    except ValueError:
        pass
    full = {f"T{i}": team(f"T{i}", 100.0 + i % 15, 114.0 - i % 15, 67.0 + i % 4) for i in range(320)}
    lg = m.league_from_teams(full)
    assert abs(lg["oe"] - 107.0) < 1e-9
    m.set_league(oe=107.0, tempo=69.0)
    print("ALL LEAGUE-FIX TESTS PASSED")


if __name__ == "__main__":
    main()
