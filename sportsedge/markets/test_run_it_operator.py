"""Synthetic acceptance checks for the offline RUN IT operator command."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sportsedge.markets.run_it_operator import REPO, main, run_operator
from sportsedge.markets.test_screenshot_line_handoff import fixture as screenshot_fixture
from sportsedge.markets.test_slate_orchestrator import fixture as slate_fixture


class RunItOperatorTests(unittest.TestCase):
    def test_receipt_slate_produces_research_and_preserves_full_census(self):
        result = run_operator(slate_fixture())
        self.assertEqual(result["input_lane"], "PREPARED_SLATE")
        self.assertEqual(result["state"], "PAPER_RESEARCH_AVAILABLE")
        self.assertEqual(result["summary"], {"scheduled_events": 2,
                                             "research_priced_sides": 1})
        self.assertEqual(len(result["research"]["events"]), 2)
        self.assertIsNone(result["final_bets"])
        self.assertEqual((result["approved_stake_u"], result["official_counted"]), (0, 0))

    def test_no_lines_preserves_events_and_explains_block(self):
        slate = slate_fixture()
        slate["event_inputs"][0]["manifest"]["markets"] = []
        result = run_operator(slate)
        self.assertEqual(result["state"], "NEEDS_LINES_OR_REVIEW")
        self.assertEqual(result["summary"]["scheduled_events"], 2)
        self.assertEqual(result["summary"]["research_priced_sides"], 0)
        self.assertIn("CHECK_FROZEN_INPUTS_AND_SUBMITTED_EXACT_PRICES",
                      result["next_actions"])
        self.assertTrue(all("NO_MARKETS_SUBMITTED_OR_OFFERED_UNVERIFIED" in event["reasons"]
                            for event in result["research"]["events"]))
        self.assertIsNone(result["final_bets"])

    def test_screenshots_count_unique_events_and_keep_side_orientations(self):
        with TemporaryDirectory() as d:
            slate, screenshots, asof = screenshot_fixture(d)
            result = run_operator(slate, screenshots, now=asof)
        self.assertEqual(result["input_lane"], "SCREENSHOT_TRANSCRIPTION")
        self.assertEqual(result["summary"], {"scheduled_events": 1,
                                             "research_priced_sides": 4})
        self.assertEqual(len(result["research"]["orientations"]), 2)
        self.assertEqual(result["research"]["paired_markets"], 2)
        self.assertEqual(result["decision_at_utc"], asof.isoformat())
        self.assertEqual(result["decision_clock"], "EXPLICIT_REPLAY")
        self.assertTrue(all(view["generated_at_utc"] == asof.isoformat()
                            for view in result["research"]["orientations"]))
        self.assertFalse(result["source_authenticated"])
        self.assertIsNone(result["final_bets"])

    def test_partial_screen_never_invents_the_missing_side(self):
        with TemporaryDirectory() as d:
            slate, screenshots, asof = screenshot_fixture(d)
            screenshots["captures"][0]["offers"] = screenshots["captures"][0]["offers"][:1]
            result = run_operator(slate, screenshots, now=asof)
        self.assertEqual(result["state"], "NEEDS_LINES_OR_REVIEW")
        self.assertEqual(result["research"]["paired_markets"], 0)
        self.assertEqual([row["reason"] for row in result["research"]["blocked_offers"]],
                         ["MISSING_OR_AMBIGUOUS_OPPOSITE_PRICE"])
        self.assertIn("REVIEW_EVENT_AND_OFFER_BLOCK_REASONS", result["next_actions"])

    def test_screenshots_refuse_quote_bound_overlay(self):
        with TemporaryDirectory() as d:
            slate, screenshots, asof = screenshot_fixture(d)
            slate["projection_evidence"] = [{"synthetic": "quote-bound"}]
            with self.assertRaisesRegex(ValueError, "RUN_IT_SCREENSHOT_EVIDENCE_OVERLAY_UNSUPPORTED"):
                run_operator(slate, screenshots, now=asof)

    def test_refuses_underlying_nonzero_or_official_release(self):
        with patch("sportsedge.markets.run_it_operator.run_slate") as run:
            for invalid in ({"approved_stake_u": 1}, {"approved_stake_u": False},
                            {"card": {}}, {"issue10_release_certified": True}):
                with self.subTest(invalid=invalid):
                    run.return_value = {"approved_stake_u": 0, "official_counted": 0,
                                        "card": None, "issue10_release_certified": False,
                                        **invalid}
                    with self.assertRaisesRegex(ValueError, "RUN_IT_RELEASE_INVARIANT_FAILED"):
                        run_operator({})

    def test_cli_hashes_bytes_uses_private_create_only_output(self):
        with (TemporaryDirectory() as d, redirect_stdout(io.StringIO()) as stdout,
              redirect_stderr(io.StringIO()) as stderr):
            src = Path(d) / "slate.json"
            dst = Path(d) / "out.json"
            src.write_text(json.dumps(slate_fixture()), encoding="utf-8")
            self.assertEqual(main([str(src), str(dst)]), 0)
            report = json.loads(dst.read_text())
            self.assertRegex(report["input_sha256"]["slate"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(dst.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(str(dst), stdout.getvalue())
            self.assertEqual(json.loads(stdout.getvalue())["decision_clock"], "SYSTEM_UTC")
            self.assertEqual(main([str(src), str(dst)]), 2)
            self.assertEqual(json.loads(stderr.getvalue())["reason"], "RUN_IT_REPORT_ALREADY_EXISTS")
            self.assertEqual(json.loads(dst.read_text()), report)

    def test_cli_rejects_repo_paths_and_same_paths(self):
        with TemporaryDirectory() as d, redirect_stderr(io.StringIO()) as stderr:
            src = Path(d) / "slate.json"
            dst = Path(d) / "out.json"
            self.assertEqual(main([str(src), str(src)]), 2)
            self.assertEqual(main([str(REPO / "README.md"), str(dst)]), 2)
            self.assertEqual([json.loads(line)["reason"] for line in stderr.getvalue().splitlines()],
                             ["RUN_IT_DISTINCT_PATHS_REQUIRED", "RUN_IT_PRIVATE_PATH_REQUIRED"])
            self.assertFalse(dst.exists())

    def test_cli_redacts_invalid_json_and_rejects_overflow(self):
        with TemporaryDirectory() as d, redirect_stderr(io.StringIO()) as stderr:
            src, dst = Path(d) / "input.json", Path(d) / "new-report.json"
            for payload, reason in (
                ('{"PRIVATE_LABEL":{"PRIVATE_LABEL":0,"PRIVATE_LABEL":1}}',
                 "RUN_MANIFEST_DUPLICATE_JSON_KEY"),
                ('{"PRIVATE_LABEL":NaN}', "RUN_MANIFEST_NONFINITE_JSON_NUMBER"),
                ('{"PRIVATE_LABEL":1e999}', "RUN_MANIFEST_NONFINITE_JSON_NUMBER"),
                ('{"PRIVATE_LABEL":', "RUN_IT_MALFORMED_JSON"),
            ):
                with self.subTest(reason=reason):
                    src.write_text(payload, encoding="utf-8")
                    self.assertEqual(main([str(src), str(dst)]), 2)
                    self.assertEqual(json.loads(stderr.getvalue().splitlines()[-1])["reason"], reason)
                    self.assertFalse(dst.exists())
            self.assertNotIn("PRIVATE_LABEL", stderr.getvalue())

    def test_cli_screen_replay_reproduces_private_report_and_expires(self):
        with (TemporaryDirectory() as d, redirect_stdout(io.StringIO()) as stdout,
              redirect_stderr(io.StringIO()) as stderr):
            slate, screenshots, asof = screenshot_fixture(d)
            src, screens = Path(d) / "slate.json", Path(d) / "screens.json"
            src.write_text(json.dumps(slate), encoding="utf-8")
            screens.write_text(json.dumps(screenshots), encoding="utf-8")
            reports = [Path(d) / f"report-{i}.json" for i in range(3)]
            for path in reports[:2]:
                self.assertEqual(main([str(src), str(path), "--screenshots", str(screens),
                                       "--replay-at", asof.isoformat()]), 0)
            self.assertEqual(reports[0].read_bytes(), reports[1].read_bytes())
            result = json.loads(reports[0].read_text())
            self.assertEqual(result["summary"]["research_priced_sides"], 4)
            self.assertIn("screenshots", result["input_sha256"])
            self.assertEqual(json.loads(stdout.getvalue().splitlines()[0])["decision_clock"],
                             "EXPLICIT_REPLAY")
            observed = datetime.fromisoformat(screenshots["captures"][0]["observed_at_utc"])
            # Use old synthetic capture times to test staleness without crossing wall time.
            screenshots["captures"][0].update(
                observed_at_utc=(observed - timedelta(minutes=5)).isoformat(),
                received_at_utc=(observed - timedelta(minutes=4)).isoformat(),
            )
            screens.write_text(json.dumps(screenshots), encoding="utf-8")
            self.assertEqual(main([str(src), str(reports[2]), "--screenshots", str(screens),
                                   "--replay-at", asof.isoformat()]), 2)
            self.assertFalse(reports[2].exists())
            self.assertEqual(json.loads(stderr.getvalue())["reason"],
                             "SCREENSHOT_PRICE_STALE_OVER_300_SECONDS")

    def test_cli_never_echoes_unrecognized_args_or_accepts_future_replay(self):
        with TemporaryDirectory() as d, redirect_stderr(io.StringIO()) as stderr:
            src, dst = Path(d) / "slate.json", Path(d) / "report.json"
            src.write_text(json.dumps(slate_fixture()), encoding="utf-8")
            self.assertEqual(main([str(src), str(dst), "PRIVATE_ARG"]), 2)
            future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            self.assertEqual(main([str(src), str(dst), "--replay-at", future]), 2)
            self.assertNotIn("PRIVATE_ARG", stderr.getvalue())
            self.assertEqual([json.loads(line)["reason"] for line in stderr.getvalue().splitlines()],
                             ["RUN_IT_INVALID_ARGUMENTS", "RUN_IT_FUTURE_REPLAY_CLOCK"])
            self.assertFalse(dst.exists())

    def test_cli_rejects_extreme_decimal_market_line(self):
        with TemporaryDirectory() as d, redirect_stderr(io.StringIO()) as stderr:
            slate, screenshots, asof = screenshot_fixture(d)
            screenshots["captures"][0]["offers"][0]["market"]["line"] = "1e1000000"
            src, screens, dst = (Path(d) / name for name in ("slate.json", "screens.json", "report.json"))
            src.write_text(json.dumps(slate), encoding="utf-8")
            screens.write_text(json.dumps(screenshots), encoding="utf-8")
            self.assertEqual(main([str(src), str(dst), "--screenshots", str(screens),
                                   "--replay-at", asof.isoformat()]), 2)
            self.assertEqual(json.loads(stderr.getvalue())["state"], "RUN_IT_REJECTED")
            self.assertNotIn("1e1000000", stderr.getvalue())
            self.assertFalse(dst.exists())


if __name__ == "__main__":
    unittest.main()
