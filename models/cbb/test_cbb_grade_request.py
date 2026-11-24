import json
from datetime import datetime, timezone
import unittest
from cbb_grade_request import validate, SCHEMA


class GradeRequest(unittest.TestCase):
    now = datetime(2026, 11, 24, 5, 59, tzinfo=timezone.utc)  # Nov 23 CT

    def request(self, **over):
        return json.dumps(dict({"schema": SCHEMA, "date_ct": "2026-11-22",
                                "season": 2027, "label": "PAPER_0U"}, **over)).encode()

    def test_previous_completed_central_date(self):
        day, season = validate(self.request(), self.now)
        self.assertEqual(day.isoformat(), "2026-11-22")
        self.assertEqual(season, 2027)

    def test_same_central_date_wrong_season_and_extra_fields_block(self):
        for kwargs in ({"date_ct": "2026-11-23"}, {"season": 2026}, {"label": "LIVE"},
                       {"stake": 1}, {"date_ct": "2026-11-25"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                validate(self.request(**kwargs), self.now)

    def test_duplicate_keys_refused(self):
        with self.assertRaises(ValueError):
            validate(b'{"schema":"x","schema":"y"}', self.now)
