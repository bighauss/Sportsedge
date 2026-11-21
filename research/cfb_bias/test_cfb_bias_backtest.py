import json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfb_bias_backtest as B

ROWS = [{"week": 5, "game": f"A{i} @ H{i}", "proj_total": 60.0 + i % 3, "proj_margin": 3.0, "pts_h": 31, "pts_a": 29,
         "mkt_total": 52.5, "mkt_spread": -3.0, "act_h": 24 + i % 7, "act_a": 21 + i % 5} for i in range(40)]

class T(unittest.TestCase):
    def test_bias_and_recentre(self):
        md, js = B.report(ROWS)
        self.assertGreater(js["frozen"]["bias_model_total_vs_actual"], 5)
        self.assertAlmostEqual(js["recentred"]["bias_model_total_vs_actual"], 0, places=6)
        self.assertEqual(js["frozen"]["model_says_over_rate"], 1.0)
        self.assertIn("RESEARCH ONLY", md)

    def test_cli_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "r.json"); json.dump(ROWS, open(f, "w"))
            self.assertEqual(B.main(["--fixture", f, "--out", d]), 0)
            self.assertTrue((Path(d) / "bias.json").exists())

if __name__ == "__main__":
    unittest.main()
