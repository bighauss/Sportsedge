"""Offline contract checks for PIT evidence and prospective calibration."""
import json
import unittest
from datetime import datetime, timezone
from research.nfl_beta_evidence_intake import ingest
from research.nfl_beta_calibration_audit import audit

def envelope():
    model = {"event_id":"e1","model_asof_utc":"2026-11-22T13:00:00Z",
             "scenarios":[{"event_id":"e1","players":{"p":{"rec_yds":55}},
                           "ordered_touchdowns":["p"]} for _ in range(1000)]}
    quotes = {"source":"DraftKings","captured_at_utc":"2026-11-22T13:01:00Z",
              "offers":[{"event_id":"e1","quote_id":"q1","kind":"XPLUS",
                         "player_id":"p","stat":"rec_yds","threshold":50,
                         "kickoff_utc":"2026-11-22T14:00:00Z","odds_american":150}]}
    return json.dumps(quotes).encode(),json.dumps(model).encode()

class IntakeTests(unittest.TestCase):
    def test_hashes_are_computed_from_bytes(self):
        q,m=envelope()
        result=ingest(q,m,decision_utc="2026-11-22T13:02:00Z")
        self.assertEqual(result["official_bets"],0)
        self.assertEqual(result["external_authentication"],"UNVERIFIED")
        self.assertTrue(result["quote_sha256"].startswith("sha256:"))

    def test_stale_capture_rejected(self):
        q,m=envelope()
        with self.assertRaises(ValueError):
            ingest(q,m,decision_utc="2026-11-22T13:10:00Z")

    def test_conflicting_provenance_rejected(self):
        q,m=envelope()
        d=json.loads(q);d["offers"][0]["source_sha256"]="fake"
        with self.assertRaises(ValueError):
            ingest(json.dumps(d).encode(),m,decision_utc="2026-11-22T13:02:00Z")

    def test_unfrozen_calibration_rejected(self):
        with self.assertRaises(ValueError):
            audit([{"prediction_id":"a","kind":"XPLUS","status":"PAPER_HOLD_0U",
                    "stake_u":0,"beta_probability":0.5}], [{"prediction_id":"a","result":1}])

    def test_calibration_remains_unvalidated(self):
        p=[{"prediction_id":"a","kind":"XPLUS","status":"PAPER_HOLD_0U",
            "stake_u":0,"beta_probability":0.5,
            "frozen_at_utc":"2026-11-22T13:00:00Z",
            "kickoff_utc":"2026-11-22T14:00:00Z",
            "receipt_sha256":"sha256:"+"a"*64}]
        r=audit(p,[{"prediction_id":"a","result":1}])
        self.assertFalse(r["families"]["XPLUS"]["validated"])
        self.assertEqual(r["families"]["XPLUS"]["n"],1)

if __name__=="__main__":
    unittest.main()
