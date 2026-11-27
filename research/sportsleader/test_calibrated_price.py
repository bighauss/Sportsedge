import unittest
from research.sportsleader.calibrated_price import calibrated_price

class CalibrationTests(unittest.TestCase):
    def records(self):
        return [dict(game_id=str(i),season=2024,train_end_season=2023,
                     home_residual=0,away_residual=0) for i in range(100)]
    def run_price(self,rows):
        return calibrated_price(70,60,rows,2025,"total",130,"over",2)
    def test_future_excluded(self):
        rows=self.records()
        rows.append(dict(game_id="future",season=2025,train_end_season=2024,
                         home_residual=100,away_residual=100))
        r=self.run_price(rows)
        self.assertEqual(r["n"],100)
        self.assertEqual(r["push"],1)
    def test_leakage(self):
        rows=self.records()
        rows[0]["train_end_season"]=2024
        with self.assertRaises(ValueError):
            self.run_price(rows)
    def test_duplicate(self):
        rows=self.records()
        rows.append(rows[0])
        with self.assertRaises(ValueError):
            self.run_price(rows)
    def test_small_sample(self):
        with self.assertRaises(ValueError):
            self.run_price(self.records()[:-1])
