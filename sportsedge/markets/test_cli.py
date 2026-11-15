"""Synthetic create-only multi-sport command runner contract tests."""
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path

from sportsedge.markets.cli import run_from_manifest,main

H="sha256:"+"a"*64
S="sha256:"+"b"*64


def nowutc():
    return datetime.now(timezone.utc)


def manifest():
    now=nowutc()
    p_asof=(now-timedelta(hours=1)).isoformat()
    fit=(now-timedelta(days=15)).isoformat()
    observed=(now-timedelta(minutes=2)).isoformat()
    received=(now-timedelta(minutes=1)).isoformat()
    kickoff=(now+timedelta(hours=3)).isoformat()
    def market(side):
        return {"sport":"CBB","event_id":"GAME-1","kind":"TOTAL",
                "period":"FG","selection":side,"line":"142.5",
                "settlement":"REGULATION"}
    def quote(side,receipt,quote_id):
        return {"market":market(side),"odds_american":-110,
                "book":"DraftKings","provider_id":"dk_feed_test",
                "provider_event_id":"prov-event-1",
                "provider_market_id":"prov-total-1",
                "quote_id":quote_id,"receipt_id":receipt,
                "raw_payload_sha256":H,
                "observed_at_utc":observed,
                "received_at_utc":received,
                "event_start_utc":kickoff}
    return {
        "projection":{
            "sport":"CBB","event_id":"GAME-1","home_id":"HOME","away_id":"AWAY",
            "expected_home":70.0,"expected_away":68.0,
            "model_sha256":H,"feature_sha256":S,"asof_utc":p_asof,
        },
        "distribution":{
            "sport":"CBB","sd_margin":11.0,"sd_total":16.0,
            "period_shares":[.24,.26,.24,.26],
            "model_sha256":H,"training_end_utc":fit,
            "status":"UNCALIBRATED_RESEARCH",
        },
        "simulation_count":1100,"simulation_seed":20261115,
        "markets":[{
            "market":market("OVER"),"dk_quote":quote("OVER","one","q1"),
            "dk_opposite_quote":quote("UNDER","two","q2"),
            "v21_inputs":{"sport":"CBB","source_receipt_verified":True,
                          "independent_model_verified":True},
        }],
    }


class CLIContract(unittest.TestCase):
    def test_cbb_single_market_research_only(self):
        out=run_from_manifest(manifest())
        self.assertEqual(out["status"],"PAPER_0U_RESEARCH_ONLY")
        self.assertEqual(out["submitted_candidates"],1)
        self.assertEqual(out["approved_stake_u"],0)
        self.assertIsNone(out["card"])
        self.assertEqual(out["rows"][0]["guard_state"],"BLOCK")
        self.assertEqual(out["rows"][0]["research_state"],"PAPER_0U")

    def test_missing_price_returns_visible_block(self):
        p=manifest()
        p["markets"][0].pop("dk_opposite_quote")
        out=run_from_manifest(p)
        self.assertIn("MISSING_TWO_SIDED_PRICE",out["rows"][0]["research_reasons"])
        self.assertEqual(out["rows"][0]["approved_stake_u"],0)

    def test_fake_source_auth_claim_cannot_lift_gate(self):
        p=manifest()
        p["markets"][0]["v21_inputs"]={"source_receipt_verified":True,
                "independent_model_verified":True,"sport":"CBB"}
        out=run_from_manifest(p)
        self.assertEqual(out["rows"][0]["guard_state"],"BLOCK")
        self.assertEqual(out["official_counted"],0)

    def test_model_generated_after_event_quote_blocked(self):
        p=manifest()
        p["projection"]["asof_utc"]=(nowutc()+timedelta(minutes=5)).isoformat()
        with self.assertRaisesRegex(ValueError,"MODEL_PROJECTION_DATED_IN_FUTURE"):
            run_from_manifest(p)

    def test_unknown_secret_field_rejected(self):
        p=manifest()
        p["markets"][0]["dk_quote"]["api_key"]="fake secret"
        with self.assertRaisesRegex(ValueError,"UNSUPPORTED_OR_SECRET_FIELD"):
            run_from_manifest(p)

    def test_create_only_cli_does_not_overwrite_archives(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"input.json"; dest=Path(d)/"out.json"
            src.write_text(json.dumps(manifest()))
            self.assertEqual(main([str(src),str(dest)]),0)
            payload=json.loads(dest.read_text())
            self.assertEqual(payload["status"],"PAPER_0U_RESEARCH_ONLY")
            self.assertEqual(payload["approved_stake_u"],0)
            with self.assertRaises(FileExistsError):
                main([str(src),str(dest)])


if __name__=="__main__":
    unittest.main()
