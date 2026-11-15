"""End-to-end test: python3 test_sportsedge_mlb_model.py  (stdlib unittest)."""
import os, csv, math, tempfile, unittest, shutil
import sportsedge_mlb_model as m
HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "sample_inputs")

class T(unittest.TestCase):
    def test_nb_pmf(self):
        pm = m.nb_pmf(4.5)
        mean = sum(k*p for k,p in enumerate(pm)); var = sum((k-mean)**2*p for k,p in enumerate(pm))
        self.assertAlmostEqual(sum(pm), 1, 6); self.assertAlmostEqual(mean, 4.5, 1)
        self.assertAlmostEqual(var/mean, 1.6, 1)
    def test_odds(self):
        self.assertAlmostEqual(m.american_to_decimal(-110), 1.9091, 3)
        a, b = m.no_vig(m.implied(-110), m.implied(-110)); self.assertAlmostEqual(a, .5)
        r = m.ev_row(0.6, 100, 0.5); self.assertAlmostEqual(r["ev_raw"], 0.2); self.assertAlmostEqual(r["p_blend"], 0.53)
    def test_regress(self):
        self.assertAlmostEqual(m.regress(5.0, 60, 4.0), 4.5)
    def test_filter(self):
        self.assertTrue(m.contradicts("under", 8.5, 9.2)); self.assertTrue(m.contradicts("over", 8.5, 8.0))
        self.assertFalse(m.contradicts("over", 8.5, 9.2))
    def test_end_to_end(self):
        out = tempfile.mkdtemp()
        try:
            rows, md = m.run_card(m.load_inputs(SAMPLE), out_dir=out)
            self.assertTrue(rows, "card should contain plays")
            evs = [r["ev_blend"] for r in rows]; self.assertEqual(evs, sorted(evs, reverse=True))
            for r in rows:
                self.assertTrue(0 < r["model_p"] < 1); self.assertIn(r["stars"], range(1, 6))
                if r["projection"] is not None and r["market"] not in ("ML","RL","F5_ML","NRFI"):
                    self.assertFalse(m.contradicts(r["selection"], r["line"], r["projection"]))
            inp = m.load_inputs(SAMPLE)
            for g in inp["games"]:
                pr = m.project_game(inp, g)
                f, pv, ex = m.price_game(pr, g)
                pa, ph = f("ML","away",None)[0], f("ML","home",None)[0]
                self.assertAlmostEqual(pa+ph, 1, 6)
                self.assertTrue(0.4 < ex["nrfi"] < 0.7, ex["nrfi"])
                self.assertTrue(6 < pv["TOTAL"] < 13)
            self.assertTrue(os.path.exists(os.path.join(out, "mlb_card.csv")))
            with open(os.path.join(out, "mlb_card.csv")) as fh:
                self.assertEqual(len(list(csv.reader(fh))) - 1, len(rows))
            print("\n" + md)
        finally:
            shutil.rmtree(out)
    def test_missing_lineup_falls_back(self):
        inp = m.load_inputs(SAMPLE); inp["lineups"] = []
        rows, _ = m.run_card(inp, out_dir=tempfile.mkdtemp()); self.assertIsInstance(rows, list)

if __name__ == "__main__":
    unittest.main(verbosity=2)
