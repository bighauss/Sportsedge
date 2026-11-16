"""Research-only empirical discrete NFL scoring regression tests."""
from copy import deepcopy
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
import unittest

from discrete_score_pit import score_distribution, main
from score_walkforward_pit import REPO_ROOT

SHA = "sha256:" + "b" * 64


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def fixtures(n=60):
    kickoff = datetime(2026, 12, 1, 21, tzinfo=timezone.utc)
    target = {
        "game_id": "target", "home_id": "CHI", "away_id": "GB",
        "kickoff_utc": iso(kickoff),
        "forecast_asof_utc": iso(kickoff - timedelta(hours=3)),
        "source_observed_utc": iso(kickoff - timedelta(hours=4)),
        "model_sha256": SHA, "projected_home": 20.0, "projected_away": 20.0,
    }
    outcomes = [(24,21), (27,20), (21,21), (17,24)]
    history = []
    for i in range(n):
        past_start = kickoff - timedelta(days=2 + i)
        home, away = outcomes[i%4]
        history.append({
            "game_id": f"old_{i}", "home_id": "CHI", "away_id": "GB",
            "kickoff_utc": iso(past_start),
            "forecast_asof_utc": iso(past_start - timedelta(hours=3)),
            "source_observed_utc": iso(past_start - timedelta(hours=4)),
            "model_sha256": SHA,
            "projected_home": 20.0, "projected_away": 20.0,
            "final_utc": iso(past_start + timedelta(hours=4)),
            "result_available_utc": iso(past_start + timedelta(hours=6)),
            "final_home": home, "final_away": away,
        })
    lines = {
        "game_id": "target",
        "observed_at_utc": iso(kickoff - timedelta(hours=4)),
        "home_spread": -3.0,
        "game_total": 45.0,
        "home_team_total": 24.0,
        "away_team_total": 21.0,
    }
    return target, history, lines


