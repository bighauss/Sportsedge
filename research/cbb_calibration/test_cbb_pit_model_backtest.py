"""Synthetic checks: prior-only forecasts, schema handling, pairing, rejection, pinned model untouched."""
import csv, hashlib, os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cbb_pit_model_backtest as B

OLD = ["player", "position", "MIN", "FGM", "FGA", "3PTM", "3PTA", "FTM", "FTA", "OREB", "DREB", "REB",
       "AST", "STL", "BLK", "TO", "PF", "PTS", "starter", "date", "opponent", "location"]
NEW = ["player_id", "player", "position", "MIN", "FGM", "FGA", "3PTM", "3PTA", "FTM", "FTA", "OREB", "DREB",
       "REB", "AST", "STL", "BLK", "TO", "PF", "PTS", "team", "opponent", "home", "starter", "date", "location"]


def line(pts, fga=60, fgm=26, tpm=7, tpa=22, fta=18, ftm=12, orb=9, drb=24, to=12):
    return dict(MIN=200, FGM=fgm, FGA=fga, **{"3PTM": tpm, "3PTA": tpa}, FTM=ftm, FTA=fta,
                OREB=orb, DREB=drb, REB=orb + drb, AST=12, STL=6, BLK=3, TO=to, PF=17, PTS=pts)


def write_game(root, season, gid, date, home, away, hp, ap, schema="old", neutral=False):
    for team, opp, pts, loc in ((home, away, hp, "N" if neutral else "H"), (away, home, ap, "N" if neutral else "A")):
        d = os.path.join(root, season, "box_scores", team.replace(" ", "_"))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{gid}.csv"), "w", newline="") as f:
            if schema == "old":
                w = csv.DictWriter(f, OLD); w.writeheader()
                w.writerow({"player": "TEAM", "position": "NA", "starter": "FALSE", "date": date,
                            "opponent": opp, "location": loc, **line(pts)})
            else:
                w = csv.DictWriter(f, NEW); w.writeheader()
                for k in range(5):  # five equal player rows summing to the team line
                    L = {c: v / 5 for c, v in line(pts).items()}
                    w.writerow({"player_id": k, "player": f"P{k}", "position": "G", "team": team, "opponent": opp,
                                "home": "TRUE" if loc == "H" else "FALSE", "starter": "TRUE", "date": date,
                                "location": loc, **L})


def slate(root, season, n=8, extra=()):
    teams = ["Alpha", "Bravo", "Charlie", "Delta"]
    k = 0
    for wk in range(n):
        for i in range(0, 4, 2):
            h, a = teams[(i + wk) % 4], teams[(i + 1 + wk) % 4]
            write_game(root, season, f"{season[:4]}{k:04d}", f"{season[:4]}-12-{wk + 1:02d}", h, a, 70 + wk, 65 + i)
            k += 1
    for g in extra:
        write_game(root, season, *g)


class T(unittest.TestCase):
    def test_pinned_model_unchanged(self):
        p = os.path.join(HERE, "..", "..", "models", "cbb", "sportsedge_cbb_model.py")
        data = open(p, "rb").read()
        self.assertEqual(hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(),
                         "8bbe83b7a17d184b3521094b40e00be66ba0f852")

    def test_future_games_do_not_change_past_forecasts(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            slate(a, "2021-22")
            slate(b, "2021-22", extra=[("20219998", "2021-12-30", "Alpha", "Bravo", 150, 20),
                                       ("20219999", "2021-12-31", "Charlie", "Delta", 30, 140)])
            fa, _ = B.run_season(B.load_box(a, "2021-22"), {})
            fb, _ = B.run_season(B.load_box(b, "2021-22"), {})
            self.assertTrue(fa)
            self.assertEqual(fa, fb[:len(fa)])

    def test_forecast_is_made_before_update(self):
        with tempfile.TemporaryDirectory() as a:
            slate(a, "2021-22")
            g = B.load_box(a, "2021-22")
            fc, _ = B.run_season(g, {})
            first = fc[0]
            prior = [x for x in g if (x["date"], x["gid"]) < (first["date"], first["gid"])]
            for team in (first["home"], first["away"]):
                self.assertGreaterEqual(sum(team in (x["home"], x["away"]) for x in prior), B.MIN_PRIOR)

    def test_old_and_new_schema_give_same_totals(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            write_game(a, "2023-24", "1", "2023-12-01", "Alpha", "Bravo", 75, 70, schema="old")
            write_game(b, "2023-24", "1", "2023-12-01", "Alpha", "Bravo", 75, 70, schema="new")
            ga, gb = B.load_box(a, "2023-24")[0], B.load_box(b, "2023-24")[0]
            for k in ("FGA", "PTS", "OREB", "TO", "FTA"):
                self.assertAlmostEqual(ga["h"][k], gb["h"][k])

    def test_home_from_location_and_neutral(self):
        with tempfile.TemporaryDirectory() as a:
            write_game(a, "2023-24", "1", "2023-12-01", "Zulu", "Alpha", 75, 70)
            write_game(a, "2023-24", "2", "2023-12-02", "Bravo", "Alpha", 75, 70, neutral=True)
            g = {x["gid"]: x for x in B.load_box(a, "2023-24")}
            self.assertEqual((g["1"]["home"], g["1"]["neutral"]), ("Zulu", False))
            self.assertTrue(g["2"]["neutral"])

    def test_single_sided_and_implausible_games_excluded(self):
        with tempfile.TemporaryDirectory() as a:
            write_game(a, "2023-24", "1", "2023-12-01", "Alpha", "Bravo", 75, 70)
            os.remove(os.path.join(a, "2023-24", "box_scores", "Bravo", "1.csv"))
            write_game(a, "2023-24", "2", "2023-12-02", "Alpha", "Bravo", 5, 70)
            B.REJECTED.clear()
            self.assertEqual(B.load_box(a, "2023-24"), [])
            self.assertEqual(B.REJECTED.get("2023-24"), 1)

    def test_summary_moments(self):
        m = B.moments([-2.0, 0.0, 2.0])
        self.assertEqual((m["mean"], m["sd"], m["mae"]), (0.0, 2.0, 1.333))


if __name__ == "__main__":
    unittest.main()
