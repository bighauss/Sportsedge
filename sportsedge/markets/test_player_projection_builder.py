"""Synthetic-only tests. Passing these does NOT authenticate pregame features."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import io
import json
import unittest

from sportsedge.markets.player_projection_builder import (
    SCHEMA, build_player_forecast_csv, main,
)
from sportsedge.markets.player_forecast_intake import ingest_player_forecast_csv

F = datetime(2026, 11, 21, 17, tzinfo=timezone.utc)
H = "sha256:" + "a" * 64
SOURCE = {"NFL": "NFLVERSE_NGS", "CFB": "CFB_DATA", "CBB": "CBB_HOOPR"}


def p(sport="CBB"):
    return {
        "schema": SCHEMA, "sport": sport, "event_id": "GAME-1",
        "home_id": "HOME", "away_id": "AWAY",
        "event_start_utc": (F + timedelta(hours=1)).isoformat(),
        "forecast_asof_utc": F.isoformat(),
        "trained_until_utc": (F - timedelta(days=3)).isoformat(),
        "source_published_utc": (F - timedelta(days=1)).isoformat(),
        "source_captured_utc": (F - timedelta(hours=5)).isoformat(),
        "source_snapshot_sha256": H, "source_id": SOURCE[sport],
        "frozen_roster": {"PLAYER-A": "HOME", "PLAYER-B": "AWAY"},
        "players": [],
    }


def player(stat="POINTS", unit="MINUTES", n=30, rate=0.5, sd=5.0,
           pid="PLAYER-A", team="HOME"):
    return {
        "player_id": pid, "team_id": team, "stat": stat,
        "opportunity_unit": unit, "opportunities": n,
        "rate_per_opportunity": rate, "standard_deviation": sd,
        "confirmed_active": True,
    }


def first(raw):
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))[0]


class ThreeSportPlayerProjectionBuilder(unittest.TestCase):
    def test_cbb_points_and_rebounds_are_market_independent(self):
        q = p()
        q["players"] = [player("POINTS", n=32, rate=.6),
                        player("REBOUNDS", n=32, rate=.2, sd=2)]
        raw, report = build_player_forecast_csv(q)
        rows = list(csv.DictReader(io.StringIO(raw.decode())))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["mean"], "19.2")
        self.assertEqual(rows[0]["projected_minutes"], "32")
        self.assertEqual(rows[1]["mean"], "6.4")
        self.assertEqual(report["produced"], 2)
        self.assertEqual(report["blocked"], [])
        self.assertFalse(report["source_authenticated"])
        self.assertFalse(report["calibration_verified"])
        self.assertEqual((report["approved_stake_u"], report["official_counted"]), (0, 0))

    def test_nfl_pass_yards_and_receiving_yards_by_opportunity(self):
        q = p("NFL")
        q["players"] = [player("PASS_YDS", "PASS_ATT", 34, 7, 30),
                        player("REC_YDS", "TARGETS", 8, 8.5, 19,
                               pid="PLAYER-B", team="AWAY")]
        raw, report = build_player_forecast_csv(q)
        rows = list(csv.DictReader(io.StringIO(raw.decode())))
        self.assertEqual(rows[0]["mean"], "238")
        self.assertEqual(rows[1]["mean"], "68")
        self.assertEqual(rows[1]["projected_targets"], "8")
        self.assertEqual(report["produced"], 2)

    def test_cfb_rush_yards_and_receptions(self):
        q = p("CFB")
        q["players"] = [player("RUSH_YDS", "RUSH_ATT", 16, 5.2, 25),
                        player("RECEPTIONS", "TARGETS", 6, .7, 2,
                               pid="PLAYER-B", team="AWAY")]
        raw, report = build_player_forecast_csv(q)
        rows = list(csv.DictReader(io.StringIO(raw.decode())))
        self.assertEqual(rows[0]["mean"], "83.2")
        self.assertEqual(rows[0]["projected_rush_attempts"], "16")
        self.assertEqual(rows[1]["mean"], "4.2")
        self.assertEqual(report["produced"], 2)

    def test_output_is_accepted_by_existing_player_file_intake(self):
        q = p("NFL")
        q["players"] = [player("REC_YDS", "TARGETS", 6, 10, 15)]
        raw, census = build_player_forecast_csv(q)
        intake = ingest_player_forecast_csv(
            raw, sport="NFL", event_id="GAME-1",
            game_roster_ids=frozenset(q["frozen_roster"]),
            event_team_ids=frozenset({"HOME", "AWAY"}),
            forecast_freeze_utc=F,
            odds_observed_at_utc=F + timedelta(minutes=5),
            expected_file_sha256=census["file_sha256"],
        )
        self.assertEqual(intake.moments[0].projected_mean, 60)
        self.assertEqual(intake.moments[0].projected_targets, 6)
        self.assertEqual(intake.moments[0].standard_deviation, 15)

    def test_compound_pra_is_not_faked_from_independent_marginals(self):
        q = p()
        q["players"] = [player("PRA"), player("POINTS")]
        raw, census = build_player_forecast_csv(q)
        self.assertEqual(census["produced"], 1)
        self.assertEqual(census["blocked"],
            [{"player_id": "PLAYER-A", "stat": "PRA",
              "reason": "NO_INDEPENDENT_STAT_RECIPE"}])
        self.assertEqual(first(raw)["stat"], "POINTS")

    def test_no_projections_from_inactive_player_or_low_prop_volume(self):
        q = p("CFB")
        inactive = player("RUSH_YDS", "RUSH_ATT", 18)
        inactive["confirmed_active"] = False
        q["players"] = [inactive,
                        player("REC_YDS", "TARGETS", 3, 10, 9,
                               pid="PLAYER-B", team="AWAY")]
        _, result = build_player_forecast_csv(q)
        self.assertEqual(result["produced"], 0)
        self.assertEqual(result["status"], "BLOCK_NO_PLAYER_FORECASTS")
        self.assertEqual([b["reason"] for b in result["blocked"]],
            ["PLAYER_NOT_CONFIRMED_ACTIVE",
             "RECEIVING_PROP_TARGET_VOLUME_BELOW_FLOOR"])

    def test_wrong_player_team_or_same_name_identity_is_not_guessed(self):
        q = p()
        q["players"] = [player(team="AWAY")]
        with self.assertRaisesRegex(ValueError, "PLAYER_TEAM_EVENT_UNBOUND"):
            build_player_forecast_csv(q)
        q["players"] = [player(pid="PLAYER-MISSING")]
        with self.assertRaisesRegex(ValueError, "PLAYER_TEAM_EVENT_UNBOUND"):
            build_player_forecast_csv(q)

    def test_odds_as_features_rejected_at_root_or_player(self):
        q = p()
        q["players"] = [player()]
        q["odds"] = -110
        with self.assertRaisesRegex(ValueError, "FORBIDDEN_FEATURE"):
            build_player_forecast_csv(q)
        del q["odds"]
        q["players"][0]["market_implied_mean"] = 19
        with self.assertRaisesRegex(ValueError, "ODDS_FEATURE"):
            build_player_forecast_csv(q)

    def test_future_published_or_after_start_features_rejected(self):
        q = p()
        q["players"] = [player()]
        q["source_published_utc"] = (F + timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD_OR_SOURCE_CLOCK"):
            build_player_forecast_csv(q)
        q = p()
        q["players"] = [player()]
        q["forecast_asof_utc"] = q["event_start_utc"]
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD_OR_SOURCE_CLOCK"):
            build_player_forecast_csv(q)

    def test_wrong_source_or_missing_frozen_roster_rejected(self):
        q = p("NFL")
        q["players"] = [player("PASS_YDS", "PASS_ATT")]
        q["source_id"] = "CBB_HOOPR"
        with self.assertRaisesRegex(ValueError, "SOURCE_SPORT_MISMATCH"):
            build_player_forecast_csv(q)
        q["source_id"] = "NFLVERSE_NGS"
        q["frozen_roster"] = {}
        with self.assertRaisesRegex(ValueError, "FROZEN_ROSTER_REQUIRED"):
            build_player_forecast_csv(q)

    def test_duplicate_player_stat_or_incorrect_unit_rejected(self):
        q = p()
        q["players"] = [player(), player()]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PLAYER_STAT"):
            build_player_forecast_csv(q)
        q["players"] = [player(unit="GAME")]
        with self.assertRaisesRegex(ValueError, "WRONG_STAT_OPPORTUNITY_UNIT"):
            build_player_forecast_csv(q)

    def test_nonfinite_rate_and_negative_sd_rejected(self):
        q = p()
        q["players"] = [player(rate=float("nan"))]
        with self.assertRaisesRegex(ValueError, "INVALID_NUMBER"):
            build_player_forecast_csv(q)
        q["players"] = [player(sd=-1)]
        with self.assertRaisesRegex(ValueError, "INVALID_NUMBER"):
            build_player_forecast_csv(q)

    def test_bitidentical_output_hash(self):
        q = p()
        q["players"] = [player()]
        raw, a = build_player_forecast_csv(q)
        other, b = build_player_forecast_csv(deepcopy(q))
        self.assertEqual(raw, other)
        self.assertEqual(a["file_sha256"], b["file_sha256"])
        self.assertEqual(a["file_sha256"], "sha256:" + sha256(raw).hexdigest())

    def test_private_create_only_cli_no_overwrite(self):
        q = p()
        q["players"] = [player()]
        with TemporaryDirectory() as d:
            src = Path(d) / "features.json"
            csv_path = Path(d) / "forecast.csv"
            census_path = Path(d) / "census.json"
            src.write_text(json.dumps(q))
            self.assertEqual(main([str(src), str(csv_path), str(census_path)]), 0)
            result = json.loads(census_path.read_text())
            self.assertEqual(result["produced"], 1)
            self.assertEqual("sha256:" + sha256(csv_path.read_bytes()).hexdigest(),
                             result["file_sha256"])
            with self.assertRaisesRegex(ValueError, "CREATE_ONLY"):
                main([str(src), str(csv_path), str(census_path)])

    def test_failed_census_publication_rolls_back_just_created_csv(self):
        q = p()
        q["players"] = [player()]
        with TemporaryDirectory() as d:
            root = Path(d)
            src = root / "features.json"
            csv_path = root / "forecast.csv"
            # No such parent: forces a failure AFTER the valid CSV is written.
            census_path = root / "missing_directory" / "census.json"
            src.write_text(json.dumps(q))
            original = src.read_bytes()
            with self.assertRaises((FileNotFoundError, NotADirectoryError)):
                main([str(src), str(csv_path), str(census_path)])
            self.assertFalse(csv_path.exists(),
                             "incomplete evidence handoff must not leave an orphan")
            self.assertFalse(census_path.exists())
            self.assertEqual(src.read_bytes(), original)

    def test_existing_census_does_not_get_overwritten_or_leave_csv(self):
        q = p()
        q["players"] = [player()]
        with TemporaryDirectory() as d:
            root = Path(d)
            src = root / "features.json"
            csv_path = root / "forecast.csv"
            census_path = root / "census.json"
            src.write_text(json.dumps(q))
            census_path.write_text("PRESERVE ORIGINAL CENSUS")
            with self.assertRaisesRegex(ValueError, "CREATE_ONLY_OUTPUT_REQUIRED"):
                main([str(src), str(csv_path), str(census_path)])
            self.assertEqual(census_path.read_text(), "PRESERVE ORIGINAL CENSUS")
            self.assertFalse(csv_path.exists())

    def test_duplicate_json_keys_block_before_projection(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "dup.json"
            src.write_text('{"schema":"x","schema":"y"}')
            with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
                main([str(src), str(Path(d)/"a.csv"), str(Path(d)/"b.json")])


if __name__ == "__main__":
    unittest.main()
