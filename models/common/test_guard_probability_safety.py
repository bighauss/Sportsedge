"""Regression tests for the shared model-vs-market admission guard."""
import math
import unittest
from guard import is_input_gap

class GuardTests(unittest.TestCase):
    def test_valid_near_market_is_not_a_gap(self):
        self.assertFalse(is_input_gap(.51, .50))
    def test_large_disagreement_is_gap(self):
        self.assertTrue(is_input_gap(.70, .50))
    def test_nonfinite_fail_closed(self):
        for x in (math.nan, math.inf, -math.inf):
            with self.subTest(value=x):
                self.assertTrue(is_input_gap(x, .5))
                self.assertTrue(is_input_gap(.5, x))
    def test_missing_and_unparseable_fail_closed(self):
        for x in (None, "", "bad", object()):
            with self.subTest(value=repr(x)):
                self.assertTrue(is_input_gap(x, .5))
                self.assertTrue(is_input_gap(.5, x))
    def test_probability_bounds(self):
        for model,market in ((-0.1,.5),(1.1,.5),(.5,0),(.5,1),(.5,-.1),(.5,1.1)):
            with self.subTest(model=model,market=market):
                self.assertTrue(is_input_gap(model,market))
    def test_numeric_strings(self):
        self.assertFalse(is_input_gap("0.51","0.50"))

if __name__=="__main__":
    unittest.main()
