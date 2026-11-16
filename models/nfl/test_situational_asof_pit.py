"""NFL point-in-time situation input guards, synthetic only."""
from copy import deepcopy
import unittest

from situational_asof_pit import situational_census

HASH = "sha256:" + "c"*64


def receipt():
    return {
        "source_id": "SYNTHETIC_PROVIDER",
        "source_observed_utc": "2026-11-15T16:00:00Z",
        "captured_at_utc": "2026-11-15T17:00:00Z",
        "original_bytes_sha256": HASH,
    }


def fixture():
    event = {
        "event_id": "2026_GB_CHI",
        "home_id": "CHI",
        "away_id": "GB",
        "kickoff_utc": "2026-11-15T21:00:00Z",
        "freeze_utc": "2026-11-15T18:00:00Z",
    }
    roster = {
        "event_id": event["event_id"],
        "home_qb_gsis_id": "00-0033873",
        "away_qb_gsis_id": "00-0034444",
        "home_qb_status": "CONFIRMED",
        "away_qb_status": "CONFIRMED",
        "official_inactives_received": True,
        "receipt": receipt(),
    }
    rest = {
        "event_id": event["event_id"],
        "home_rest_days": 7,
        "away_rest_days": 6,
        "away_travel_km": 315,
        "away_time_zones_crossed": 0,
        "receipt": receipt(),
    }
    weather = {
        "event_id": event["event_id"],
        "roof_state": "OPEN_AIR",
        "forecast_valid_from_utc": "2026-11-15T20:00:00Z",
        "forecast_valid_until_utc": "2026-11-15T22:00:00Z",
        "wind_mph": 17.5,
        "temperature_f": 43.0,
        "precip_probability": 0.25,
        "receipt": receipt(),
    }
    return event,roster,rest,weather


def run(e=None,r=None,s=None,w=None):
    original=fixture()
    return situational_census(
        original[0] if e is None else e,
        roster=original[1] if r is None else r,
        rest=original[2] if s is None else s,
        weather=original[3] if w is None else w,
    )


