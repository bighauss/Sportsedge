import hashlib
import json
import unittest
from cbb_delivery_audit import delivery_audit, fit_prior_residuals


def card(**over):
    row = {"game_id": "g", "period": "FG", "market": "ML", "side": "away",
           "captured_utc": "2026-11-25T22:35:00Z",
           "provenance": "AUTHENTICATED_DK_CAPTURE",
           "hybrid_method": "LOGIT_BLEND_CHALLENGER_W0.125_VALIDATION_SELECTED_OPEN",
           "ev_hybrid": 0.01, **over}
    c = {"freeze_utc": "2026-11-25T22:40:00Z", "projection_adapter": "frozen_native_cbbd",
         "games": [{"game_id": "g", "tipoff_utc": "2026-11-26T00:00:00Z"}],
         "priced": [row]}
    c["card_sha256"] = hashlib.sha256(json.dumps(c, sort_keys=True, separators=(",", ":"),
                                                allow_nan=False).encode()).hexdigest()
    return c


def residual(gid, error, final="2026-11-24T22:00:00Z"):
    return {"game_id": gid, "forecast_observed_utc": "2026-11-24T18:00:00Z",
            "tip_utc": "2026-11-24T19:00:00Z", "final_observed_utc": final,
            "predicted_margin": 2, "actual_margin": 2 + error,
            "predicted_total": 140, "actual_total": 140 + 2 * error}


class DeliveryAudit(unittest.TestCase):
    def test_fresh_still_never_released(self):
        result = delivery_audit(card(), "2026-11-25T22:49:00Z")
        self.assertEqual(result["rows"][0]["status"], "RESEARCH_ONLY")
        self.assertEqual(result["released"], 0)

    def test_stale_at_delivery_not_at_freeze(self):
        result = delivery_audit(card(), "2026-11-25T23:00:00Z")
        self.assertIn("STALE_AT_DELIVERY", result["rows"][0]["reasons"])

    def test_evening_half_quote_and_ev_floor(self):
        result = delivery_audit(card(period="1H", ev_hybrid=0.005,
                                    captured_utc="2026-11-25T12:35:00Z",
                                    provenance="UNAUTHENTICATED_PDF"), "2026-11-25T22:49:00Z")
        self.assertTrue({"STALE_AT_DELIVERY", "ODDS_UNAUTHENTICATED", "BELOW_EV_FLOOR",
                         "HALF_BLEND_UNVALIDATED", "HALF_ML_SETTLEMENT_UNVERIFIED"}
                        <= set(result["rows"][0]["reasons"]))

    def test_started_at_exact_tip(self):
        self.assertIn("GAME_STARTED", delivery_audit(card(), "2026-11-26T00:00:00Z")["rows"][0]["reasons"])

    def test_future_quote(self):
        self.assertIn("QUOTE_AFTER_FREEZE", delivery_audit(card(captured_utc="2026-11-25T22:45:00Z"),
                      "2026-11-25T22:49:00Z")["rows"][0]["reasons"])

    def test_tampered_card(self):
        c = card()
        c["priced"][0]["ev_hybrid"] = 0.9
        with self.assertRaisesRegex(ValueError, "CARD_DIGEST_MISMATCH"):
            delivery_audit(c, "2026-11-25T22:49:00Z")

    def test_residual_cutoff_and_bias(self):
        records = [residual("a", -2), residual("b", 4), residual("future", 1000, "2026-11-26T22:00:00Z")]
        out = fit_prior_residuals(records, "2026-11-25T00:00:00Z", min_games=2)
        self.assertEqual(out["n"], 2)
        self.assertEqual(out["metrics"]["margin"]["bias_actual_minus_model"], 1)
        self.assertAlmostEqual(out["metrics"]["margin"]["sd"], 18 ** 0.5)

    def test_residual_requires_prior_forecast(self):
        r = residual("a", 0)
        r["forecast_observed_utc"] = r["tip_utc"]
        with self.assertRaisesRegex(ValueError, "RESIDUAL_CLOCK_INVALID"):
            fit_prior_residuals([r], "2026-11-25T00:00:00Z")

    def test_residual_sample_hold_and_duplicates(self):
        r = residual("a", 1)
        self.assertEqual(fit_prior_residuals([r], "2026-11-25T00:00:00Z")["status"],
                         "HOLD_INSUFFICIENT_PRIOR_RESIDUALS")
        with self.assertRaisesRegex(ValueError, "DUPLICATE_RESIDUAL_GAME"):
            fit_prior_residuals([r, r], "2026-11-25T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
