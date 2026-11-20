"""Synthetic screenshot price transcription into pre-frozen three-sport research."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo
import json
import unittest

from sportsedge.markets.screenshot_line_handoff import (
    SCHEMA, prepare_line_capture, run_line_capture, main,
)
from sportsedge.markets.test_player_features_run_it import _nfl_setup
from sportsedge.markets.slate_orchestrator import SCHEMA as SLATE_SCHEMA


def offer(kind, side, line, *, stat="", player_id="", team_id=""):
    return {"market": {
        "sport": "NFL", "event_id": "NFL-TEST", "kind": kind,
        "period": "FG", "selection": side, "line": line,
        "team_id": team_id, "player_id": player_id, "stat": stat,
        "settlement": "REGULATION",
    }, "odds_american": -110}


def fixture(directory):
    now = datetime.now(timezone.utc)
    p, f, _ = _nfl_setup(directory)
    start = f["event_start_utc"]
    day = datetime.fromisoformat(start).astimezone(
        ZoneInfo("America/Chicago")).date().isoformat()
    slate = {
        "schema": SLATE_SCHEMA,
        "slate_id": "PRIVATE-FROZEN-TEST",
        "slate_date_ct": day,
        "sports": ["NFL", "CFB", "CBB"],
        "expected_events": [
            {"sport": "NFL", "event_id": "NFL-TEST", "start_utc": start},
        ],
        "event_inputs": [
            {"sport": "NFL", "event_id": "NFL-TEST", "manifest": p},
        ],
    }
    # Synthetic fake PNG header, no actual visual contents: byte binding only.
    image = Path(directory)/"screen.png"
    image.write_bytes(bytes.fromhex("89504e470d0a1a0a") + b"SYNTHETIC-FIXTURE")
    digest = "sha256:" + sha256(image.read_bytes()).hexdigest()
    snap = {
        "schema": SCHEMA, "captures": [{
            "image_path": str(image), "image_sha256": digest,
            "observed_at_utc": (now-timedelta(seconds=25)).isoformat(),
            "received_at_utc": (now-timedelta(seconds=5)).isoformat(),
            "source_surface": "DK_APP_SCREENSHOT",
            "offers": [
                offer("TOTAL", "OVER", "42.5"),
                offer("TOTAL", "UNDER", "42.5"),
                offer("PLAYER_PROP", "OVER", "245.5",
                      stat="PASS_YDS", player_id="QB-1", team_id="Alpha"),
                offer("PLAYER_PROP", "UNDER", "245.5",
                      stat="PASS_YDS", player_id="QB-1", team_id="Alpha"),
            ],
        }],
    }
    return slate, snap, now


class ScreenshotOnlyHandoffTest(unittest.TestCase):
    def test_four_offers_two_pairs_both_sides_priced_without_double_count(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            out = run_line_capture(slate, snap, now=now)
            self.assertEqual((out["captured_offers"], out["paired_markets"]), (4, 2))
            self.assertEqual(out["blocked_offers"], [])
            self.assertFalse(out["source_authenticated"])
            self.assertIsNone(out["wager_card"])
            self.assertEqual((out["official_counted"], out["approved_stake_u"]), (0, 0))
            self.assertEqual(len(out["orientations"]), 2)
            for view in out["orientations"]:
                self.assertEqual(view["counts"]["priced_research"], 2)
                nfl = next(x for x in view["events"] if x["sport"] == "NFL")
                self.assertEqual(nfl["research_candidates"], 2)
                self.assertEqual(nfl["player_projection_builder_census"]["produced"], 2)
                self.assertEqual(nfl["status"], "PAPER_0U_RESEARCH_ONLY")
                self.assertTrue(all(x["guard_state"] == "BLOCK"
                                    for x in nfl["research_rows"]))
            self.assertEqual(out["orientations"][0]["counts"]["expected"], 1)

    def test_broken_opposite_line_blocks_not_autofilled(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            snap["captures"][0]["offers"][1]["market"]["line"] = "44.5"
            r = prepare_line_capture(slate, snap, now=now)
            self.assertEqual(r["paired_markets"], 1)
            self.assertEqual(len(r["blocked_offers"]), 2)
            self.assertTrue(all(x["reason"] == "MISSING_OR_AMBIGUOUS_OPPOSITE_PRICE"
                                for x in r["blocked_offers"]))

    def test_different_images_cannot_form_same_market_two_sided_quote(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            original = snap["captures"][0]
            one = deepcopy(original)
            other = deepcopy(original)
            one["offers"] = [offer("TOTAL", "OVER", "42.5")]
            other["offers"] = [offer("TOTAL", "UNDER", "42.5")]
            image = Path(d) / "different_screen.png"
            image.write_bytes(bytes.fromhex("89504e470d0a1a0a") + b"SECOND-SYNTHETIC-SCREEN")
            other["image_path"] = str(image)
            other["image_sha256"] = "sha256:" + sha256(image.read_bytes()).hexdigest()
            snap["captures"] = [one, other]
            result = prepare_line_capture(slate, snap, now=now)
            self.assertEqual(result["paired_markets"], 0)
            self.assertEqual(len(result["blocked_offers"]), 2)

    def test_unmodelled_sgp_remains_visible_block_while_totals_price(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            sgp = offer("TOTAL", "OVER", "42.5")
            sgp["market"]["kind"] = "SGP"
            sgp["market"]["line"] = ""
            snap["captures"][0]["offers"].append(sgp)
            result = prepare_line_capture(slate, snap, now=now)
            self.assertEqual(result["captured_offers"], 5)
            self.assertEqual(result["paired_markets"], 2)
            self.assertEqual(result["blocked_offers"][0]["reason"],
                             "SCREENSHOT_SGP_NOT_SUPPORTED_NO_JOINT_MODEL")

    def test_one_sided_only_block_no_invented_negative_110(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            snap["captures"][0]["offers"] = [offer("TOTAL", "OVER", "42.5")]
            r = prepare_line_capture(slate, snap, now=now)
            self.assertEqual(r["paired_markets"], 0)
            self.assertEqual(r["blocked_offers"][0]["reason"],
                             "MISSING_OR_AMBIGUOUS_OPPOSITE_PRICE")

    def test_screen_digest_tamper_fails_closed(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            snap["captures"][0]["image_sha256"] = "sha256:"+"0"*64
            with self.assertRaisesRegex(ValueError, "BYTES_OR_SHA256_MISMATCH"):
                prepare_line_capture(slate, snap, now=now)

    def test_duplicate_same_side_in_capture_blocks_both(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            snap["captures"][0]["offers"].append(
                deepcopy(snap["captures"][0]["offers"][0]))
            r = prepare_line_capture(slate, snap, now=now)
            self.assertEqual(r["paired_markets"], 1)
            self.assertEqual(sum(x["reason"] == "DUPLICATE_SCREENSHOT_OFFER_IDENTITY"
                                 for x in r["blocked_offers"]), 2)

    def test_transcription_cannot_supply_its_own_model(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            slate["event_inputs"][0]["manifest"]["projection"] = {
                "sport": "NFL", "event_id": "NFL-TEST",
            }
            del slate["event_inputs"][0]["manifest"]["projection_ref"]
            with self.assertRaisesRegex(
                ValueError, "PREGAME_INDEPENDENT_UNPRICED_PROJECTION_REQUIRED"):
                prepare_line_capture(slate, snap, now=now)

    def test_transcription_cannot_override_frozen_model_inputs(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            snap["captures"][0]["offers"][0]["bookmaker_implied_mean"] = 42.5
            with self.assertRaisesRegex(ValueError, "SCREENSHOT_INVALID_FIELDS:offer"):
                prepare_line_capture(slate, snap, now=now)

    def test_market_names_do_not_fuzzy_match_frozen_event(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            snap["captures"][0]["offers"][0]["market"]["event_id"] = "OTHER-NFL-GAME"
            with self.assertRaisesRegex(ValueError, "SCREENSHOT_EVENT_NOT_IN_FROZEN_SLATE"):
                prepare_line_capture(slate, snap, now=now)

    def test_quote_after_start_or_expired_is_rejected(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            snap["captures"][0]["observed_at_utc"] = (
                now-timedelta(minutes=7)).isoformat()
            with self.assertRaisesRegex(ValueError, "PRICE_STALE_OVER_300"):
                prepare_line_capture(slate, snap, now=now)
            snap["captures"][0]["observed_at_utc"] = (
                now-timedelta(seconds=20)).isoformat()
            snap["captures"][0]["received_at_utc"] = (
                now+timedelta(seconds=2)).isoformat()
            with self.assertRaisesRegex(ValueError, "OBSERVATION_CLOCK_INVALID"):
                prepare_line_capture(slate, snap, now=now)

    def test_new_report_create_only_and_private(self):
        with TemporaryDirectory() as d:
            slate, snap, _ = fixture(d)
            frozen = Path(d)/"frozen_slate.json"
            screenshot_json = Path(d)/"typed_screen.json"
            out = Path(d)/"report.json"
            frozen.write_text(json.dumps(slate))
            screenshot_json.write_text(json.dumps(snap))
            self.assertEqual(main([str(frozen), str(screenshot_json), str(out)]), 0)
            result = json.loads(out.read_text())
            self.assertEqual(result["paired_markets"], 2)
            with self.assertRaises(FileExistsError):
                main([str(frozen), str(screenshot_json), str(out)])

    def test_local_internal_ids_cannot_be_mistaken_for_book_provider_ids(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            pre = prepare_line_capture(slate, snap, now=now)
            candidate = pre["review_runs"][0]["event_inputs"][0]["manifest"]["markets"][0]
            self.assertEqual(candidate["dk_quote"]["provider_id"],
                             "MANUAL_SCREENSHOT_UNVERIFIED")
            self.assertTrue(candidate["dk_quote"]["quote_id"].startswith("LOCAL_SCREEN_"))
            self.assertTrue(candidate["dk_quote"]["provider_market_id"].startswith(
                "LOCAL_GROUP_"))
            self.assertEqual(candidate["dk_quote"]["raw_payload_sha256"],
                             snap["captures"][0]["image_sha256"])

    def test_no_model_for_submitted_event_stays_blocked(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            slate["event_inputs"] = []
            with self.assertRaisesRegex(ValueError, "SCREENSHOT_NO_FROZEN_MODELS"):
                prepare_line_capture(slate, snap, now=now)

    def test_three_sports_are_supported_without_hallucinating_schedule(self):
        with TemporaryDirectory() as d:
            slate, snap, now = fixture(d)
            result = run_line_capture(slate, snap, now=now)
            for view in result["orientations"]:
                self.assertEqual(view["sport_coverage"]["CFB"]["expected_games"], 0)
                self.assertEqual(view["sport_coverage"]["CBB"]["expected_games"], 0)
                self.assertFalse(view["schedule_independently_authenticated"])


if __name__ == "__main__":
    unittest.main()
