import unittest

from research.cbb_contract_events import group_events
from research.cbb_event_binding import reconcile


class ContractIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.base = dict(
            dk_event_id="123", home="A", away="B",
            tipoff_ct="2026-11-24T09:00:00-06:00", source_comment_id="123456",
            capture_start_ct="2026-11-24T07:30:00-06:00",
            capture_end_ct="2026-11-24T07:45:00-06:00",
            sport="CBB", period="FULL_GAME", eligible_for_pricing=False,
            settlement_rules_verified=False,
        )

    def markets(self, kinds=("TOTAL", "SPREAD"), **changes):
        return [dict(self.base, market=k, **changes) for k in kinds]

    def rejected(self, rows):
        events, blocked = group_events(rows)
        self.assertEqual(events, [])
        self.assertEqual(sum(r["contract_count"] for r in blocked), len(rows))

    def test_group_then_bind(self):
        slate = [dict(game_id=456, _home="A", _away="B", tipoff_utc="2026-11-24T15:00:00Z")]
        for kinds in [("TOTAL", "SPREAD"), ("TOTAL", "SPREAD", "ML")]:
            events, blocked = group_events(self.markets(kinds))
            self.assertEqual(blocked, [])
            self.assertEqual(len(events), 1)
            self.assertEqual(reconcile(events, slate),
                             [dict(dk_event_id="123", status="MATCHED", cbbd_game_id="456")])
            self.assertNotIn("eligible_for_pricing", events[0])

    def test_reject_malformed_rows_without_losing_other_events(self):
        for bad in [{}, None, {"dk_event_id": []}, {"dk_event_id": 123}]:
            with self.subTest(bad=bad):
                events, blocked = group_events([bad] + self.markets())
                self.assertEqual(len(events), 1)
                self.assertEqual([r["contract_count"] for r in blocked], [1])

    def test_reject_bad_teams(self):
        for home, away in [("", "B"), (" A", "a"), ("A", 1), ("  ", "B")]:
            with self.subTest(home=home, away=away):
                self.rejected(self.markets(home=home, away=away))

    def test_require_source_reference(self):
        for source in ["", None, False]:
            with self.subTest(source=source):
                self.rejected(self.markets(source_comment_id=source))

    def test_reject_wrong_market_census(self):
        for kinds in [("TOTAL",), ("TOTAL", "SPREAD", "TOTAL"), ("TOTAL", "SPREAD", "PROP")]:
            self.rejected(self.markets(kinds))

    def test_reject_mixed_metadata(self):
        rows = self.markets()
        rows[1]["away"] = "C"
        self.rejected(rows)

    def test_reject_bad_chronology(self):
        for changes in [dict(capture_end_ct=self.base["tipoff_ct"]),
                        dict(capture_start_ct=self.base["tipoff_ct"]),
                        dict(capture_end_ct="2026-11-24T07:45:00")]:
            self.rejected(self.markets(**changes))

    def test_reject_nonresearch_or_wrong_period(self):
        for changes in [dict(sport="CFB"), dict(period="1H"), dict(eligible_for_pricing=True),
                        dict(settlement_rules_verified=True)]:
            self.rejected(self.markets(**changes))
