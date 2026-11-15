"""Synthetic create-only multi-sport command runner contract tests."""
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from hashlib import sha256

from sportsedge.markets.cli import run_from_manifest,main
from sportsedge.markets.pit_source_manifest import (
    MANIFEST_VERSION,_inputs_to_check,
)


def source_manifest(paths, sport, event_id, freeze_utc):
    """Artificial dated receipts for tests ONLY, not proof of historic capture."""
    freeze=datetime.fromisoformat(freeze_utc)
    files=[]
    for role,path in _inputs_to_check(paths).items():
        files.append({
           "role":role,"path":str(path),
           "raw_sha256":"sha256:"+sha256(path.read_bytes()).hexdigest(),
           "source_id":{"NFL":"NFLVERSE_WEEKLY","CBB":"CBB_HOOPR",
                        "CFB":"CFB_DATA","NBA":"NBA_STATS",
                        "MLB":"MLB_STATCAST"}[sport],
           "data_through_utc":(freeze-timedelta(days=3)).isoformat(),
           "observed_at_utc":(freeze-timedelta(hours=3)).isoformat(),
           "captured_at_utc":(freeze-timedelta(hours=2)).isoformat(),
        })
    return {"version":MANIFEST_VERSION,"sport":sport,"event_id":event_id,
            "forecast_asof_utc":freeze_utc,
            "model_trained_until_utc":(freeze-timedelta(days=2)).isoformat(),
            "files":files}


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

    def test_direct_cbb_claude_model_projection_without_bookmaker_inputs(self):
        from models.cbb import test_cbb
        paths={k:v for k,v in test_cbb.make_samples().items()
               if k not in ("odds","props")}
        p=manifest()
        p.pop("projection")
        asof=(nowutc()-timedelta(hours=1)).isoformat()
        p["projection_ref"]={
            "sport":"CBB","event_id":"C1","asof_utc":asof,
            "feature_paths":paths,
            "source_manifest":source_manifest(paths,"CBB","C1",asof),
        }
        p["markets"]=[]
        r=run_from_manifest(p)
        self.assertEqual(r["event_id"],"C1")
        self.assertEqual(r["model_projection_method"],"RECOVERED_MODEL_FUNCTION")
        self.assertEqual(r["approved_stake_u"],0)

    def test_direct_nfl_frozen_ridge_recomputation_in_research_cli(self):
        source=("team,off,def,gp,lg,hfa,asof,half_life,ridge\\n"
                "Alpha,2,1,5,21,1.6,2026-11-15,45,5\\n"
                "Beta,-1,0,5,21,1.6,2026-11-15,45,5\\n")
        # Construct physical CSV from actual newlines, not untrusted caller odds.
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ratings.csv"
            path.write_text(source.replace("\\n",chr(10)))
            p=manifest()
            p.pop("projection")
            asof=(nowutc()-timedelta(hours=1)).isoformat()
            p["projection_ref"]={
               "sport":"NFL","event_id":"NFL-TEST",
               "asof_utc":asof,
               "ratings_csv":str(path),
               "source_manifest":source_manifest(
                    {"ratings_csv":str(path)},"NFL","NFL-TEST",asof),
               "forecast":{
                   "home":"Alpha","away":"Beta",
                   "home_proj":"23.800","away_proj":"18.200",
                   "model_version":"SPORTSEDGE_NFL_RIDGE_R1",
                   "asof_ct":"2026-11-15T12:00:00+00:00",
               }
            }
            p["distribution"]["sport"]="NFL"
            p["markets"]=[]
            out=run_from_manifest(p)
            self.assertEqual(out["sport"],"NFL")
            self.assertEqual(out["model_projection_method"],"RECOVERED_MODEL_FUNCTION")

    def test_direct_model_without_pit_manifest_rejected(self):
        p=manifest()
        p.pop("projection")
        p["projection_ref"]={"sport":"CBB","event_id":"C1",
            "asof_utc":(nowutc()-timedelta(hours=1)).isoformat(),
            "feature_paths":{}}
        with self.assertRaisesRegex(ValueError,
                                    "PIT_SOURCE_MANIFEST_REQUIRED_FOR_DIRECT_MODEL"):
            run_from_manifest(p)

    def test_direct_model_file_hash_tamper_rejected(self):
        from models.cbb import test_cbb
        paths={k:v for k,v in test_cbb.make_samples().items()
               if k not in ("odds","props")}
        asof=(nowutc()-timedelta(hours=1)).isoformat()
        m=source_manifest(paths,"CBB","C1",asof)
        m["files"][0]["raw_sha256"]="sha256:"+"0"*64
        p=manifest()
        p.pop("projection")
        p["projection_ref"]={"sport":"CBB","event_id":"C1",
            "asof_utc":asof,"feature_paths":paths,"source_manifest":m}
        with self.assertRaisesRegex(ValueError,"PIT_FEATURE_RAW_HASH_MISMATCH"):
            run_from_manifest(p)

    def test_direct_model_future_observation_rejected(self):
        from models.cbb import test_cbb
        paths={k:v for k,v in test_cbb.make_samples().items()
               if k not in ("odds","props")}
        asof=(nowutc()-timedelta(hours=1)).isoformat()
        m=source_manifest(paths,"CBB","C1",asof)
        m["files"][0]["captured_at_utc"]=(nowutc()+timedelta(hours=1)).isoformat()
        p=manifest()
        p.pop("projection")
        p["projection_ref"]={"sport":"CBB","event_id":"C1",
            "asof_utc":asof,"feature_paths":paths,"source_manifest":m}
        with self.assertRaisesRegex(ValueError,"PIT_FEATURE_LOOKAHEAD_OR_BAD_CAPTURE_ORDER"):
            run_from_manifest(p)

    def test_odds_masquerading_as_projection_feature_rejected(self):
        from models.cbb import test_cbb
        paths=test_cbb.make_samples()
        asof=(nowutc()-timedelta(hours=1)).isoformat()
        p=manifest()
        p.pop("projection")
        p["projection_ref"]={"sport":"CBB","event_id":"C1",
            "asof_utc":asof,"feature_paths":paths,
            "source_manifest":{"version":"v1"}}
        with self.assertRaisesRegex(ValueError,
                                    "PIT_SCHEMA_EXTRA_OR_MISSING_FIELDS"):
            run_from_manifest(p)

    def test_two_team_projection_sources_fail_closed(self):
        p=manifest()
        p["projection_ref"]={"sport":"CBB"}
        with self.assertRaisesRegex(ValueError,"EXACTLY_ONE_TEAM_PROJECTION_SOURCE_REQUIRED"):
            run_from_manifest(p)

    def test_no_projection_source_fail_closed(self):
        p=manifest()
        del p["projection"]
        with self.assertRaisesRegex(ValueError,"EXACTLY_ONE_TEAM_PROJECTION_SOURCE_REQUIRED"):
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
