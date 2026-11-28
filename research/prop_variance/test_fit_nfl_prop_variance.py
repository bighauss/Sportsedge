"""Synthetic checks: strict prior-only forecasts, role eligibility, duplicate refusal."""
import csv, gzip, io, math, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_nfl_prop_variance as V

COLS = ["player_id", "season", "week", "season_type", "passing_yards", "attempts",
        "rushing_yards", "carries", "receiving_yards", "targets", "receptions"]


def write(rows):
    d = tempfile.mkdtemp(); p = os.path.join(d, "x.csv.gz")
    with gzip.open(p, "wt", newline="") as f:
        w = csv.DictWriter(f, COLS); w.writeheader()
        for r in rows:
            w.writerow({**{c: 0 for c in COLS}, **r})
    return p


def wr(week, yds, tgt=6, pid="P1", season=2020, st="REG"):
    return {"player_id": pid, "season": season, "week": week, "season_type": st,
            "receiving_yards": yds, "targets": tgt, "receptions": 3}


class T(unittest.TestCase):
    def rec(self, rows):
        return [(f, y) for s, st, f, y in V.forecasts(V.load([write(rows)])) if st == "rec_yds"]

    def test_forecast_uses_only_prior_games(self):
        out = self.rec([wr(1, 40), wr(2, 60), wr(3, 50), wr(4, 999)])
        self.assertEqual(len(out), 1)
        f, y = out[0]
        ew = 40; ew = .35 * 60 + .65 * ew; ew = .35 * 50 + .65 * ew
        self.assertAlmostEqual(f, ew); self.assertEqual(y, 999)

    def test_future_rows_do_not_change_past_forecast(self):
        a = self.rec([wr(1, 40), wr(2, 60), wr(3, 50), wr(4, 70)])
        b = self.rec([wr(1, 40), wr(2, 60), wr(3, 50), wr(4, 70), wr(5, 500), wr(6, 0)])
        self.assertEqual(a[0], b[0])

    def test_input_order_irrelevant(self):
        rows = [wr(1, 40), wr(2, 60), wr(3, 50), wr(4, 70), wr(5, 20)]
        self.assertEqual(self.rec(rows), self.rec(list(reversed(rows))))

    def test_ineligible_role_games_do_not_update_or_score(self):
        out = self.rec([wr(1, 40), wr(2, 60), wr(3, 50), wr(4, 5, tgt=1), wr(5, 70)])
        self.assertEqual([y for _, y in out], [70])

    def test_duplicate_player_week_refused(self):
        self.assertEqual(self.rec([wr(1, 40), wr(1, 41), wr(2, 60), wr(3, 50), wr(4, 70)]), [])

    def test_preseason_excluded(self):
        self.assertEqual(self.rec([wr(1, 40, st="PRE"), wr(2, 60), wr(3, 50), wr(4, 70)]), [])

    def test_power_fit_recovers_known_scale(self):
        import random; random.seed(1)
        train = [(f, random.gauss(f, 0.5 * f)) for f in [random.uniform(20, 80) for _ in range(20000)]]
        a, b = V.fit_power(train)
        self.assertAlmostEqual(b, 1.0, delta=0.05)
        self.assertAlmostEqual(a * 50 ** b, 25, delta=2.5)


if __name__ == "__main__":
    unittest.main()
