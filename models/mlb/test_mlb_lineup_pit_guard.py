"""Synthetic MLB source freeze checks; never official provider proof."""
import hashlib
import json
import unittest
from mlb_lineup_pit_guard import inspect_lineup_freeze, SCHEMA

def fixture():
    home = [{"slot":i,"player_id":str(1000+i),"team_id":"100"} for i in range(1,10)]
    away = [{"slot":i,"player_id":str(2000+i),"team_id":"200"} for i in range(1,10)]
    snap = {"schema":SCHEMA,"event_id":"12345",
            "event_start_utc":"2026-07-15T21:00:00Z",
            "home_team_id":"100","away_team_id":"200",
            "home_starter_id":"1011","away_starter_id":"2011",
            "home_starter_team_id":"100","away_starter_team_id":"200",
            "starters_confirmed":True,"lineups_confirmed":True,
            "home_lineup":home,"away_lineup":away}
    meta = {"schema":SCHEMA,"event_id":"12345",
            "event_start_utc":"2026-07-15T21:00:00Z",
            "forecast_asof_utc":"2026-07-15T19:00:00Z",
            "source_published_utc":"2026-07-15T18:00:00Z",
            "source_captured_utc":"2026-07-15T18:01:00Z",
            "source_id":"MLB_STATSAPI",
            "original_provider_sha256":"sha256:"+"a"*64}
    return snap,meta

def check(snap,meta):
    raw=json.dumps(snap,sort_keys=True).encode()
    return inspect_lineup_freeze(raw,dict(meta,normalized_sha256=
        "sha256:"+hashlib.sha256(raw).hexdigest()))

class MLBLineupPITTests(unittest.TestCase):
    def test_valid_structure_is_still_not_authenticated(self):
        snap,meta=fixture()
        result=check(snap,meta)
        self.assertTrue(result["lineup_structurally_complete"])
        self.assertFalse(result["source_authenticated"])
        self.assertFalse(result["projection_calibrated"])
        self.assertEqual(result["approved_stake_u"],0)

    def test_unconfirmed_lineup_or_starter_blocks(self):
        for flag in ("starters_confirmed","lineups_confirmed"):
            snap,meta=fixture()
            snap[flag]=False
            result=check(snap,meta)
            self.assertFalse(result["lineup_structurally_complete"])
            self.assertIn("MLB_PIT_NOT_CONFIRMED:"+flag,result["blocked_reasons"])

    def test_partial_lineup_and_duplicate_slots_block(self):
        snap,meta=fixture()
        snap["home_lineup"].pop()
        self.assertIn("MLB_PIT_LINEUP_NOT_NINE_BATTERS:home",
                      check(snap,meta)["blocked_reasons"])
        snap,meta=fixture()
        snap["home_lineup"][1]["slot"]=1
        self.assertIn("MLB_PIT_LINEUP_SLOT_DUPLICATE:home",
                      check(snap,meta)["blocked_reasons"])

    def test_starter_changed_or_cross_team_blocks(self):
        snap,meta=fixture()
        snap["away_starter_team_id"]="100"
        self.assertIn("MLB_PIT_STARTER_ID_OR_TEAM_INVALID:away",
                      check(snap,meta)["blocked_reasons"])
        snap,meta=fixture()
        snap["home_starter_id"]=snap["away_starter_id"]
        self.assertIn("MLB_PIT_BOTH_TEAMS_SAME_STARTER",
                      check(snap,meta)["blocked_reasons"])

    def test_player_cross_team_collision_and_team_mismatch_block(self):
        snap,meta=fixture()
        snap["away_lineup"][0]["player_id"]=snap["home_lineup"][0]["player_id"]
        self.assertIn("MLB_PIT_LINEUP_PLAYER_DUPLICATE:away",
                      check(snap,meta)["blocked_reasons"])
        snap,meta=fixture()
        snap["away_lineup"][0]["team_id"]="100"
        self.assertIn("MLB_PIT_LINEUP_PLAYER_TEAM_INVALID:away",
                      check(snap,meta)["blocked_reasons"])

    def test_future_source_or_postkickoff_prediction_fails(self):
        for field,value in (("source_published_utc","2026-07-15T19:01:00Z"),
                            ("source_captured_utc","2026-07-15T19:01:00Z"),
                            ("forecast_asof_utc","2026-07-15T21:00:00Z")):
            snap,meta=fixture()
            meta[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"MLB_PIT_FUTURE_SOURCE_OR_FORECAST"):
                check(snap,meta)

    def test_hash_mismatch_and_invalid_claim_block(self):
        snap,meta=fixture()
        meta["original_provider_sha256"]="not-a-hash"
        with self.assertRaisesRegex(ValueError,"DIGEST_INVALID"):
            check(snap,meta)
        snap,meta=fixture()
        raw=json.dumps(snap).encode()
        meta["normalized_sha256"]="sha256:"+"0"*64
        with self.assertRaisesRegex(ValueError,"BYTES_HASH_MISMATCH"):
            inspect_lineup_freeze(raw,meta)

    def test_postgame_fields_or_book_odds_cannot_enter_features(self):
        for key,value in (("final_score",5),("odds",{"ml":-110})):
            snap,meta=fixture()
            snap[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"POSTGAME_DATA"):
                check(snap,meta)

    def test_event_and_start_identity_fails_closed(self):
        snap,meta=fixture()
        snap["event_id"]="12346"
        with self.assertRaisesRegex(ValueError,"EVENT_BINDING_INVALID"):
            check(snap,meta)
        snap,meta=fixture()
        snap["event_start_utc"]="2026-07-16T21:00:00Z"
        with self.assertRaisesRegex(ValueError,"EVENT_START_CHANGED"):
            check(snap,meta)

    def test_duplicate_json_keys_and_boolean_slots_refused(self):
        snap,meta=fixture()
        raw=json.dumps(snap).encode().replace(
            b'"event_id": "12345"', b'"event_id": "12345", "event_id": "12346"')
        meta["normalized_sha256"]="sha256:"+hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
            inspect_lineup_freeze(raw,meta)
        snap,meta=fixture()
        snap["home_lineup"][0]["slot"]=True
        self.assertIn("MLB_PIT_LINEUP_SLOT_INVALID:home",
                      check(snap,meta)["blocked_reasons"])

if __name__=="__main__":
    unittest.main()
