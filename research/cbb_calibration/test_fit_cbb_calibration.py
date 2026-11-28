"""Synthetic no-leakage and join-integrity checks for fit_cbb_calibration."""
import csv, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_cbb_calibration as C

BOX = ["player_id", "player", "PTS", "REB", "AST", "3PTM", "FGA", "FTA", "TO", "PF", "STL", "BLK", "date"]


def tree(games, sched):
    root = tempfile.mkdtemp()
    for (season, team, gid), rows in games.items():
        d = os.path.join(root, season, "box_scores", team); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{gid}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, BOX); w.writeheader()
            for r in rows:
                w.writerow({**{c: 0 for c in BOX}, **r})
    for (season, team), rows in sched.items():
        d = os.path.join(root, season, "schedules"); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{team}_schedule.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, ["game_id", "date", "opponent", "location", "team_score", "opp_score"])
            w.writeheader(); w.writerows(rows)
    return root


def p(date, pts, pid="1"):
    return {"player_id": pid, "player": "A", "PTS": pts, "FGA": 5, "date": date}


class T(unittest.TestCase):
    def props(self, seq):
        g = {("2021-22", "X", str(i)): [p(d, v)] for i, (d, v) in enumerate(seq)}
        rows, _ = C.load_players(tree(g, {}), ["2021-22"])
        return [(f, y) for s, st, f, y in C.prop_forecasts(rows) if st == "pts"]

    def test_prop_forecast_prior_only(self):
        out = self.props([("2021-11-0%d" % i, v) for i, v in enumerate([10, 20, 30, 999], 1)])
        ew = 10; ew = .35 * 20 + .65 * ew; ew = .35 * 30 + .65 * ew
        self.assertEqual(len(out), 1); self.assertAlmostEqual(out[0][0], ew); self.assertEqual(out[0][1], 999)

    def test_future_games_do_not_change_past(self):
        a = self.props([("2021-11-01", 10), ("2021-11-02", 20), ("2021-11-03", 30), ("2021-11-04", 12)])
        b = self.props([("2021-11-01", 10), ("2021-11-02", 20), ("2021-11-03", 30), ("2021-11-04", 12),
                        ("2021-11-05", 90)])
        self.assertEqual(a[0], b[0])

    def test_dnp_rows_dropped_and_duplicates_counted(self):
        g = {("2021-22", "X", "1"): [p("2021-11-01", 10), p("2021-11-01", 10)],
             ("2021-22", "Y", "1"): [p("2021-11-01", 10)],
             ("2021-22", "X", "2"): [{"player_id": "2", "player": "B", "date": "2021-11-02"}]}
        rows, dup = C.load_players(tree(g, {}), ["2021-22"])
        self.assertEqual(len(rows), 1); self.assertEqual(dup, 2)

    def sched(self, a_row, b_row):
        root = tree({}, {("2021-22", "A"): [a_row], ("2021-22", "B"): [b_row]})
        return C.load_games(root, ["2021-22"])

    def test_game_join_home_away(self):
        g = self.sched({"game_id": "9", "date": "d", "opponent": "B", "location": "H", "team_score": 70, "opp_score": 60},
                       {"game_id": "9", "date": "d", "opponent": "A", "location": "A", "team_score": 60, "opp_score": 70})
        self.assertEqual((g[0]["home"], g[0]["hs"], g[0]["as"], g[0]["neutral"]), ("A", 70, 60, False))

    def test_game_join_refuses_inconsistent_scores(self):
        g = self.sched({"game_id": "9", "date": "d", "opponent": "B", "location": "H", "team_score": 70, "opp_score": 60},
                       {"game_id": "9", "date": "d", "opponent": "A", "location": "A", "team_score": 61, "opp_score": 70})
        self.assertEqual(g, [])

    def test_game_forecast_uses_prior_games_only(self):
        games = [{"season": 2021, "date": "2021-11-%02d" % i, "gid": str(i), "home": "A", "away": "B",
                  "neutral": True, "hs": 70 + i, "as": 60} for i in range(1, 6)]
        out = C.game_forecasts(games)
        self.assertEqual([g["gid"] for g in out], ["4", "5"])
        off = 71; off = .35 * 72 + .65 * off; off = .35 * 73 + .65 * off
        self.assertAlmostEqual(out[0]["fh"], off)  # 0.5*(A scored EWMA + B allowed EWMA); both equal A's scores
        self.assertAlmostEqual(out[0]["fa"], 60)


if __name__ == "__main__":
    unittest.main()
