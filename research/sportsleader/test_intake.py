import unittest
from research.sportsleader.intake import validate_entry, ROOT

class IntakeContract(unittest.TestCase):
    def setUp(self):
        self.entry = dict(league="cbb", dataset="games", season=2025,
                          url=ROOT+"cbb_games/2025.parquet", sha256="a"*64,
                          bytes=100, rows=2)
    def test_valid(self):
        self.assertEqual(validate_entry(self.entry), self.entry["url"])
    def test_reject_invalid(self):
        for key, value in [("league","nba"), ("dataset","odds"),
                           ("season","../2025"), ("url","https://example.com"),
                           ("sha256","bad"), ("bytes",True), ("rows",0)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_entry(dict(self.entry, **{key:value}))

if __name__ == "__main__":
    unittest.main()
