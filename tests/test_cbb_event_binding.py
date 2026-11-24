import unittest
from research.cbb_event_binding import reconcile

class BindingTests(unittest.TestCase):
    def setUp(self):
        self.e = dict(dk_event_id="123", home="A", away="B", tipoff_ct="2026-11-24T09:00:00-06:00")
        self.g = dict(game_id="456", _home="A", _away="B", tipoff_utc="2026-11-24T15:00:00Z")

    def check(self, events, slate, expected):
        self.assertEqual([r["status"] for r in reconcile(events, slate)], expected)

    def test_exact(self):
        self.check([self.e], [self.g], ["MATCHED"])
        self.assertEqual(reconcile([self.e], [self.g])[0]["cbbd_game_id"], "456")

    def test_reversed(self):
        self.check([self.e], [dict(self.g, _home="B", _away="A")], ["BLOCKED"])

    def test_wrong_time(self):
        self.check([self.e], [dict(self.g, tipoff_utc="2026-11-24T16:00:00Z")], ["BLOCKED"])

    def test_naive_time(self):
        self.check([dict(self.e, tipoff_ct="2026-11-24T09:00:00")], [self.g], ["BLOCKED"])

    def test_duplicate_dk(self):
        self.check([self.e, self.e], [self.g], ["BLOCKED", "BLOCKED"])

    def test_duplicate_cbbd(self):
        self.check([self.e], [self.g, self.g], ["BLOCKED"])

    def test_ambiguous(self):
        self.check([self.e], [self.g, dict(self.g, game_id="789")], ["BLOCKED"])

    def test_many_to_one(self):
        self.check([self.e, dict(self.e, dk_event_id="124")], [self.g], ["BLOCKED", "BLOCKED"])

    def test_missing_match(self):
        self.check([self.e], [], ["BLOCKED"])

if __name__ == "__main__":
    unittest.main()
