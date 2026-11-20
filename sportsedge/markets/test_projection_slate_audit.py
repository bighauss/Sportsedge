"""Synthetic RUN IT projection overlay tests; never real bookmaker/model evidence."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from sportsedge.markets.slate_orchestrator import run_slate
from sportsedge.markets.test_slate_orchestrator import fixture

HASH = "sha256:" + "a" * 64


def make_receipt(source_slate, priced_slate):
    event = next(e for e in priced_slate["events"] if e["sport"] == "CBB")
    market = next(r["market"] for r in event["research_rows"] if len(r["market"]) == 10)
    freeze = datetime.fromisoformat(
        source_slate["event_inputs"][0]["manifest"]["projection"]["asof_utc"])
    generated = freeze + timedelta(seconds=1)
    published = freeze - timedelta(seconds=60)
    return {
        "market_identity": list(market),
        "forecast": {
            "origin": "SPORTSEDGE_INDEPENDENT",
            "model_sha256": event["research_model_sha256"],
            "feature_sha256": event["research_feature_sha256"],
            "distribution_sha256": HASH,
            "feature_frozen_utc": freeze.isoformat(),
            "generated_utc": generated.isoformat(),
            "event_start_utc": event["start_utc"],
            "feature_sources": [{
                "kind": "PLAY_BY_PLAY",
                "sha256": HASH,
                "published_utc": published.isoformat(),
            }],
            "p_win": 0.56,
            "p_push": 0.01,
            "projected_mean": 143.2,
        },
    }


class TestSlateProjectionOverlay(unittest.TestCase):
    def test_missing_independent_receipt_blocks_each_research_model_claim(self):
        out = run_slate(fixture())
        event = next(e for e in out["events"] if e["sport"] == "CBB")
        self.assertEqual(event["research_priced"], 1)  # existing PAPER pricer, unchanged
        self.assertEqual(event["research_rows"][0]["independent_projection"]["status"], "BLOCK")
        self.assertEqual(event["research_rows"][0]["independent_projection"]["reasons"],
                         ["NO_INDEPENDENT_PROJECTION_RECEIPT"])
        self.assertFalse(event["research_rows"][0]["verified_model_ev"])
        self.assertEqual(out["independent_projection_coverage"]["blocked"], 1)
        self.assertEqual(out["independent_projection_coverage"]["valid_shape_unverified"], 0)
        self.assertEqual((out["official_counted"], out["approved_stake_u"]), (0, 0))

    def test_matching_frozen_model_is_only_shape_accepted_not_certified(self):
        f = fixture()
        baseline = run_slate(f)
        f["projection_evidence"] = [make_receipt(f, baseline)]
        out = run_slate(f)
        event = next(e for e in out["events"] if e["sport"] == "CBB")
        verdict = event["research_rows"][0]["independent_projection"]
        self.assertEqual(verdict["status"], "PAPER_0U_MODEL_PROJECTION_UNVERIFIED")
        self.assertTrue(verdict["research_projection_usable"])
        self.assertFalse(verdict["source_authenticated"])
        self.assertFalse(verdict["calibration_verified"])
        self.assertFalse(verdict["positive_ev_verified"])
        self.assertFalse(event["research_rows"][0]["verified_model_ev"])
        self.assertEqual(out["independent_projection_coverage"]["receipts_matched"], 1)
        self.assertEqual(out["independent_projection_coverage"]["valid_shape_unverified"], 1)
        self.assertEqual(out["independent_projection_coverage"]["verified_model_ev_count"], 0)

    def test_market_anchor_never_becomes_own_independent_forecast(self):
        f = fixture()
        row = make_receipt(f, run_slate(f))
        row["forecast"]["origin"] = "MARKET_ANCHOR"
        f["projection_evidence"] = [row]
        verdict = run_slate(f)["events"][0]["research_rows"][0]["independent_projection"]
        self.assertIn("SPORTSBOOK_ANCHOR_NOT_INDEPENDENT", verdict["reasons"])

    def test_wrong_model_feature_hash_and_future_publication_rejected(self):
        f = fixture()
        row = make_receipt(f, run_slate(f))
        row["forecast"]["model_sha256"] = "sha256:" + "f" * 64
        f["projection_evidence"] = [row]
        verdict = run_slate(f)["events"][0]["research_rows"][0]["independent_projection"]
        self.assertIn("PROJECTION_RECEIPT_NOT_BOUND_TO_PRICED_MODEL", verdict["reasons"])
        row = make_receipt(f, run_slate(f))
        row["forecast"]["feature_sources"][0]["published_utc"] = row["forecast"]["event_start_utc"]
        f["projection_evidence"] = [row]
        verdict = run_slate(f)["events"][0]["research_rows"][0]["independent_projection"]
        self.assertIn("FEATURE_PUBLISHED_AFTER_MODEL_FREEZE", verdict["reasons"])

    def test_event_clock_and_result_generation_identity_are_required(self):
        f = fixture()
        row = make_receipt(f, run_slate(f))
        row["forecast"]["event_start_utc"] = "2026-11-18T01:00:00Z"
        f["projection_evidence"] = [row]
        verdict = run_slate(f)["events"][0]["research_rows"][0]["independent_projection"]
        self.assertIn("PROJECTION_RECEIPT_GAME_OR_RUN_CLOCK_MISMATCH", verdict["reasons"])

    def test_unmatched_and_duplicate_receipts_refused(self):
        f = fixture()
        row = make_receipt(f, run_slate(f))
        f["projection_evidence"] = [deepcopy(row), deepcopy(row)]
        with self.assertRaisesRegex(ValueError, "PROJECTION_EVIDENCE_DUPLICATE_MARKET"):
            run_slate(f)
        row = deepcopy(row)
        row["market_identity"][1] = "OTHER-EVENT"
        f["projection_evidence"] = [row]
        with self.assertRaisesRegex(ValueError, "PROJECTION_EVIDENCE_NOT_IN_SUBMITTED_MARKET_CENSUS"):
            run_slate(f)

    def test_sgp_placeholder_kept_blocked_and_counted(self):
        f = fixture()
        f["event_inputs"][0]["manifest"]["markets"].append({
            "market": {"sport": "CBB", "event_id": "GAME-1",
                       "kind": "SGP", "period": "FG"}})
        out = run_slate(f)
        event = next(e for e in out["events"] if e["sport"] == "CBB")
        self.assertEqual(len(event["research_rows"]), 2)
        self.assertEqual(out["independent_projection_coverage"]["submitted_research_rows"], 2)
        self.assertEqual(out["independent_projection_coverage"]["blocked"], 2)
        self.assertIn("SGP_INVENTORY_ONLY_NO_POSTED_LEGS",
                      event["research_rows"][1]["independent_projection"]["reasons"])
        self.assertEqual(event["research_rows"][1]["approved_stake_u"], 0)

    def test_secret_fields_not_accepted_and_no_research_price_promotion(self):
        f = fixture()
        f["projection_evidence"] = [{
            **make_receipt(f, run_slate(f)), "api_token": "do-not-accept"
        }]
        with self.assertRaisesRegex(ValueError, "PROJECTION_EVIDENCE_FIELDS_INVALID"):
            run_slate(f)
        f["projection_evidence"] = []
        out = run_slate(f)
        self.assertEqual(out["counts"]["priced_research"], 1)
        self.assertEqual(out["independent_projection_coverage"]["verified_model_ev_count"], 0)
        self.assertIsNone(out["card"])


    def test_three_sport_five_family_matrix_does_not_hallucinate_missing_projections(self):
        out = run_slate(fixture())
        matrix = out["cbb_cfb_nfl_projection_matrix"]
        self.assertEqual(set(matrix), {"CBB", "CFB", "NFL"})
        cbb = matrix["CBB"]["families"]
        self.assertEqual(set(cbb), {"ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP"})
        self.assertEqual(cbb["TOTAL"]["submitted_candidates"], 1)
        self.assertEqual(cbb["TOTAL"]["valid_model_receipt_shape_unverified"], 0)
        self.assertEqual(cbb["TOTAL"]["status"],
                         "BLOCK_MISSING_OR_INVALID_INDEPENDENT_MODEL_RECEIPTS")
        self.assertEqual(cbb["PLAYER_PROP"]["status"],
                         "MARKET_NOT_SUBMITTED_OFFERING_UNVERIFIED")
        self.assertEqual(matrix["NFL"]["families"]["TEAM_TOTAL"]["status"],
                         "MARKET_NOT_SUBMITTED_OFFERING_UNVERIFIED")
        self.assertEqual(matrix["CFB"]["families"]["SPREAD"]["status"],
                         "NO_SCHEDULED_EVENTS_SUPPLIED")
        self.assertFalse(matrix["CBB"]["all_market_families_verified"])
        self.assertEqual(out["approved_stake_u"], 0)

    def test_three_sport_matrix_valid_receipt_is_still_paper_not_market_complete(self):
        f = fixture()
        f["projection_evidence"] = [make_receipt(f, run_slate(f))]
        out = run_slate(f)
        cbb = out["cbb_cfb_nfl_projection_matrix"]["CBB"]["families"]
        self.assertEqual(cbb["TOTAL"]["valid_model_receipt_shape_unverified"], 1)
        self.assertEqual(cbb["TOTAL"]["status"], "PAPER_MODEL_RECEIPT_SHAPE_ONLY")
        self.assertFalse(cbb["TOTAL"]["source_authenticated"])
        self.assertFalse(cbb["TOTAL"]["calibration_verified"])
        self.assertEqual(cbb["PLAYER_PROP"]["valid_model_receipt_shape_unverified"], 0)
        self.assertEqual(out["independent_projection_coverage"]["verified_model_ev_count"], 0)



if __name__ == "__main__":
    unittest.main()
