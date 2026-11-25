"""Synthetic regression fixtures; not historical performance evidence."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "paired_holdout_audit", Path(__file__).with_name("paired_holdout_audit.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

HEADER = ("game_id,home_id,away_id,tip_utc,observed_final_utc,"
          "home_points,away_points,home_possessions,away_possessions,neutral\n")

def row(gid, day, observed, h="A", a="B", hp=75, ap=70):
    return (f"{gid},{h},{a},2026-11-{day:02d}T12:00:00Z,"
            f"2026-11-{observed:02d}T16:00:00Z,{hp},{ap},70,70,0\n")

def games(*rows):
    return m.load_games((HEADER+"".join(rows)).encode())

class ReplayTests(unittest.TestCase):
    def test_common_holdout_and_availability(self):
        g = games(row("1",1,1),row("2",2,2),row("3",3,3),
                  row("late",4,6,hp=200),row("test",5,5),
                  row("missing",6,6,a="C"),row("pending",7,9))
        rows, report = m.replay(g,m.stamp("2026-11-05T00:00:00Z"),
                                 m.stamp("2026-11-08T00:00:00Z"),3,10)
        self.assertEqual(report["training_games"],3)
        self.assertEqual(report["holdout_games"],3)
        self.assertEqual(report["dispositions"],{"SCORED":1,
            "MISSING_TRAINING_TEAM":1,"FINAL_NOT_AVAILABLE":1})
        for model in m.MODELS:
            self.assertEqual(report["metrics"][model]["margin"]["n"],1)
            self.assertIn(model+"_total_error",rows[0])
        self.assertAlmostEqual(rows[0]["raw_home"],75)
        self.assertAlmostEqual(rows[0]["raw_away"],70)

    def test_duplicate_game_fails(self):
        with self.assertRaisesRegex(ValueError,"duplicate"):
            games(row("1",1,1),row("1",2,2))

    def test_naive_clock_fails(self):
        with self.assertRaises(ValueError):
            m.stamp("2026-11-05T00:00:00")

    def test_invalid_possessions_fails(self):
        with self.assertRaises(ValueError):
            games(row("1",1,1).replace(",70,70,0",",0,70,0"))

    def test_nonfinal_score_fails(self):
        with self.assertRaises(ValueError):
            games(row("1",1,1,hp=70,ap=70))

if __name__=="__main__":
    unittest.main()
