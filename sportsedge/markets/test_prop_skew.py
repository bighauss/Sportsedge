"""Adversarial checks for sport-specific skew tables (CFB, CBB)."""
import json, math, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from sportsedge.markets import prop_skew as PS

TABLES = {"CFB": os.path.join(ROOT, "models", "cfb", "prop_skew_cfb_v1_table.json"),
          "CBB": os.path.join(ROOT, "models", "cbb", "prop_skew_cbb_v1_table.json")}
VALID = {"CFB": os.path.join(ROOT, "research", "prop_variance", "cfb_prop_skew_v1_validation.json"),
         "CBB": os.path.join(ROOT, "research", "prop_variance", "cbb_prop_skew_v1_validation.json")}


class SkewTables(unittest.TestCase):
    def each(self):
        for sport, path in TABLES.items():
            tab = PS.load(path)
            for stat, st in tab["stats"].items():
                yield sport, tab, stat, st

    def test_probabilities_sum_to_one_and_push_only_on_integers(self):
        for sport, tab, stat, st in self.each():
            for mean in (st["min_mean"], st["min_mean"] * 1.7, st["bins"][-1]["lo"] * 1.3):
                for line in [x / 2 for x in range(1, int(mean * 6))]:
                    with self.subTest(sport=sport, stat=stat, mean=mean, line=line):
                        po, pp, pu = PS.three_way(tab, stat, mean, line)
                        self.assertAlmostEqual(po + pp + pu, 1.0, places=12)
                        self.assertTrue(all(0 <= p <= 1 for p in (po, pp, pu)))
                        if float(line).is_integer():
                            self.assertGreaterEqual(pp, 0.0)
                        else:
                            self.assertEqual(pp, 0.0)

    def test_integer_lines_have_positive_push_near_mean(self):
        for sport, tab, stat, st in self.each():
            mean = st["bins"][len(st["bins"]) // 2]["lo"] * 1.05
            self.assertGreater(PS.three_way(tab, stat, mean, float(round(mean)))[1], 0.0, (sport, stat))

    def test_alternate_lines_monotonic(self):
        for sport, tab, stat, st in self.each():
            mean = st["bins"][len(st["bins"]) // 2]["lo"] * 1.05
            prev = 1.0
            for line in [x / 2 for x in range(1, int(mean * 8))]:
                po = PS.three_way(tab, stat, mean, line)[0]
                self.assertLessEqual(po, prev + 1e-12, (sport, stat, line)); prev = po

    def test_low_volume_refused_not_extrapolated(self):
        for sport, tab, stat, st in self.each():
            with self.assertRaisesRegex(PS.SkewError, "LOW_VOLUME_FORECAST"):
                PS.three_way(tab, stat, st["min_mean"] * 0.99, 0.5)

    def test_bad_inputs_refused(self):
        tab = PS.load(TABLES["CBB"])
        for mean, line in ((float("nan"), 10.5), (-3, 10.5), (True, 10.5), (12, 10.25), (12, float("inf"))):
            with self.assertRaises(PS.SkewError):
                PS.three_way(tab, "pts", mean, line)
        with self.assertRaisesRegex(PS.SkewError, "NOT_FITTED"):
            PS.three_way(tab, "pass_yds", 200, 199.5)

    def test_tables_are_sport_specific_and_train_only(self):
        cfb, cbb = PS.load(TABLES["CFB"]), PS.load(TABLES["CBB"])
        self.assertEqual((cfb["sport"], cbb["sport"]), ("CFB", "CBB"))
        self.assertEqual(set(cfb["stats"]), {"pass_yds", "rush_yds", "rec_yds", "receptions"})
        self.assertEqual(set(cbb["stats"]), {"pts", "reb", "ast", "tpm"})
        self.assertEqual(cfb["train_seasons"], "2014-2021")
        self.assertEqual(cbb["train_seasons"], "2021-22,2022-23")
        for sport in ("CFB", "CBB"):
            rep = json.load(open(VALID[sport]))
            self.assertEqual(rep["bias_tuning"], "NONE (reported only)")
            self.assertNotEqual(rep["train"], rep["holdout"])

    def test_holdout_bias_is_reported_for_every_offset(self):
        for sport in ("CFB", "CBB"):
            rep = json.load(open(VALID[sport]))
            for stat, d in rep["stats"].items():
                self.assertEqual(len(d["by_line"]), 10)
                for v in d["by_line"].values():
                    self.assertIn("signed_over_bias", v["skew"])
                    self.assertIn("signed_over_bias", v["pinned_normal"])


if __name__ == "__main__":
    unittest.main()