class DiscreteNFLPITTests(unittest.TestCase):
    def test_exact_margin_key_numbers_and_tie_mass(self):
        target, hist, lines = fixtures()
        out = score_distribution(target, hist, lines=lines)
        self.assertEqual(out["status"], "PAPER_HOLD_0U")
        self.assertEqual(out["approved_stake_u"], 0)
        self.assertEqual(out["census"]["eligible_prior_residual_pairs"], 60)
        self.assertEqual(out["score_diagnostics"]["margin_3_frequency"], .25)
        self.assertEqual(out["score_diagnostics"]["margin_7_frequency"], .25)
        self.assertEqual(out["score_diagnostics"]["abs_margin_3_frequency"], .25)
        self.assertEqual(out["score_diagnostics"]["abs_margin_7_frequency"], .5)
        self.assertEqual(out["markets"]["MONEYLINE"]["home_win"], .5)
        self.assertEqual(out["markets"]["MONEYLINE"]["tie"], .25)
        self.assertEqual(out["markets"]["MONEYLINE"]["away_win"], .25)
        self.assertEqual(out["markets"]["MONEYLINE"]["settlement_rule"],
                         "3_WAY_RESULTS_ONLY_NO_2_WAY_TIE_ASSUME")

    def test_push_aware_spread_total_and_team_totals(self):
        target, hist, lines = fixtures()
        out = score_distribution(target, hist, lines=lines)
        spread = out["markets"]["SPREAD"]
        self.assertEqual(spread["line"], -3)
        self.assertEqual(spread["over_or_home_cover"], .25)
        self.assertEqual(spread["push"], .25)
        self.assertEqual(spread["under_or_away_cover"], .5)
        total = out["markets"]["GAME_TOTAL"]
        self.assertEqual(total["line"], 45)
        self.assertEqual((total["over_or_home_cover"], total["push"],
                          total["under_or_away_cover"]), (.25, .25, .5))
        self.assertEqual(out["markets"]["HOME_TEAM_TOTAL"]["push"], .25)
        self.assertEqual(out["markets"]["AWAY_TEAM_TOTAL"]["push"], .5)

    def test_missing_market_lines_are_not_claimed_not_offered(self):
        t,h,_ = fixtures()
        out = score_distribution(t,h)
        self.assertEqual(out["markets"]["SPREAD"]["status"], "NOT_CAPTURED")
        self.assertEqual(out["markets"]["GAME_TOTAL"]["status"], "NOT_CAPTURED")
        self.assertIn("FIRST_TD", out["markets"])
        self.assertEqual(out["markets"]["FIRST_TD"]["status"], "NO_MODEL")
        self.assertNotIn("expected_value", out)

    def test_future_results_do_not_enter_past_prediction(self):
        target, history, lines = fixtures()
        original = score_distribution(target, history, lines=lines)
        later = deepcopy(history[0])
        later["game_id"] = "future_heldout"
        later["kickoff_utc"] = "2026-12-02T20:00:00Z"
        later["forecast_asof_utc"] = "2026-12-02T18:00:00Z"
        later["source_observed_utc"] = "2026-12-02T17:00:00Z"
        later["final_utc"] = "2026-12-03T00:00:00Z"
        later["result_available_utc"] = "2026-12-03T02:00:00Z"
        later["final_home"], later["final_away"] = 100, 0
        modified = score_distribution(target, history + [later], lines=lines)
        self.assertEqual(original["markets"], modified["markets"])
        self.assertEqual(modified["census"]["excluded_outcome_unavailable_at_forecast"], 1)

    def test_late_report_is_excluded_even_for_earlier_game(self):
        t,h,l = fixtures()
        original = score_distribution(t,h,lines=l)
        h[0]["result_available_utc"] = "2026-12-03T02:00:00Z"
        alt = score_distribution(t,h,lines=l)
        self.assertEqual(alt["census"]["eligible_prior_residual_pairs"], 59)
        self.assertNotEqual(original["markets"]["MONEYLINE"]["home_win"],
                            alt["markets"]["MONEYLINE"]["home_win"])

    def test_version_changes_not_mixed_in_pool(self):
        t,h,l = fixtures()
        h[0]["model_sha256"] = "sha256:" + "c"*64
        out = score_distribution(t,h,lines=l)
        self.assertEqual(out["census"]["excluded_different_model_version"], 1)
        self.assertEqual(out["census"]["eligible_prior_residual_pairs"], 59)

    def test_history_below_threshold_yields_no_numbers(self):
        t,h,l = fixtures(31)
        out = score_distribution(t,h,lines=l,min_history=50)
        self.assertNotIn("score_diagnostics", out)
        self.assertEqual(out["markets"]["MONEYLINE"]["status"], "NO_MODEL")
        self.assertEqual(out["markets"]["SPREAD"]["status"], "NO_MODEL")

    def test_duplicate_or_self_event_blocks_instead_of_counting_twice(self):
        t,h,l = fixtures()
        with self.assertRaisesRegex(ValueError, "SELF_EVENT_OR_DUPLICATE"):
            score_distribution(t,h+[deepcopy(h[0])],lines=l)
        h[0]["game_id"] = t["game_id"]
        with self.assertRaisesRegex(ValueError, "SELF_EVENT_OR_DUPLICATE"):
            score_distribution(t,h,lines=l)

    def test_frozen_forecast_after_game_start_rejected(self):
        t,h,l = fixtures()
        t["forecast_asof_utc"] = t["kickoff_utc"]
        with self.assertRaisesRegex(ValueError, "FROZEN_FORECAST_AFTER"):
            score_distribution(t,h,lines=l)

    def test_late_or_cross_event_market_line_rejected(self):
        t,h,l = fixtures()
        l["observed_at_utc"] = t["kickoff_utc"]
        with self.assertRaisesRegex(ValueError, "MARKET_LINES_AFTER"):
            score_distribution(t,h,lines=l)
        l["observed_at_utc"] = t["source_observed_utc"]
        l["game_id"] = "different"
        with self.assertRaisesRegex(ValueError, "MARKET_EVENT_ID_MISMATCH"):
            score_distribution(t,h,lines=l)

    def test_missing_or_invalid_score_and_nonfinite_forecast(self):
        t,h,l = fixtures()
        h[0]["final_home"] = "24"
        with self.assertRaisesRegex(ValueError, "INVALID_FINAL_SCORE"):
            score_distribution(t,h,lines=l)
        t,h,l=fixtures()
        t["projected_home"] = float("nan")
        with self.assertRaisesRegex(ValueError, "NONFINITE_NUMERIC"):
            score_distribution(t,h,lines=l)

    def test_result_chronology_required(self):
        t,h,l = fixtures()
        h[0]["final_utc"] = h[0]["kickoff_utc"]
        with self.assertRaisesRegex(ValueError, "POSTGAME_OUTCOME_TIME_ORDER"):
            score_distribution(t,h,lines=l)

    def test_no_zero_fill_for_missing_history_field(self):
        t,h,l = fixtures()
        h[0].pop("final_away")
        with self.assertRaisesRegex(ValueError, "BAD_HISTORICAL_FORECAST_SCHEMA"):
            score_distribution(t,h,lines=l)

    def test_min_history_threshold_and_line_bound(self):
        t,h,l = fixtures()
        with self.assertRaisesRegex(ValueError, "MINIMUM_RESIDUAL_HISTORY"):
            score_distribution(t,h,lines=l,min_history=20)
        l["game_total"] = 999
        with self.assertRaisesRegex(ValueError, "MARKET_LINE_OUT_OF_REASONABLE_RANGE"):
            score_distribution(t,h,lines=l)

    def test_false_production_claims_not_present(self):
        t,h,l = fixtures()
        out = score_distribution(t,h,lines=l)
        self.assertEqual(out["official_counted"], 0)
        self.assertEqual(out["source_authentication"], "NOT_INDEPENDENTLY_ATTESTED")
        self.assertEqual(out["calibration"], "UNVERIFIED_EMPIRICAL_RESIDUALS")
        self.assertFalse(out["markets"]["SPREAD"]["source_authentication"])


