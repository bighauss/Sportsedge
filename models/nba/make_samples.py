"""Write SYNTHETIC sample inputs for the NBA model test (made-up stats and odds).

Run: python3 make_samples.py  -> sample/*.csv
Player names are only labels the test looks for; every number is fake.
"""
import csv, os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sample")


def w(name, rows):
    with open(os.path.join(OUT, name + ".csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader(); wr.writerows(rows)


def team(t, rating, ortg, drtg, pace):
    return dict(team=t, games=12, rating=rating, ortg=ortg, drtg=drtg, pace=pace,
                ortg_l15=ortg + 0.8, drtg_l15=drtg - 0.4, efg=0.545, tov=0.130, orb=0.27, ftr=0.24,
                opp_efg=0.535, opp_tov=0.135, opp_orb=0.28, opp_ftr=0.23)


def player(name, t, pos, starter, mins, use, pts, reb, ast, fg3):
    return dict(player=name, team=t, pos=pos, starter=starter, minutes=mins, usage=use,
                pts_pm=pts, reb_pm=reb, ast_pm=ast, fg3m_pm=fg3)


def main():
    os.makedirs(OUT, exist_ok=True)
    w("teams", [team("DEN", 4.0, 118.5, 113.0, 98.5), team("LAL", 1.5, 116.0, 114.5, 100.5),
                team("BOS", 5.5, 120.0, 111.5, 97.0), team("MIA", -1.0, 112.5, 113.5, 96.5)])
    w("games", [dict(game_id="G1", date="2026-11-15", tipoff_et="21:00", home="DEN", away="LAL", neutral=0,
                     home_b2b=1, away_b2b=0, home_3in4=0, away_3in4=0, away_tz_shift=1),
                dict(game_id="G2", date="2026-11-15", tipoff_et="19:30", home="BOS", away="MIA", neutral=0,
                     home_b2b=0, away_b2b=1, home_3in4=0, away_3in4=1, away_tz_shift=0)])
    w("injuries", [dict(team="DEN", player="Aaron Gordon", status="OUT", minutes=30, on_off_net=3.5),
                   dict(team="MIA", player="Guard M2", status="QUESTIONABLE", minutes=26, on_off_net=2.0)])
    roster = [
        player("Guard D1", "DEN", "G", 1, 34, 0.24, 0.62, 0.15, 0.25, 0.08),
        player("Guard D2", "DEN", "G", 1, 31, 0.20, 0.50, 0.12, 0.12, 0.09),
        player("Aaron Gordon", "DEN", "F", 1, 30, 0.18, 0.48, 0.22, 0.10, 0.03),
        player("Peyton Watson", "DEN", "F", 0, 14, 0.15, 0.40, 0.18, 0.06, 0.04),
        player("Big D5", "DEN", "C", 1, 34, 0.29, 0.78, 0.36, 0.28, 0.03),
        player("Bench D6", "DEN", "G", 0, 18, 0.17, 0.42, 0.10, 0.10, 0.07),
        player("Guard L1", "LAL", "G", 1, 35, 0.31, 0.75, 0.22, 0.24, 0.07),
        player("Wing L2", "LAL", "F", 1, 34, 0.27, 0.70, 0.22, 0.12, 0.06),
        player("Big L3", "LAL", "C", 1, 32, 0.22, 0.55, 0.35, 0.08, 0.01),
        player("Guard L4", "LAL", "G", 1, 29, 0.17, 0.42, 0.10, 0.12, 0.10),
        player("Wing L5", "LAL", "F", 1, 27, 0.15, 0.38, 0.17, 0.06, 0.06),
        player("Guard B1", "BOS", "G", 1, 34, 0.28, 0.72, 0.15, 0.17, 0.12),
        player("Wing B2", "BOS", "F", 1, 36, 0.31, 0.78, 0.24, 0.13, 0.10),
        player("Big B3", "BOS", "C", 1, 28, 0.18, 0.46, 0.30, 0.07, 0.05),
        player("Guard M1", "MIA", "G", 1, 34, 0.25, 0.60, 0.14, 0.18, 0.09),
        player("Guard M2", "MIA", "G", 1, 26, 0.20, 0.52, 0.10, 0.16, 0.08),
        player("Big M3", "MIA", "C", 1, 33, 0.24, 0.58, 0.32, 0.12, 0.02),
    ]
    w("players", roster)
    w("positional_defense", [dict(team="LAL", pos="C", pts_f=1.06, reb_f=1.04, ast_f=1.03, fg3m_f=1.00),
                             dict(team="DEN", pos="G", pts_f=1.03, reb_f=1.00, ast_f=1.02, fg3m_f=1.05)])
    odds = []
    for gid, h, a, spread, total in (("G1", "DEN", "LAL", -3.5, 229.5), ("G2", "BOS", "MIA", -8.5, 216.5)):
        odds += [dict(game_id=gid, market="ML", selection=h, line="", price=-160),
                 dict(game_id=gid, market="ML", selection=a, line="", price=140),
                 dict(game_id=gid, market="SPREAD", selection=h, line=spread, price=-104),
                 dict(game_id=gid, market="SPREAD", selection=a, line=-spread, price=-104),
                 dict(game_id=gid, market="TOTAL", selection="OVER", line=total, price=-104),
                 dict(game_id=gid, market="TOTAL", selection="UNDER", line=total, price=-104),
                 dict(game_id=gid, market=f"TT_{h}", selection="OVER", line=round(total / 2 - spread / 2 - 0.5, 1) + 0.0, price=-104),
                 dict(game_id=gid, market=f"TT_{h}", selection="UNDER", line=round(total / 2 - spread / 2 - 0.5, 1) + 0.0, price=-104),
                 dict(game_id=gid, market="1H_SPREAD", selection=h, line=-2.0, price=-104),
                 dict(game_id=gid, market="1H_SPREAD", selection=a, line=2.0, price=-104),
                 dict(game_id=gid, market="1H_TOTAL", selection="OVER", line=round(total * 0.49) + 0.5, price=-104),
                 dict(game_id=gid, market="1H_TOTAL", selection="UNDER", line=round(total * 0.49) + 0.5, price=-104),
                 dict(game_id=gid, market="1Q_TOTAL", selection="OVER", line=round(total * 0.245) + 0.5, price=-104),
                 dict(game_id=gid, market="1Q_TOTAL", selection="UNDER", line=round(total * 0.245) + 0.5, price=-104)]
    w("odds", odds)
    w("props", [dict(game_id="G1", player="Big D5", stat="PTS", line=26.5, over_price=-105, under_price=-105),
                dict(game_id="G1", player="Big D5", stat="PRA", line=48.5, over_price=-105, under_price=-105),
                dict(game_id="G1", player="Peyton Watson", stat="PTS", line=7.5, over_price=-105, under_price=-105),
                dict(game_id="G1", player="Guard L1", stat="AST", line=7.5, over_price=-105, under_price=-105),
                dict(game_id="G2", player="Wing B2", stat="3PM", line=3.5, over_price=-105, under_price=-105),
                dict(game_id="G2", player="Big M3", stat="REB", line=10.5, over_price=-105, under_price=-105)])
    print(f"wrote synthetic samples to {OUT}")


if __name__ == "__main__":
    main()
