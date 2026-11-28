"""Synthetic checks for the 1H join validation and prior-only dedicated forecasts."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_cbb_first_half as H


def g(gid, date, home, away, hp, ap, neutral=False):
    return {"gid": gid, "date": date, "home": home, "away": away, "neutral": neutral,
            "h": {"PTS": hp}, "a": {"PTS": ap}}


class T(unittest.TestCase):
    def test_join_accepts_matching_and_flipped_orientation(self):
        games = [g("1", "d", "A", "B", 70, 60), g("2", "d", "C", "D", 80, 75)]
        halves = {"1": dict(h1_home=33, h1_away=28, final_home=70, final_away=60),
                  "2": dict(h1_home=40, h1_away=35, final_home=75, final_away=80)}  # pbp home/away flipped
        out, st = H.join(games, halves)
        self.assertEqual(st, {"no_pbp": 0, "final_mismatch": 0, "ok": 2})
        self.assertEqual((out[1]["h1h"], out[1]["h1a"]), (35, 40))

    def test_join_rejects_mismatch_missing_and_impossible(self):
        games = [g("1", "d", "A", "B", 70, 60), g("2", "d", "A", "B", 70, 60), g("3", "d", "A", "B", 70, 60)]
        halves = {"1": dict(h1_home=33, h1_away=28, final_home=71, final_away=60),
                  "3": dict(h1_home=75, h1_away=28, final_home=70, final_away=60)}
        out, st = H.join(games, halves)
        self.assertEqual(out, [])
        self.assertEqual(st, {"no_pbp": 1, "final_mismatch": 2, "ok": 0})

    def test_dedicated_forecast_uses_prior_games_only(self):
        seq = []
        for i in range(6):
            x = g(str(i), f"2023-12-{i + 1:02d}", "A", "B", 0, 0); x.update(h1h=30 + i, h1a=25); seq.append(x)
        base = H.dedicated(seq)
        future = seq + [dict(seq[0], gid="99", date="2023-12-31", h1h=99, h1a=1)]
        self.assertEqual(H.dedicated(future)[:len(base)], base)
        first_game, fh, fa = base[0]
        self.assertEqual(first_game["gid"], str(H.MIN_PRIOR))
        self.assertLess(fh, 30 + H.MIN_PRIOR)  # cannot see its own 1H score


if __name__ == "__main__":
    unittest.main()
