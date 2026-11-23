"""Synthetic tests: python3 -m unittest discover -s ledger/nfl/tests"""
import csv, json, os, sys, tempfile, unittest
from datetime import datetime, timezone

NFL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, NFL)
import freeze, settle, scorecard  # noqa: E402

FIELDS = ["game", "market", "pick", "player", "line", "price", "model_p", "market_p",
          "blend_p", "ev", "model_ev", "held", "status"]
PICKS = [
    ["CIN@WAS", "spread", "CIN", "", "-2.5", "-110", ".55", ".5", ".53", ".03", ".05", "0", "play"],
    ["CIN@WAS", "spread", "WAS", "", "+3", "-110", ".5", ".5", ".5", "-.01", "0", "1", "held"],
    ["CIN@WAS", "total", "over", "", "47.5", "-105", ".56", ".5", ".53", ".06", ".09", "0", "play"],
    ["CIN@WAS", "total", "under", "", "40", "-110", ".5", ".5", ".5", ".0", ".0", "0", "play"],
    ["CIN@WAS", "ml", "WAS", "", "", "+130", ".46", ".42", ".44", ".012", ".05", "0", "play"],
    ["CIN@WAS", "1H_spread", "CIN", "", "-0.5", "-120", ".55", ".52", ".53", ".11", ".12", "0", "play"],
    ["CIN@WAS", "1Q_total", "over", "", "9.5", "-110", ".5", ".5", ".5", ".01", ".01", "0", "play"],
    ["CIN@WAS", "prop_pass_yds", "over", "Joe Burrow", "265.5", "-115", ".58", ".52", ".55", ".04", ".07", "0", "play"],
    ["CIN@WAS", "prop_anytime_td", "yes", "Ja'Marr Chase", "", "+120", ".5", ".45", ".47", ".03", ".1", "1", "held"],
    ["CIN@WAS", "prop_rush_yds", "under", "Nobody", "50.5", "-110", ".5", ".5", ".5", ".01", ".01", "0", "play"],
]
FINALS = {"away": "CIN", "home": "WAS", "away_score": 27, "home_score": 24,
          "periods": {"1H": [14, 10]}}


def _w(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows(rows)


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.runs, self.sdir = os.path.join(self.t, "runs"), os.path.join(self.t, "settle")
        self.board = os.path.join(self.t, "board.csv")
        _w(self.board, [["spread", "CIN", "-2.5", "-110"]], ["market", "side", "line", "price"])
        self.proj = os.path.join(self.t, "p.json")
        json.dump({"proj_margin": -1.0, "proj_total": 49.0, "market_margin": -2.5,
                   "market_total": 47.5}, open(self.proj, "w"))
        self.picks = os.path.join(self.t, "picks.csv")
        _w(self.picks, PICKS, FIELDS)
        self.stats = os.path.join(self.t, "stats.csv")
        _w(self.stats, [["Joe Burrow", "pass_yds", "280"], ["Ja'Marr Chase", "anytime_td", "1"]],
           ["player", "stat", "value"])
        self.now = datetime(2026, 11, 23, 22, 0, tzinfo=timezone.utc)

    def _freeze(self):
        return freeze.freeze("CIN@WAS", self.board, self.proj,
                             {"challenger": self.picks, "baseline": self.picks},
                             {"engine": "abc123"}, "2026-11-24T01:15:00Z", runs_dir=self.runs, now=self.now)

    def test_freeze_layout_and_no_overwrite(self):
        rd = self._freeze()
        m = json.load(open(os.path.join(rd, "manifest.json")))
        self.assertTrue(m["pregame"])
        self.assertEqual(m["commits"]["engine"], "abc123")
        for rel in ("inputs/board.csv", "projection/frozen.json", "challenger/picks_nfl.csv",
                    "baseline/picks_nfl.csv"):
            self.assertEqual(m["files"][rel], freeze.sha256_file(os.path.join(rd, rel)))
        self.assertEqual(freeze.verify(rd), [])
        with self.assertRaises(FileExistsError):
            self._freeze()

    def test_settle_grades_and_leaves_run_untouched(self):
        rd = self._freeze()
        before = {r: freeze.sha256_file(os.path.join(rd, r)) for r in os.listdir(rd) if r.endswith(".json")}
        path, rec = settle.settle(rd, FINALS, "synthetic", self.stats, self.sdir, now=self.now)
        self.assertEqual(before, {r: freeze.sha256_file(os.path.join(rd, r)) for r in before})
        self.assertTrue(rec["run_integrity_ok"])
        g = [x for x in rec["graded"] if x["pick_set"] == "challenger"]
        res = [x["result"] for x in g]
        # CIN-2.5 W(27-24), WAS+3 P, o47.5 W(51), u40 L, WAS ML L, 1H CIN-0.5 W, 1Q missing NG,
        # Burrow o265.5 W, Chase TD yes W, Nobody NG
        self.assertEqual(res, ["W", "P", "W", "L", "L", "W", "NG", "W", "W", "NG"])
        self.assertAlmostEqual(g[0]["units"], 100 / 110, places=4)
        self.assertTrue(g[1]["held"] and g[8]["held"])
        self.assertAlmostEqual(g[8]["units"], 1.2)
        settle.settle(rd, FINALS, "second source", self.stats, self.sdir, now=self.now)
        self.assertEqual(len(json.load(open(path))), 2)  # appended, not overwritten

    def test_scorecard(self):
        rd = self._freeze()
        settle.settle(rd, FINALS, "synthetic", self.stats, self.sdir, now=self.now)
        md = scorecard.build(scorecard.load_week("2026-11-19", "2026-11-25", self.runs, self.sdir),
                             pick_set="challenger")
        self.assertIn("Margin: model 2.00 vs market 0.50", md)   # actual margin -3
        self.assertIn("Total: model 2.00 vs market 3.50", md)    # actual total 51
        self.assertIn("- Held: 1-0-1", md)
        self.assertIn("- prop:pass_yds: 1-0-0", md)
        self.assertIn("- periods: 1-0-0", md)
        self.assertIn("Not gradable (missing score/stat): 2", md)
        self.assertIn("10%+", md)
        self.assertNotIn("CLV", md)
        self.assertEqual(scorecard.load_week("2026-12-01", "2026-12-07", self.runs, self.sdir), [])


if __name__ == "__main__":
    unittest.main()
