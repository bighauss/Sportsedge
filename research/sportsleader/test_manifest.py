import hashlib
import json
import unittest
from research.sportsleader.manifest import select
from research.sportsleader.intake import ROOT

class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.entry = dict(league="cbb", dataset="games", season=2025,
                          url=ROOT+"cbb_games/2025.parquet", sha256="a"*64,
                          bytes=100, rows=2)
    def test_receipt(self):
        raw = json.dumps({"files":[self.entry]}).encode()
        receipt = select(raw, "cbb", "games", 2025)
        self.assertEqual(receipt["manifest_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt["entry"], self.entry)
    def test_fail_closed(self):
        for data in [[], [self.entry, self.entry], {"unknown":[]},
                     [dict(self.entry, url="https://example.com")]]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                select(json.dumps(data).encode(), "cbb", "games", 2025)
