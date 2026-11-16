"""Synthetic CFB source-history checks; do not use these as real CFBD receipts."""
from copy import deepcopy
from hashlib import sha256
import json
import unittest

from models.cfb.cfb_source_pit_contract import (
    SCHEMA, SOURCES, FAMILIES, PITRefused, audit,
)

FROZEN = "2026-11-15T18:00:00Z"
KICKOFF = "2026-11-15T21:00:00Z"
EVENT = "cfbd:2026:123"


def fixture(*, all_prices=True):
    payloads = {
        "game": {"event_id": EVENT, "season": 2026, "home_team_id": "TEAM_HOME",
                 "away_team_id": "TEAM_AWAY", "kickoff_utc": KICKOFF},
        "team_stats": [
            {"team_id": "TEAM_HOME", "season": 2026, "offense_ppa": 0.2,
             "defense_ppa": -0.1, "plays_per_game": 71.0},
            {"team_id": "TEAM_AWAY", "season": 2026, "offense_ppa": 0.1,
             "defense_ppa": 0.0, "plays_per_game": 65.0},
        ],
        "qb": [
            {"team_id": "TEAM_HOME", "qb_id": "QB_H", "starter_status": "CONFIRMED"},
            {"team_id": "TEAM_AWAY", "qb_id": "QB_A", "starter_status": "CONFIRMED"},
        ],
        "weather": {"event_id": EVENT, "is_forecast": True, "wind_mph": 9},
        "injuries": [],
    }
    raw = {k: json.dumps(v, sort_keys=True).encode() for k, v in payloads.items()}
    receipts = {
        k: {
            "provider": "operator_allowed_export_" + k,
            "sha256": sha256(raw[k]).hexdigest(),
            "published_utc": "2026-11-15T17:00:00Z",
            "observed_utc": "2026-11-15T17:05:00Z",
            "captured_utc": "2026-11-15T17:06:00Z",
        }
        for k in SOURCES
    }
    census = [
        ({"family": fam, "state": "CAPTURED_UNVERIFIED",
          "receipt_sha256": "a" * 64}
         if all_prices else
         {"family": fam, "state": "NOT_CAPTURED",
          "reason": "NO_ORIGINAL_QUOTE"})
        for fam in FAMILIES
    ]
    manifest = {
        "schema": SCHEMA, "event_id": EVENT, "season": 2026,
        "frozen_utc": FROZEN, "kickoff_utc": KICKOFF,
        "source_clock_receipts": receipts,
        "market_family_census": census,
    }
    return raw, manifest


def replace_payload(raw, manifest, key, body):
    raw[key] = json.dumps(body, sort_keys=True).encode()
    manifest["source_clock_receipts"][key]["sha256"] = sha256(raw[key]).hexdigest()


