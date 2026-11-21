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

if __name__ == "__main__":
    unittest.main()