class NFLAsOfSituationalTests(unittest.TestCase):
    def test_all_claimed_present_still_paper(self):
        x=run()
        self.assertTrue(x["claimed_inputs_complete"])
        self.assertTrue(x["weather_applies_to_score_model"])
        self.assertEqual(x["wind_mph_if_applicable"],17.5)
        self.assertFalse(x["independent_authentication"])
        self.assertEqual(x["approved_stake_u"],0)
        self.assertIsNone(x["projected_score_adjustment"])
        self.assertIsNone(x["fitted_situational_coefficients"])
        self.assertFalse(x["source_receipts"]["roster"]["independently_authenticated"])

    def test_future_roster_or_weather_cannot_be_used(self):
        e,r,s,w=fixture()
        r["receipt"]["captured_at_utc"]="2026-11-15T19:00:00Z"
        with self.assertRaisesRegex(ValueError,"SOURCE_NOT_AVAILABLE_AT_FORECAST"):
            run(e,r,s,w)
        e,r,s,w=fixture()
        w["receipt"]["source_observed_utc"]="2026-11-15T19:00:00Z"
        with self.assertRaisesRegex(ValueError,"SOURCE_NOT_AVAILABLE_AT_FORECAST"):
            run(e,r,s,w)

    def test_forecast_after_kickoff_refused(self):
        e,r,s,w=fixture()
        e["freeze_utc"]=e["kickoff_utc"]
        with self.assertRaisesRegex(ValueError,"MODEL_FREEZE_NOT_PREGAME"):
            run(e,r,s,w)

    def test_qb_injury_uncertainty_is_explicit_hold(self):
        e,r,s,w=fixture()
        r["away_qb_status"]="EXPECTED"
        r["official_inactives_received"]=False
        x=run(e,r,s,w)
        self.assertFalse(x["claimed_inputs_complete"])
        self.assertIn("AWAY_QB_NOT_CONFIRMED",x["issues"])
        self.assertIn("OFFICIAL_INACTIVES_NOT_CONFIRMED",x["issues"])
        self.assertEqual(x["approved_stake_u"],0)

    def test_no_fuzzy_qb_identity_or_fake_confirmed_qb(self):
        e,r,s,w=fixture()
        r["home_qb_gsis_id"]="Quarterback John"
        with self.assertRaisesRegex(ValueError,"UNBOUND_OR_MALFORMED_QB_GSIS_ID"):
            run(e,r,s,w)
        e,r,s,w=fixture()
        r["home_qb_gsis_id"]=None
        with self.assertRaisesRegex(ValueError,"CONFIRMED_QB_WITHOUT_ID"):
            run(e,r,s,w)

    def test_roof_closed_ignores_weather_and_does_not_set_wind_zero(self):
        e,r,s,w=fixture()
        w["roof_state"]="DOME_CLOSED"
        w["wind_mph"]=None
        w["precip_probability"]=None
        w["temperature_f"]=None
        x=run(e,r,s,w)
        self.assertTrue(x["claimed_inputs_complete"])
        self.assertFalse(x["weather_applies_to_score_model"])
        self.assertIsNone(x["wind_mph_if_applicable"])

    def test_open_air_weather_missing_blocks_not_fills(self):
        e,r,s,w=fixture()
        w["wind_mph"]=None
        x=run(e,r,s,w)
        self.assertIn("OUTDOOR_WEATHER_FORECAST_INCOMPLETE",x["issues"])
        self.assertIsNone(x["wind_mph_if_applicable"])

    def test_weather_issued_at_wrong_validity_window_rejected(self):
        e,r,s,w=fixture()
        w["forecast_valid_until_utc"]="2026-11-15T20:59:00Z"
        with self.assertRaisesRegex(ValueError,"WEATHER_VALIDITY_DOES_NOT_SPAN_KICKOFF"):
            run(e,r,s,w)

    def test_mismatched_event_refused(self):
        e,r,s,w=fixture()
        s["event_id"]="other"
        with self.assertRaisesRegex(ValueError,"SITUATIONAL_EVENT_ID_MISMATCH"):
            run(e,r,s,w)

    def test_required_rest_missing_reported(self):
        e,r,s,w=fixture()
        s["away_rest_days"]=None
        x=run(e,r,s,w)
        self.assertIn("MISSING_AWAY_REST_DAYS",x["issues"])

    def test_out_of_bounds_probabilities_and_wind_are_not_clamped(self):
        e,r,s,w=fixture()
        w["precip_probability"]=1.7
        with self.assertRaisesRegex(ValueError,"OUT_OF_BOUNDS_PRECIP_PROBABILITY"):
            run(e,r,s,w)
        e,r,s,w=fixture()
        w["wind_mph"]=float("nan")
        with self.assertRaisesRegex(ValueError,"OUT_OF_BOUNDS_WIND_MPH"):
            run(e,r,s,w)

    def test_bad_receipt_hash_or_naive_timestamp_refused(self):
        e,r,s,w=fixture()
        r["receipt"]["original_bytes_sha256"]="not-a-hash"
        with self.assertRaisesRegex(ValueError,"SOURCE_RAW_SHA256_INVALID"):
            run(e,r,s,w)
        e,r,s,w=fixture()
        w["receipt"]["captured_at_utc"]="2026-11-15T17:00:00"
        with self.assertRaisesRegex(ValueError,"NAIVE_TIMESTAMP"):
            run(e,r,s,w)

    def test_unknown_roof_state_cannot_be_indoor_by_default(self):
        e,r,s,w=fixture()
        w["roof_state"]="ROOF_UNKNOWN"
        x=run(e,r,s,w)
        self.assertIn("ROOF_STATE_NOT_CONFIRMED",x["issues"])
        self.assertFalse(x["weather_applies_to_score_model"])

    def test_extra_keys_are_rejected_and_no_bookmaker_prices(self):
        e,r,s,w=fixture()
        s["dk_spread"]=-3.5
        with self.assertRaisesRegex(ValueError,"INVALID_REST_TRAVEL_SCHEMA"):
            run(e,r,s,w)

    def test_source_observation_cannot_follow_its_capture(self):
        e,r,s,w=fixture()
        w["receipt"]["source_observed_utc"]="2026-11-15T17:30:00Z"
        with self.assertRaisesRegex(ValueError,"SOURCE_NOT_AVAILABLE_AT_FORECAST"):
            run(e,r,s,w)


if __name__=="__main__":
    unittest.main()
