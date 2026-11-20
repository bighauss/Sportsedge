"""PAPER-only direct, from-source player stat projection to RUN IT research rows."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from sportsedge.markets.cli import run_from_manifest
from sportsedge.markets.test_cli import manifest, source_manifest
from sportsedge.markets.player_projection_builder import SCHEMA

H = "sha256:" + "a" * 64


def _player(stat, unit, opportunities, rate, sd, player, team, active=True):
    return {
        "player_id": player, "team_id": team, "stat": stat,
        "opportunity_unit": unit, "opportunities": opportunities,
        "rate_per_opportunity": rate, "standard_deviation": sd,
        "confirmed_active": active,
    }


def _nfl_setup(directory):
    now = datetime.now(timezone.utc)
    asof = (now - timedelta(hours=1)).isoformat()
    rating = Path(directory) / "ratings.csv"
    rating.write_text("team,off,def,gp,lg,hfa,asof,half_life,ridge\n"
                      "Alpha,2,1,5,21,1.6,2026-11-15,45,5\n"
                      "Beta,-1,0,5,21,1.6,2026-11-15,45,5\n")
    p = manifest()
    p.pop("projection")
    p["projection_ref"] = {
        "sport": "NFL", "event_id": "NFL-TEST", "asof_utc": asof,
        "ratings_csv": str(rating),
        "source_manifest": source_manifest(
            {"ratings_csv": str(rating)}, "NFL", "NFL-TEST", asof),
        "forecast": {
            "home": "Alpha", "away": "Beta",
            "home_proj": "23.800", "away_proj": "18.200",
            "model_version": "SPORTSEDGE_NFL_RIDGE_R1",
            "asof_ct": "2026-11-15T12:00:00+00:00",
        },
    }
    p["distribution"]["sport"] = "NFL"
    p["roster_ids"] = ["QB-1", "WR-1"]
    started = p["markets"][0]["dk_quote"]["event_start_utc"]
    features = {
        "schema": SCHEMA, "sport": "NFL", "event_id": "NFL-TEST",
        "home_id": "Alpha", "away_id": "Beta",
        "event_start_utc": started,
        "forecast_asof_utc": asof,
        "trained_until_utc": (now - timedelta(days=15)).isoformat(),
        "source_published_utc": (now - timedelta(hours=5)).isoformat(),
        "source_captured_utc": (now - timedelta(hours=4)).isoformat(),
        "source_snapshot_sha256": H, "source_id": "NFLVERSE_NGS",
        "frozen_roster": {"QB-1": "Alpha", "WR-1": "Beta"},
        "players": [
            _player("PASS_YDS", "PASS_ATT", 35, 7, 27, "QB-1", "Alpha"),
            _player("REC_YDS", "TARGETS", 7, 8, 20, "WR-1", "Beta"),
        ],
    }
    path = Path(directory) / "player_features.json"
    raw = json.dumps(features, sort_keys=True).encode()
    path.write_bytes(raw)
    p["player_features_ref"] = {
        "path": str(path),
        "raw_sha256": "sha256:" + sha256(raw).hexdigest(),
        "odds_observed_at_utc": p["markets"][0]["dk_quote"]["observed_at_utc"],
    }
    p["markets"] = []
    return p, features, path


def _update_features(p, path, features):
    raw = json.dumps(features, sort_keys=True).encode()
    path.write_bytes(raw)
    p["player_features_ref"]["raw_sha256"] = "sha256:" + sha256(raw).hexdigest()


class DirectThreeSportPlayerResearch(unittest.TestCase):
    def test_nfl_real_recovered_team_model_plus_private_features(self):
        with TemporaryDirectory() as d:
            p, features, path = _nfl_setup(d)
            out = run_from_manifest(p)
            census = out["player_projection_builder_census"]
            self.assertEqual(out["model_projection_method"], "RECOVERED_MODEL_FUNCTION")
            self.assertEqual(out["player_projection_producer"],
                             "THREE_SPORT_PRIVATE_FEATURES_UNVERIFIED")
            self.assertEqual(census["produced"], 2)
            self.assertEqual(census["submitted"], 2)
            self.assertEqual((out["official_counted"], out["approved_stake_u"]), (0, 0))
            self.assertFalse(census["source_authenticated"])

    def test_nfl_player_prop_prices_without_bookmaker_derived_model_mean(self):
        with TemporaryDirectory() as d:
            p, _, _ = _nfl_setup(d)
            base = manifest()["markets"][0]
            m = {
                "sport": "NFL", "event_id": "NFL-TEST", "kind": "PLAYER_PROP",
                "period": "FG", "selection": "OVER", "line": "246.5",
                "player_id": "QB-1", "team_id": "Alpha",
                "stat": "PASS_YDS", "settlement": "REGULATION",
            }
            base["market"] = m
            base["dk_quote"]["market"] = m
            base["dk_opposite_quote"]["market"] = dict(m, selection="UNDER")
            base["dk_quote"]["event_start_utc"] = p["player_features_ref"].get(
                "event_start_utc", base["dk_quote"]["event_start_utc"])
            # Align the quote to the exact event frozen in the feature source.
            features = json.loads(Path(p["player_features_ref"]["path"]).read_text())
            for quote in ("dk_quote", "dk_opposite_quote"):
                base[quote]["event_start_utc"] = features["event_start_utc"]
            p["markets"] = [base]
            out = run_from_manifest(p)
            self.assertEqual(out["submitted_candidates"], 1)
            self.assertEqual(out["rows"][0]["research_state"], "PAPER_0U")
            self.assertEqual(out["rows"][0]["guard_state"], "BLOCK")
            self.assertEqual(out["approved_stake_u"], 0)

    def test_tampered_private_feature_bytes_are_blocked(self):
        with TemporaryDirectory() as d:
            p, f, path = _nfl_setup(d)
            f["players"][0]["rate_per_opportunity"] = 1000
            path.write_text(json.dumps(f))
            with self.assertRaisesRegex(ValueError, "ORIGINAL_BYTES_HASH_MISMATCH"):
                run_from_manifest(p)

    def test_both_player_sources_are_not_allowed(self):
        with TemporaryDirectory() as d:
            p, _, _ = _nfl_setup(d)
            p["player_file"] = {"path": "/private/forbidden.csv"}
            with self.assertRaisesRegex(ValueError, "ONLY_ONE_PLAYER_FORECAST_SOURCE"):
                run_from_manifest(p)

    def test_player_features_require_own_direct_team_projection(self):
        with TemporaryDirectory() as d:
            p, _, _ = _nfl_setup(d)
            p["projection"] = manifest()["projection"]
            del p["projection_ref"]
            with self.assertRaisesRegex(ValueError, "PLAYER_FEATURES_REQUIRE_DIRECT_OWN_TEAM_MODEL"):
                run_from_manifest(p)

    def test_team_or_event_mismatch_fails_closed(self):
        with TemporaryDirectory() as d:
            p, f, path = _nfl_setup(d)
            f["home_id"] = "WrongTeam"
            _update_features(p, path, f)
            with self.assertRaisesRegex(ValueError, "MODEL_EVENT_TEAM_MISMATCH"):
                run_from_manifest(p)

    def test_roster_census_mismatch_fails_closed(self):
        with TemporaryDirectory() as d:
            p, f, path = _nfl_setup(d)
            f["frozen_roster"].pop("WR-1")
            _update_features(p, path, f)
            with self.assertRaisesRegex(ValueError, "FROZEN_ROSTER_CENSUS_MISMATCH"):
                run_from_manifest(p)

    def test_future_publication_fails_closed(self):
        with TemporaryDirectory() as d:
            p, f, path = _nfl_setup(d)
            f["source_published_utc"] = (
                datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            _update_features(p, path, f)
            with self.assertRaisesRegex(ValueError, "LOOKAHEAD_OR_SOURCE_CLOCK"):
                run_from_manifest(p)

    def test_extra_odds_feature_fails_closed(self):
        with TemporaryDirectory() as d:
            p, f, path = _nfl_setup(d)
            f["players"][0]["sportsbook_line"] = 235.5
            _update_features(p, path, f)
            with self.assertRaisesRegex(ValueError, "ODDS_FEATURE"):
                run_from_manifest(p)

    def test_inactive_and_unsupported_stats_are_visible_no_moments_block(self):
        with TemporaryDirectory() as d:
            p, f, path = _nfl_setup(d)
            f["players"][0]["confirmed_active"] = False
            f["players"][1]["stat"] = "LONGEST_RECEPTION"
            _update_features(p, path, f)
            with self.assertRaisesRegex(ValueError, "NO_ADMISSIBLE_INDEPENDENT_MOMENTS"):
                run_from_manifest(p)


if __name__ == "__main__":
    unittest.main()
