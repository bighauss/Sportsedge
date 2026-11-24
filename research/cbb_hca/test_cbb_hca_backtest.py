import datetime as dt, json, os, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "models" / "cbb"))
import cbb_hca_backtest as B
import cbbd_paper_synthetic as S
import test_cbb_run_it as T

class Walk(unittest.TestCase):
    def test_ols(self):
        a, b = B.ols([0, 1, 2, 3], [3, 3.5, 4, 4.5]); self.assertAlmostEqual(a, 3); self.assertAlmostEqual(b, .5)

    def test_walk_and_report_on_synthetic(self):
        games, boxes = T.provider()
        finals = [g for g in games if g["status"] == "final"]
        for g in finals: g["neutralSite"] = bool(g["neutralSite"])
        lines = [{"gameId": g["id"], "lines": [{"spread": -3.0, "homeMoneyline": -150, "awayMoneyline": 130}]} for g in finals]
        days = sorted({B.R.parse_z(g["startDate"]).date() for g in finals})[-4:]
        rows = B.walk(S.ratings_body(), games, boxes, lines, S.SEASON, days)
        self.assertTrue(rows)
        md = B.report(rows)
        self.assertIn("RESEARCH ONLY", md); self.assertIn("C1 (intercept HCA)", md)
        # synthetic truth HCA is 3.0: the intercept estimate should be close to it
        self.assertLess(abs(rows[-1]["hca_c1"] - S.HCA_TRUE), 1.5)

class PITChallenger(unittest.TestCase):
    def row(self, i, x, *, neutral=False, delay=0):
        f = dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc) + dt.timedelta(days=i)
        z = lambda d: d.isoformat().replace("+00:00", "Z")
        return dict(event_id=str(i), freeze_utc=z(f), tipoff_utc=z(f+dt.timedelta(hours=3)),
                    final_observed_utc=z(f+dt.timedelta(hours=6, days=delay)), neutral=neutral,
                    neutral_margin=x, baseline_margin=x+(0 if neutral else 8),
                    actual_margin=1.4*x+(0 if neutral else 3),
                    prediction_sha256="a"*64, final_sha256="b"*64)

    def test_recovers_intercept_and_slope_on_synthetic_truth(self):
        from research.cbb_hca.pit_challenger import audit
        rows = [self.row(i, x) for i,x in enumerate((-10, 0, 10, 20, -20))]
        result = audit(rows, min_train=3)
        self.assertEqual(result["compared_rows"], 2)
        self.assertAlmostEqual(result["rows"][0]["hca"], 3)
        self.assertAlmostEqual(result["rows"][0]["slope"], .4)
        self.assertAlmostEqual(result["paired_mae"]["intercept_slope"], 0)
        self.assertEqual(result["input_rows"], len(result["holds"])+result["compared_rows"])

    def test_late_final_not_available_for_fit(self):
        from research.cbb_hca.pit_challenger import audit
        rows = [self.row(0,-10,delay=8), self.row(1,0), self.row(2,10), self.row(3,20)]
        result = audit(rows, min_train=3)
        self.assertEqual(result["compared_rows"], 0)

    def test_duplicate_events_quarantined(self):
        from research.cbb_hca.pit_challenger import audit
        a = self.row(0,0)
        result = audit([a,dict(a)], min_train=3)
        self.assertEqual(len(result["holds"]), 2)
        self.assertTrue(all(x["reason"]=="DUPLICATE_OR_INVALID_EVENT" for x in result["holds"]))

    def test_neutral_target_does_not_receive_hca(self):
        from research.cbb_hca.pit_challenger import audit
        rows = [self.row(0,-10), self.row(1,0), self.row(2,10), self.row(3,20,neutral=True)]
        result = audit(rows, min_train=3)
        self.assertAlmostEqual(result["rows"][0]["intercept_only"],20)
        self.assertAlmostEqual(result["rows"][0]["intercept_slope"],28)

    def test_constant_predictors_are_unidentified(self):
        from research.cbb_hca.pit_challenger import audit
        result = audit([self.row(i, 0) for i in range(4)], min_train=3)
        self.assertEqual(result["compared_rows"],0)
        self.assertIn("UNIDENTIFIED_MARGIN_SLOPE", [h["reason"] for h in result["holds"]])

if __name__ == "__main__":
    unittest.main()
