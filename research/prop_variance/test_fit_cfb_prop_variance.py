"""Synthetic checks: PBP aggregation, de-duplication, prior-only forecasts, eligibility."""
import csv, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_cfb_prop_variance as V

COLS = ["game_id", "season", "week", "play_id"] + [f"{r}_{k}" for r in (
    "completion", "incompletion", "interception_thrown", "rush", "reception", "target")
    for k in ("player_id",)] + ["completion_yds", "rush_yds", "reception_yds"]


def csvfile(rows):
    p = os.path.join(tempfile.mkdtemp(), "player_stats_2020.csv")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, COLS); w.writeheader()
        for r in rows:
            w.writerow({**{c: "NA" for c in COLS}, **r})
    return p


def play(pid, week=1, gid="G1", **kw):
    return {"game_id": gid, "season": 2020, "week": week, "play_id": pid, **kw}


class Aggregate(unittest.TestCase):
    def test_pass_rush_rec_totals(self):
        g = V.aggregate(csvfile([
            play("1", completion_player_id="QB", completion_yds=12, reception_player_id="WR", reception_yds=12),
            play("2", incompletion_player_id="QB", target_player_id="WR"),
            play("3", interception_thrown_player_id="QB"),
            play("4", rush_player_id="RB", rush_yds=-3),
        ]))
        qb, wr, rb = g[(2020, 1, "G1", "QB")], g[(2020, 1, "G1", "WR")], g[(2020, 1, "G1", "RB")]
        self.assertEqual((qb["pass_yds"], qb["attempts"]), (12, 3))
        self.assertEqual((wr["rec_yds"], wr["receptions"], wr["targets"]), (12, 1, 2))
        self.assertEqual((rb["rush_yds"], rb["carries"]), (-3, 1))

    def test_duplicate_play_rows_counted_once(self):
        r = play("9", rush_player_id="RB", rush_yds=10)
        g = V.aggregate(csvfile([r, dict(r)]))
        self.assertEqual(g[(2020, 1, "G1", "RB")]["rush_yds"], 10)

    def test_missing_ids_skipped(self):
        g = V.aggregate(csvfile([play("1", rush_player_id="NA", rush_yds=50), {"season": "x"}]))
        self.assertEqual(dict(g), {})


def games(seq, stat="rush_yds", opp="carries", n_opp=8, player="RB"):
    return {(2020, w, f"G{w}", player): {stat: y, opp: n_opp} for w, y in seq}


class Forecast(unittest.TestCase):
    def rush(self, g):
        return [(f, y) for s, st, f, y in V.forecasts(g) if st == "rush_yds"]

    def test_prior_only(self):
        out = self.rush(games([(1, 40), (2, 60), (3, 50), (4, 999)]))
        ew = 40; ew = .35 * 60 + .65 * ew; ew = .35 * 50 + .65 * ew
        self.assertEqual(len(out), 1); self.assertAlmostEqual(out[0][0], ew); self.assertEqual(out[0][1], 999)

    def test_future_games_do_not_change_past_forecast(self):
        a = self.rush(games([(1, 40), (2, 60), (3, 50), (4, 70)]))
        b = self.rush(games([(1, 40), (2, 60), (3, 50), (4, 70), (5, 500)]))
        self.assertEqual(a[0], b[0])

    def test_ineligible_games_skipped(self):
        g = games([(1, 40), (2, 60), (3, 50), (5, 70)])
        g[(2020, 4, "G4", "RB")] = {"rush_yds": 2, "carries": 1}
        self.assertEqual([y for _, y in self.rush(g)], [70])

    def test_two_games_same_week_refused(self):
        g = games([(1, 40), (2, 60), (3, 50), (4, 70)])
        g[(2020, 4, "G4b", "RB")] = {"rush_yds": 30, "carries": 8}
        self.assertEqual(self.rush(g), [])

    def test_pinned_constants_are_cfb_not_refit(self):
        self.assertEqual(V.CFB_PINNED_FRAC, {"rush_yds": 0.45, "rec_yds": 0.50, "pass_yds": 0.28, "receptions": 0.40})


if __name__ == "__main__":
    unittest.main()
