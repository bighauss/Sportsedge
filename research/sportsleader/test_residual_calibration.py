import unittest
from research.sportsleader.residual_calibration import price

class ResidualTests(unittest.TestCase):
    def test_push_and_ev(self):
        r=price(70,60,[(0,0)]*50+[(1,0)]*30+[(-1,0)]*20,"margin",10,"over",2)
        self.assertAlmostEqual(r["win"],.3)
        self.assertAlmostEqual(r["loss"],.2)
        self.assertAlmostEqual(r["push"],.5)
        self.assertAlmostEqual(r["ev"],.1)
    def test_pairing(self):
        r=price(70,60,[(5,-5),(-5,5)]*50,"total",130,"over",2)
        self.assertEqual(r["push"],1)
    def test_team_total(self):
        r=price(70,60,[(0,0)]*100,"away_total",60.5,"under",1.9)
        self.assertAlmostEqual(r["ev"],.9)
    def test_reject(self):
        for residuals in ([(0,0)]*99,[(float("nan"),0)]*100):
            with self.assertRaises(ValueError):
                price(70,60,residuals,"total",130,"over",2)
        with self.assertRaises(ValueError):
            price(70,60,[(0,0)]*100,"total",130,"over",1)
