"""Offline regressions for the single-request NFL odds pilot."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sportsedge.odds.daily_main_odds import run_daily
from sportsedge.odds.free_odds_aggregator_intake import REPOSITORY_ROOT


class DailyMainOddsTests(unittest.TestCase):
    clock = datetime(2026, 11, 21, 23, tzinfo=timezone.utc)
    summary = {
        "raw_filename": "original.json",
        "original_raw_sha256": "sha256:" + "a" * 64,
        "events_returned": 5,
        "outcomes_returned": 55,
        "live_poststart_outcomes_blocked": 4,
        "stale_or_missing_aggregator_market_timestamp_outcomes": 2,
        "provider_remaining_credits": "497",
        "provider_request_credits_last": "3",
    }

    def test_dry_run_does_not_request_or_touch_disk(self):
        with TemporaryDirectory() as d, patch("sportsedge.odds.daily_main_odds.capture") as capture:
            root = Path(d) / "archive"
            out = run_daily(root, now=self.clock)
            capture.assert_not_called()
            self.assertFalse(root.exists())
        self.assertEqual(out["state"], "DRY_RUN")
        self.assertEqual(out["maximum_credits_this_attempt"], 3)
        self.assertEqual(out["maximum_pilot_credits_per_31_central_dates"], 93)

    def test_concurrent_retries_make_one_request_and_create_private_receipt(self):
        with TemporaryDirectory() as d, patch(
            "sportsedge.odds.daily_main_odds.capture", return_value=self.summary
        ) as capture:
            root = Path(d) / "archive"
            with ThreadPoolExecutor(max_workers=4) as threads:
                results = list(threads.map(
                    lambda _: run_daily(root, execute=True, now=self.clock), range(4)))
            self.assertEqual(capture.call_count, 1)
            self.assertEqual(capture.call_args.args, ("NFL", root))
            self.assertEqual(capture.call_args.kwargs["markets"], ("h2h", "spreads", "totals"))
            self.assertEqual(sum(r["state"] == "ARCHIVED_PROVIDER_RESPONSE" for r in results), 1)
            self.assertEqual(sum(r["state"] == "SKIPPED_ALREADY_ATTEMPTED" for r in results), 3)
            receipt_path = root / "daily-nfl-main-2026-11-21.result.json"
            receipt = json.loads(receipt_path.read_text())
            self.assertEqual(receipt["archive"]["raw_filename"], "original.json")
            self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(receipt["full_board"])
            self.assertFalse(receipt["close"])
            self.assertEqual(receipt["approved_stake_u"], 0)

    def test_failed_attempt_cannot_retry_or_echo_secret(self):
        with TemporaryDirectory() as d, patch(
            "sportsedge.odds.daily_main_odds.capture", side_effect=ValueError("EXAMPLE_PRIVATE_VALUE")
        ) as capture:
            root = Path(d)
            result = run_daily(root, execute=True, now=self.clock)
            self.assertEqual(result["state"], "CAPTURE_FAILED_REVIEW_PRIVATELY")
            self.assertNotIn("EXAMPLE_PRIVATE_VALUE", str(result))
            out = run_daily(root, execute=True, now=self.clock)
            self.assertEqual(out["state"], "SKIPPED_ALREADY_ATTEMPTED")
            self.assertEqual(capture.call_count, 1)

    def test_one_day_is_central_not_utc(self):
        before = datetime(2026, 11, 22, 5, 59, tzinfo=timezone.utc)
        after = datetime(2026, 11, 22, 6, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as d:
            self.assertEqual(run_daily(Path(d), now=before)["date_ct"], "2026-11-21")
            self.assertEqual(run_daily(Path(d), now=after)["date_ct"], "2026-11-22")

    def test_unexpected_or_unverified_quota_blocks_next_day(self):
        for override, state in (
            ({"provider_request_credits_last": "4"}, "ARCHIVED_UNEXPECTED_QUOTA_COST_PAUSE"),
            ({"provider_request_credits_last": None}, "ARCHIVED_QUOTA_UNCONFIRMED_REVIEW"),
            ({"provider_remaining_credits": "2"}, "ARCHIVED_LOW_REMAINING_QUOTA_PAUSE"),
        ):
            with self.subTest(state=state), TemporaryDirectory() as d, patch(
                "sportsedge.odds.daily_main_odds.capture", return_value={**self.summary, **override}
            ) as capture:
                root = Path(d)
                self.assertEqual(run_daily(root, execute=True, now=self.clock)["state"], state)
                following = run_daily(root, execute=True, now=self.clock + timedelta(days=1))
                self.assertEqual(following["state"], "BLOCKED_PRIOR_QUOTA_REVIEW")
                capture.assert_called_once()

    def test_rejects_public_or_group_readable_path_before_capture(self):
        with TemporaryDirectory() as d, patch("sportsedge.odds.daily_main_odds.capture") as capture:
            root = Path(d)
            root.chmod(0o755)
            for invalid in (root, REPOSITORY_ROOT):
                with self.assertRaises(ValueError):
                    run_daily(invalid, execute=True, now=self.clock)
            capture.assert_not_called()
