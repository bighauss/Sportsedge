import csv, os, tempfile, unittest, random
from datetime import datetime, timedelta, timezone
import nfl_forecast_scorecard as sc

def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); rnd = random.Random(1)
        teams = ["T%d" % i for i in range(8)]; strength = {t: rnd.gauss(0, 6) for t in teams}
        t0 = datetime(2025, 9, 7, 17, tzinfo=timezone.utc)
        g, r, p = [], [], []
        for wk in range(1, 11):
            order = teams[:]; rnd.shuffle(order)
            for j in range(0, 8, 2):
                h, a = order[j], order[j + 1]; gid = "%d_%s_%s" % (wk, h, a)
                ko = t0 + timedelta(days=7 * (wk - 1))
                g.append([gid, 2025, wk, h, a, ko.isoformat(), (ko - timedelta(hours=2)).isoformat()])
                m = strength[h] - strength[a] + 2 + rnd.gauss(0, 13)
                hs = max(0, round(23 + m / 2)); as_ = max(0, round(23 - m / 2))
                if hs == as_: hs += 3
                fin = ko + timedelta(hours=3)
                r.append([gid, hs, as_, fin.isoformat(), (fin + timedelta(minutes=5)).isoformat()])
                pm = strength[h] - strength[a] + 2
                p.append([gid, round(pm, 2), 46, round(1 / (1 + 10 ** (-pm * 25 / 400)), 4)])
        self.gp, self.rp, self.pp = [os.path.join(self.d, n) for n in ("g.csv", "r.csv", "p.csv")]
        write(self.gp, ["game_id", "season", "week", "home_team", "away_team", "kickoff_utc", "forecast_asof_utc"], g)
        write(self.rp, ["game_id", "home_score", "away_score", "final_utc", "result_available_utc"], r)
        write(self.pp, ["game_id", "pred_margin", "pred_total", "p_home_win"], p)

    def test_runs_and_common_set(self):
        rep = sc.run(self.gp, self.rp, ["oracle=" + self.pp])
        self.assertEqual(rep["common_scored"], 40)
        self.assertFalse(rep["uses_odds"])
        self.assertLess(rep["models"]["oracle"]["brier"], rep["models"]["elo_baseline"]["brier"])

    def test_missing_rows_drop_from_all_models(self):
        rows = list(csv.reader(open(self.pp)))[:-5]
        write(self.pp, rows[0], rows[1:])
        rep = sc.run(self.gp, self.rp, ["oracle=" + self.pp])
        self.assertEqual(rep["common_scored"], 35)
        self.assertEqual(rep["models"]["oracle"]["missing_or_blocked"], 5)
        self.assertEqual(rep["models"]["elo_baseline"]["n_prob"], rep["models"]["oracle"]["n_prob"])

    def test_elo_no_lookahead(self):
        games = sc.read_csv(self.gp, ["game_id"]); res = sc.read_csv(self.rp, ["game_id"])
        a = sc.elo_baseline(games, res)
        first = [gid for gid in games if games[gid]["week"] == "1"]
        for gid in first: self.assertAlmostEqual(a[gid]["p_home_win"], 1 / (1 + 10 ** (-48 / 400)))
        # flipping a week-10 result must not change any week<=10 forecast
        late = [gid for gid in res if games[gid]["week"] == "10"][0]
        res[late]["home_score"], res[late]["away_score"] = res[late]["away_score"], res[late]["home_score"]
        b = sc.elo_baseline(games, res)
        self.assertEqual(a, b)

    def test_rejects_asof_after_kickoff(self):
        rows = list(csv.reader(open(self.gp))); rows[1][6] = rows[1][5].replace("17:00", "18:00")
        write(self.gp, rows[0], rows[1:])
        with self.assertRaises(ValueError): sc.run(self.gp, self.rp, [])

    def test_duplicate_ids_rejected(self):
        rows = list(csv.reader(open(self.pp))); rows.append(rows[1])
        write(self.pp, rows[0], rows[1:])
        with self.assertRaises(ValueError): sc.run(self.gp, self.rp, ["x=" + self.pp])

if __name__ == "__main__":
    unittest.main()
