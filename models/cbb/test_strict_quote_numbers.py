import unittest
from models.cbb.strict_quote_numbers import int_price, number

class StrictQuoteNumbers(unittest.TestCase):
    def test_bad_prices(self):
        for s in ("1+10", "110.0", "1e2", "nan", "inf", "-inf", "99", "110.5", "9"*400, "9007199254740993"):
            with self.subTest(s=s):
                self.assertEqual(int_price(s), "BAD")
    def test_bad_lines(self):
        for s in ("nan", "inf", "-inf", "4+4", "1e2", "9"*400):
            with self.subTest(s=s):
                self.assertEqual(number(s), "BAD")
    def test_valid_and_missing(self):
        for s,p in (("+110",110),("-110",-110),("100",100),(" -125 ",-125)):
            self.assertEqual(int_price(s),p)
        for s,x in (("44.5",44.5),("-2.5",-2.5),("0",0),(".5",.5)):
            self.assertEqual(number(s),x)
        for s in ("",None," "):
            self.assertIsNone(number(s))
            self.assertIsNone(int_price(s))
