import unittest
from research.sportsleader.player_probability import evaluate
class ProbabilityTests(unittest.TestCase):
    def test_prior_day_only(self):
        rows=[dict(date="2025-01-01",stat="yards",prediction=0,actual=-2),
              dict(date="2025-01-02",stat="yards",prediction=0,actual=2),
              dict(date="2025-01-02",stat="yards",prediction=0,actual=3)]
        r=evaluate(rows,min_history=1)["yards"]
        self.assertEqual(r["n"],2)
        self.assertAlmostEqual(r["brier"],4/9)
    def test_empty(self):
        self.assertEqual(evaluate([]),{})