class DiscreteScorePrivateArchiveTests(unittest.TestCase):
    """CLI tests never need provider network access or real game data."""

    def _fixture_files(self, temp):
        t, h, l = fixtures()
        paths = {
            "target": Path(temp) / "target.json",
            "history": Path(temp) / "history.json",
            "lines": Path(temp) / "lines.json",
            "out": Path(temp) / "research.json",
        }
        for key, item in (("target", t), ("history", h), ("lines", l)):
            paths[key].write_text(json.dumps(item), encoding="utf-8")
        return paths

    def _run(self, files, *, overrides=None):
        args = [
            "discrete_score_pit.py",
            "--target", str(files["target"]),
            "--history", str(files["history"]),
            "--lines", str(files["lines"]),
            "--out", str(files["out"]),
        ]
        for flag, value in (overrides or {}).items():
            args[args.index("--" + flag) + 1] = str(value)
        with patch.object(sys, "argv", args), redirect_stdout(StringIO()):
            main()

    def test_private_create_only_mode_0600_and_exact_source_hashes(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-dscore-") as tmp:
            files = self._fixture_files(tmp)
            self._run(files)
            self.assertEqual(stat.S_IMODE(files["out"].stat().st_mode), 0o600)
            decoded = json.loads(files["out"].read_bytes())
            self.assertEqual(decoded["status"], "PAPER_HOLD_0U")
            self.assertEqual(decoded["approved_stake_u"], 0)
            for key in ("target", "history", "lines"):
                actual = "sha256:" + sha256(files[key].read_bytes()).hexdigest()
                self.assertEqual(decoded["local_input_sha256"][key], actual)
            original = files["out"].read_bytes()
            with self.assertRaises(FileExistsError):
                self._run(files)
            self.assertEqual(original, files["out"].read_bytes())

    def test_all_three_raw_inputs_reject_nested_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-dscore-") as tmp:
            files = self._fixture_files(tmp)
            samples = {
                "target": b'{"x":{"z":1,"z":2}}',
                "history": b'[{"nested":{"q":1,"q":2}}]',
                "lines": b'{"x": 1,"x": 2}',
            }
            for key, raw in samples.items():
                with self.subTest(file=key):
                    backups = {k: files[k].read_bytes()
                               for k in ("target", "history", "lines")}
                    files[key].write_bytes(raw)
                    with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
                        self._run(files)
                    self.assertFalse(files["out"].exists())
                    for k, value in backups.items():
                        files[k].write_bytes(value)

    def test_nonfinite_literal_rejected_before_forecast_scoring(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-dscore-") as tmp:
            files = self._fixture_files(tmp)
            payload = files["target"].read_bytes().replace(
                b'"projected_home": 20.0', b'"projected_home": NaN'
            )
            files["target"].write_bytes(payload)
            with self.assertRaisesRegex(ValueError, "NONFINITE_JSON_LITERAL"):
                self._run(files)
            self.assertFalse(files["out"].exists())

    def test_reject_checkout_lexical_source_and_output_before_read(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-dscore-") as tmp:
            files = self._fixture_files(tmp)
            forbidden = REPO_ROOT / "forbidden_internal_private.json"
            with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
                self._run(files, overrides={"out": forbidden})
            with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
                self._run(files, overrides={"history": forbidden})
            self.assertFalse(files["out"].exists())

    def test_reject_checkout_symlink_alias_to_external_private_file(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-dscore-") as tmp:
            files = self._fixture_files(tmp)
            # Even if target resolves outside checkout, the lexical alias
            # used by the process would be publicly reachable from Git.
            alias = REPO_ROOT / "models" / "nfl" / "test_private_discrete_alias.json"
            try:
                alias.symlink_to(files["target"])
                with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
                    self._run(files, overrides={"target": alias})
            finally:
                alias.unlink(missing_ok=True)
            self.assertFalse(files["out"].exists())

    def test_existing_output_symlink_rejected_and_target_not_modified(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-dscore-") as tmp:
            files = self._fixture_files(tmp)
            protected = Path(tmp) / "protected_existing.json"
            protected.write_bytes(b"DO_NOT_CHANGE")
            files["out"].symlink_to(protected)
            with self.assertRaisesRegex(ValueError, "PRIVATE_OUTPUT_SYMLINK_REFUSED"):
                self._run(files)
            self.assertEqual(protected.read_bytes(), b"DO_NOT_CHANGE")

    def test_partial_output_removed_on_fsync_failure(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-dscore-") as tmp:
            files = self._fixture_files(tmp)
            with patch("score_walkforward_pit.os.fsync",
                       side_effect=OSError("synthetic-fsync-fail")):
                with self.assertRaisesRegex(OSError, "synthetic-fsync-fail"):
                    self._run(files)
            self.assertFalse(files["out"].exists())

    def test_key_numbers_both_margin_signs(self):
        t, h, l = fixtures()
        h[0]["final_home"] = 21
        h[0]["final_away"] = 24
        out = score_distribution(t, h, lines=l)
        self.assertEqual(out["score_diagnostics"]["margin_3_frequency"], round(14/60, 8))
        self.assertEqual(out["score_diagnostics"]["abs_margin_3_frequency"], .25)
        self.assertEqual(out["score_diagnostics"]["abs_margin_7_frequency"], .5)
        self.assertEqual(out["approved_stake_u"], 0)


    def test_extreme_json_exponent_rejected_before_schema_validation(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-dscore-") as tmp:
            files = self._fixture_files(tmp)
            original = files["target"].read_bytes()
            files["target"].write_bytes(b'{"unused":{"nested":1e9999}}')
            with self.assertRaisesRegex(ValueError,
                                        "NONFINITE_JSON_NUMBER_OVERFLOW"):
                self._run(files)
            self.assertFalse(files["out"].exists())
            self.assertNotEqual(original, files["target"].read_bytes())

    def test_extreme_numeric_exponent_in_market_line_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-dscore-") as tmp:
            files = self._fixture_files(tmp)
            raw = files["lines"].read_bytes()
            self.assertIn(b'"home_spread": -3.0', raw)
            files["lines"].write_bytes(
                raw.replace(b'"home_spread": -3.0', b'"home_spread": 1e9999'))
            with self.assertRaisesRegex(ValueError,
                                        "NONFINITE_JSON_NUMBER_OVERFLOW"):
                self._run(files)
            self.assertFalse(files["out"].exists())

    def test_source_size_limit_and_empty_file_are_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-dscore-") as tmp:
            files = self._fixture_files(tmp)
            with patch("discrete_score_pit.MAX_ORIGINAL_JSON_BYTES", 100):
                with self.assertRaisesRegex(ValueError,
                                            "ORIGINAL_JSON_EMPTY_OR_OVERSIZE"):
                    self._run(files)
            files["lines"].write_bytes(b"")
            with self.assertRaisesRegex(ValueError,
                                        "ORIGINAL_JSON_EMPTY_OR_OVERSIZE"):
                self._run(files)
            self.assertFalse(files["out"].exists())


if __name__=="__main__":
    unittest.main()
