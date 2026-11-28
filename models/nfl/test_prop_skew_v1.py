"""prop-skew-v1: fitted table integrity, distribution shape, opt-in ledger integration."""
import json, os, sys, unittest
from statistics import NormalDist
sys.path.insert(0, os.path.dirname(__file__))
import prop_skew_v1 as S  # noqa: E402
import runit_ledger as L  # noqa: E402
from test_runit_ledger import ABBR, GAME, PROJ, prop  # noqa: E402

STATS = ("pass_yds", "rush_yds", "rec_yds", "receptions")


class Table(unittest.TestCase):
    def test_fitted_on_2018_2022_only(self):
        t = S.table()
        self.assertEqual(t["train_seasons"], [2018, 2019, 2020, 2021, 2022])
        self.assertEqual(t["version"], S.VERSION)
        self.assertEqual(set(t["stats"]), set(STATS))

    def test_bins_contiguous_sorted_and_populated(self):
        for stat in STATS:
            bins = S.table()["stats"][stat]["bins"]
            self.assertEqual(bins[0]["lo"], 0.0)
            for a, b in zip(bins, bins[1:]):
                self.assertEqual(a["hi"], b["lo"])
            for b in bins:
                self.assertGreaterEqual(b["n"], 150)
                self.assertEqual(b["q"], sorted(b["q"]))

    def test_probabilities_bounded_and_monotone(self):
        for stat in STATS:
            for m in (3, 20, 60, 250):
                ps = [S.p_ge(stat, m, k) for k in (1, m * .5, m, m * 1.5, m * 3)]
                self.assertTrue(all(0 <= p <= 1 for p in ps))
                self.assertEqual(ps, sorted(ps, reverse=True))

    def test_right_skew_median_below_mean_for_rush_and_rec(self):
        for stat, m in (("rush_yds", 55.0), ("rec_yds", 45.0)):
            self.assertLess(S.p_ge(stat, m, m + 0.5), 0.5)
            normal = 1 - NormalDist(m, 0.5 * m).cdf(m)
            self.assertLess(S.p_ge(stat, m, m + 0.5), normal)

    def test_rejects_unfitted_stat_and_bad_mean(self):
        with self.assertRaises(KeyError):
            S.p_ge("pass_tds", 1.5, 2)
        for m in (0, -3, None, float("nan"), "40"):
            with self.assertRaises(ValueError):
                S.p_ge("rec_yds", m, 40)


class LedgerOptIn(unittest.TestCase):
    PROPS = [prop("QB", 240, -105), prop("WR", 60, -110, file="8.03.35"),
             prop("TD", 2, 120, file="8.03.53"), prop("RR", 80, -110, file="8.03.59")]

    def rows(self, **kw):
        rows, _ = L.build_ledger([GAME], self.PROPS, PROJ, ABBR, **kw)
        return {r["selection"].split()[0]: r for r in rows if r["kind"] == "prop"}

    def test_default_is_frozen_v3(self):
        a, b = self.rows(), self.rows(prop_dist="v3_normal")
        for k in a:
            self.assertEqual(a[k]["model_p"], b[k]["model_p"])
            self.assertEqual(a[k]["prop_dist"], "v3_normal")

    def test_skew_option_changes_fitted_stats_only(self):
        v3, sk = self.rows(), self.rows(prop_dist="skew_v1")
        for k in ("QB", "WR"):
            self.assertEqual(sk[k]["prop_dist"], S.VERSION)
            self.assertNotAlmostEqual(sk[k]["model_p"], v3[k]["model_p"], places=4)
        for k in ("TD", "RR"):
            self.assertEqual(sk[k]["prop_dist"], "v3_normal")
            self.assertEqual(sk[k]["model_p"], v3[k]["model_p"])

    def test_unknown_dist_rejected(self):
        with self.assertRaises(ValueError):
            self.rows(prop_dist="gaussian_guess")

    def test_no_stars_emitted(self):
        for r in self.rows(prop_dist="skew_v1").values():
            self.assertNotIn("stars", r)
            self.assertNotIn("flames", r)


class HoldoutReport(unittest.TestCase):
    def test_committed_validation_report_shape(self):
        p = os.path.join(os.path.dirname(__file__), "..", "..", "research", "prop_variance",
                         "nfl_prop_skew_v1_validation.json")
        rep = json.load(open(p))
        self.assertEqual(rep["holdout"], [2023, 2024, 2025])
        for stat in STATS:
            m = rep["stats"][stat]["methods"]
            self.assertLess(m["skew_v1"]["logloss"], m["v3_normal"]["logloss"])
            self.assertLess(m["skew_v1"]["brier"], m["v3_normal"]["brier"])


if __name__ == "__main__":
    unittest.main()