class TestCFBSourcePIT(unittest.TestCase):
    def test_clean_structural_claim_never_authenticates_or_prices(self):
        raw, man = fixture()
        out = audit(raw, man)
        self.assertEqual(out["status"], "PAPER_0U_LOCAL_CFB_SOURCE_CLAIMS_ONLY")
        self.assertEqual(out["official_counted"], 0)
        self.assertEqual(out["approved_stake_u"], 0)
        self.assertFalse(out["source_externally_authenticated"])
        self.assertFalse(out["market_inventory_authenticated"])
        self.assertFalse(out["model_projections_generated"])
        self.assertEqual(set(out["observed_market_family_states"]), set(FAMILIES))
        self.assertEqual(len(out["source_raw_sha256"]), 5)

    def test_missing_market_quotes_visible_as_block_not_not_offered(self):
        raw, man = fixture(all_prices=False)
        report = audit(raw, man)
        self.assertEqual(report["status"], "BLOCK")
        self.assertIn("ORIGINAL_ALL_MARKET_QUOTES_INCOMPLETE", report["reasons"])
        self.assertFalse(report["gate_a_closed"])

    def test_future_published_advanced_stats_rejected(self):
        raw, man = fixture()
        man["source_clock_receipts"]["team_stats"]["published_utc"] = "2026-11-15T18:01:00Z"
        with self.assertRaisesRegex(PITRefused, "SOURCE_LOOKAHEAD"):
            audit(raw, man)

    def test_future_weather_publication_rejected(self):
        raw, man = fixture()
        man["source_clock_receipts"]["weather"]["captured_utc"] = "2026-11-15T18:02:00Z"
        with self.assertRaisesRegex(PITRefused, "SOURCE_LOOKAHEAD"):
            audit(raw, man)

    def test_game_kickoff_revision_requires_refreeze(self):
        raw, man = fixture()
        game = json.loads(raw["game"])
        game["kickoff_utc"] = "2026-11-15T22:00:00Z"
        replace_payload(raw, man, "game", game)
        with self.assertRaisesRegex(PITRefused, "GAME_KICKOFF_REVISED"):
            audit(raw, man)

    def test_wrong_team_in_advanced_stats_refused(self):
        raw, man = fixture()
        rows = json.loads(raw["team_stats"])
        rows[1]["team_id"] = "TEAM_UNRELATED"
        replace_payload(raw, man, "team_stats", rows)
        with self.assertRaisesRegex(PITRefused, "STATS_TEAM_ID_MISMATCH"):
            audit(raw, man)

    def test_duplicate_team_stats_does_not_last_row_win(self):
        raw, man = fixture()
        rows = json.loads(raw["team_stats"])
        rows[1]["team_id"] = rows[0]["team_id"]
        replace_payload(raw, man, "team_stats", rows)
        with self.assertRaisesRegex(PITRefused, "STATS_DUPLICATE_TEAM"):
            audit(raw, man)

    def test_duplicate_team_qb_crosswalk_refused(self):
        raw, man = fixture()
        rows = json.loads(raw["qb"])
        rows[1]["team_id"] = rows[0]["team_id"]
        replace_payload(raw, man, "qb", rows)
        with self.assertRaisesRegex(PITRefused, "QB_DUPLICATE_TEAM"):
            audit(raw, man)

    def test_unconfirmed_qb_blocks_candidate_research(self):
        raw, man = fixture()
        rows = json.loads(raw["qb"])
        rows[0]["starter_status"] = "UNKNOWN"
        replace_payload(raw, man, "qb", rows)
        report = audit(raw, man)
        self.assertEqual(report["status"], "BLOCK")
        self.assertIn("QB_STARTER_NOT_CONFIRMED:TEAM_HOME", report["reasons"])

    def test_retrospective_weather_not_allowed_as_forecast(self):
        raw, man = fixture()
        wx = json.loads(raw["weather"])
        wx["is_forecast"] = False
        replace_payload(raw, man, "weather", wx)
        report = audit(raw, man)
        self.assertIn("WEATHER_NOT_A_PREGAME_FORECAST", report["reasons"])
        self.assertEqual(report["approved_stake_u"], 0)

    def test_injury_status_unresolved_is_visible(self):
        raw, man = fixture()
        replace_payload(raw, man, "injuries", [
            {"team_id": "TEAM_HOME", "player_id": "PLAYER_X", "status": "QUESTIONABLE"}])
        report = audit(raw, man)
        self.assertIn("INJURY_PARTICIPATION_UNRESOLVED:PLAYER_X", report["reasons"])

    def test_duplicate_player_injury_not_silently_merged(self):
        raw, man = fixture()
        item = {"team_id": "TEAM_HOME", "player_id": "PLAYER_X", "status": "OUT"}
        replace_payload(raw, man, "injuries", [item, item])
        with self.assertRaisesRegex(PITRefused, "DUPLICATE_INJURY_PLAYER_ID"):
            audit(raw, man)

    def test_duplicate_original_nested_json_key_refused_even_with_sha_update(self):
        raw, man = fixture()
        body = raw["game"].decode().replace(
            '"home_team_id": "TEAM_HOME"',
            '"home_team_id": "TEAM_HOME", "home_team_id": "OTHER"', 1)
        raw["game"] = body.encode()
        man["source_clock_receipts"]["game"]["sha256"] = sha256(raw["game"]).hexdigest()
        with self.assertRaisesRegex(PITRefused, "ORIGINAL_DUPLICATE_JSON_KEY"):
            audit(raw, man)

    def test_nonfinite_float_exponent_overflow_blocked(self):
        raw, man = fixture()
        text = raw["weather"].decode().replace(
            '"wind_mph": 9', '"wind_mph": 1e999')
        raw["weather"] = text.encode()
        man["source_clock_receipts"]["weather"]["sha256"] = sha256(raw["weather"]).hexdigest()
        with self.assertRaisesRegex(PITRefused, "ORIGINAL_NONFINITE_NUMBER"):
            audit(raw, man)

    def test_missing_entire_source_refused(self):
        raw, man = fixture()
        raw.pop("injuries")
        with self.assertRaisesRegex(PITRefused, "ALL_FIVE_ORIGINAL_SOURCES_REQUIRED"):
            audit(raw, man)

    def test_source_sha_mismatch_refused(self):
        raw, man = fixture()
        raw["team_stats"] += b" "
        with self.assertRaisesRegex(PITRefused, "ORIGINAL_SOURCE_SHA_MISMATCH"):
            audit(raw, man)

    def test_missing_family_from_full_market_census_fails(self):
        raw, man = fixture()
        man["market_family_census"].pop()
        with self.assertRaisesRegex(PITRefused, "INCOMPLETE_ALL_MARKET_FAMILY_CENSUS"):
            audit(raw, man)

    def test_caller_not_offered_without_authenticated_book_refused(self):
        raw, man = fixture()
        man["market_family_census"][0]["state"] = "NOT_OFFERED"
        with self.assertRaisesRegex(PITRefused, "UNAUTHENTICATED_OFFER_STATE"):
            audit(raw, man)

    def test_captured_market_without_original_receipt_hash_refused(self):
        raw, man = fixture()
        man["market_family_census"][0].pop("receipt_sha256")
        with self.assertRaisesRegex(PITRefused, "CAPTURED_ROW_REQUIRES_ORIGINAL_RECEIPT_HASH"):
            audit(raw, man)

    def test_freeze_after_kickoff_blocked(self):
        raw, man = fixture()
        man["frozen_utc"] = man["kickoff_utc"]
        with self.assertRaisesRegex(PITRefused, "FREEZE_NOT_BEFORE_KICKOFF"):
            audit(raw, man)

    def test_missing_qb_model_stats_no_silent_league_mean(self):
        raw, man = fixture()
        rows = json.loads(raw["team_stats"])
        del rows[0]["plays_per_game"]
        replace_payload(raw, man, "team_stats", rows)
        with self.assertRaisesRegex(PITRefused, "MODEL_SOURCE_STAT_INVALID"):
            audit(raw, man)


if __name__ == "__main__":
    unittest.main()
