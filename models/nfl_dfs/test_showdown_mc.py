import json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import showdown_mc as m

class T(unittest.TestCase):
    def test_scoring(self):
        self.assertAlmostEqual(m.dk_offense(py=300, ptd=2), 12 + 8 + 3)
        self.assertAlmostEqual(m.dk_offense(rec=8, rcy=100, rctd=1), 8 + 10 + 6 + 3)
        self.assertEqual(m.dk_dst(0, 0, 0, 0, 0), 10)
        self.assertEqual(m.dk_dst(24, 3, 1, 0, 0), 5)
        self.assertEqual(m.dk_dst(40, 0, 0, 0, 0), -4)

    def test_sim_and_lineups(self):
        here = os.path.dirname(os.path.abspath(__file__))
        cfg = json.load(open(os.path.join(here, "games", "PIT_CIN_2026-11-15.json")))
        sims, game = m.run(cfg, 400, seed=1)
        tot = sum(a + b for a, b in game) / len(game)
        self.assertTrue(35 < tot < 62, tot)
        sal = m.load_salaries(os.path.join(here, cfg["salary_file"]))
        pool = ["Joe Burrow", "Ja'Marr Chase", "Tee Higgins", "Jaylen Warren", "Aaron Rodgers",
                "DK Metcalf", "Mike Gesicki", "Bengals"]
        stats, cr, fr, n = m.optimize(sims, sal, pool, n_keep=50)
        for s in stats:
            self.assertLessEqual(s["salary"], 50000)
            self.assertNotIn(s["cpt"], s["flex"])
            self.assertEqual(len({sal[p]["team"] for p in s["flex"] + [s["cpt"]]}), 2)
        self.assertAlmostEqual(sum(cr.values()), 1.0, places=6)

if __name__ == "__main__":
    unittest.main()
