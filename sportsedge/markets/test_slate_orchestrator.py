"""Five-sport slate research acceptance; all offers and teams are synthetic."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, time, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo
import json
import unittest

from sportsedge.markets.test_cli import manifest
from sportsedge.markets.slate_orchestrator import SCHEMA,run_slate,main

CENTRAL=ZoneInfo("America/Chicago")


def fixture():
    now=datetime.now(timezone.utc)
    day=(now.astimezone(CENTRAL).date()+timedelta(days=1))
    start=datetime.combine(day,time(15,0),tzinfo=CENTRAL).astimezone(timezone.utc)
    later=start+timedelta(hours=3)
    one=manifest()
    one["projection"]["asof_utc"]=(now-timedelta(hours=1)).isoformat()
    for c in one["markets"]:
        for k in ("dk_quote","dk_opposite_quote"):
            c[k]["event_start_utc"]=start.isoformat()
    two=manifest()
    two["projection"].update(sport="NFL",event_id="NFL-E2",
                             home_id="HOME2",away_id="AWAY2",
                             expected_home=25,expected_away=22)
    two["distribution"]["sport"]="NFL"
    two["markets"]=[]
    return {
        "schema":SCHEMA,"slate_id":"SLATE-TEST",
        "slate_date_ct":day.isoformat(),
        "sports":["NFL","CFB","CBB","NBA","MLB"],
        "expected_events":[
            {"sport":"CBB","event_id":"GAME-1","start_utc":start.isoformat()},
            {"sport":"NFL","event_id":"NFL-E2","start_utc":later.isoformat()},
        ],
        "event_inputs":[
            {"sport":"CBB","event_id":"GAME-1","manifest":one},
            {"sport":"NFL","event_id":"NFL-E2","manifest":two},
        ],
    }


class FiveSportSlateContract(unittest.TestCase):
    def test_all_five_sports_and_all_family_gaps_visible(self):
        out=run_slate(fixture())
        self.assertEqual((out["counts"]["expected"],out["counts"]["inputs"]),(2,2))
        self.assertEqual(out["five_sports"]["MLB"]["status"],
                         "NO_AUTHENTICATED_SCHEDULE_EVIDENCE")
        self.assertEqual(out["five_sports"]["NBA"]["expected_games"],0)
        self.assertEqual(out["events"][0]["status"],"PAPER_0U_RESEARCH_ONLY")
        self.assertIn("ATTD",out["events"][1]["families"])
        self.assertEqual(out["events"][1]["families"]["FIRST_TD"]["submitted_research_candidates"],0)
        self.assertIn("SGP",out["events"][0]["families"])
        self.assertEqual(out["events"][0]["research_candidates"],1)
        self.assertEqual(out["events"][0]["research_priced"],1)
        self.assertEqual(out["events"][0]["research_rows"][0]["guard_state"],"BLOCK")
        self.assertFalse(out["source_authentication_verified"])
        self.assertFalse(out["issue10_release_certified"])
        self.assertEqual(out["approved_stake_u"],0)
        self.assertIsNone(out["card"])

    def test_no_game_silently_dropped_if_capture_missing(self):
        f=fixture();f["event_inputs"].pop()
        out=run_slate(f)
        missing=[e for e in out["events"] if e["event_id"]=="NFL-E2"][0]
        self.assertEqual(missing["status"],"BLOCK")
        self.assertIn("SCHEDULE_EVENT_CAPTURE_MISSING",missing["reasons"])
        self.assertEqual(out["counts"]["no_capture"],1)

    def test_duplicate_schedule_id_is_fatal(self):
        f=fixture();f["expected_events"].append(dict(f["expected_events"][0]))
        with self.assertRaisesRegex(ValueError,"DUPLICATED_SCHEDULE_EVENT"):
            run_slate(f)

    def test_extra_unscheduled_input_is_fatal(self):
        f=fixture();f["event_inputs"].append({
            "sport":"MLB","event_id":"UNKNOWN",
            "manifest":dict(f["event_inputs"][0]["manifest"])})
        with self.assertRaisesRegex(ValueError,"UNSCHEDULED_EVENT_INPUT"):
            run_slate(f)

    def test_event_start_quote_must_match_schedule(self):
        f=fixture()
        f["event_inputs"][0]["manifest"]["markets"][0]["dk_quote"][
            "event_start_utc"]=(datetime.now(timezone.utc)+timedelta(days=10)).isoformat()
        with self.assertRaisesRegex(ValueError,"QUOTE_START_DIFFERS_FROM_SCHEDULE"):
            run_slate(f)

    def test_model_event_id_must_match_slate_identity(self):
        f=fixture()
        f["event_inputs"][0]["manifest"]["projection"]["event_id"]="ELSEWHERE"
        with self.assertRaisesRegex(ValueError,"MODEL_EVENT_MISMATCH_WITH_SCHEDULE"):
            run_slate(f)

    def test_model_asof_cannot_be_after_event(self):
        f=fixture()
        target=f["expected_events"][0]["start_utc"]
        f["event_inputs"][0]["manifest"]["projection"]["asof_utc"]=target
        with self.assertRaisesRegex(ValueError,"MODEL_FEATURE_ASOF_AFTER_EVENT_START"):
            run_slate(f)

    def test_started_event_cannot_be_processed_into_picks(self):
        f=fixture()
        future=datetime.fromisoformat(f["expected_events"][1]["start_utc"])
        out=run_slate(f,now=future+timedelta(minutes=1))
        self.assertEqual(out["counts"]["after_start"],2)
        self.assertTrue(all(e["status"]=="BLOCK" for e in out["events"]))
        self.assertEqual(out["approved_stake_u"],0)

    def test_invalid_model_distribution_is_visible_block(self):
        f=fixture()
        f["event_inputs"][0]["manifest"]["distribution"]["sd_total"]=-1
        out=run_slate(f)
        event=[e for e in out["events"] if e["sport"]=="CBB"][0]
        self.assertEqual(event["status"],"BLOCK")
        self.assertGreaterEqual(out["counts"]["model_input_failures"],1)
        self.assertEqual(out["counts"]["priced_research"],0)

    def test_two_events_cannot_reuse_upstream_quote_id(self):
        f=fixture()
        other=deepcopy(f["event_inputs"][0]["manifest"])
        other["projection"]["event_id"]="GAME-2"
        for item in other["markets"]:
            item["market"]["event_id"]="GAME-2"
            for k in ("dk_quote","dk_opposite_quote"):
                item[k]["market"]["event_id"]="GAME-2"
        f["expected_events"].append({
            "sport":"CBB","event_id":"GAME-2",
            "start_utc":f["expected_events"][0]["start_utc"]})
        f["event_inputs"].append({
            "sport":"CBB","event_id":"GAME-2","manifest":other})
        with self.assertRaisesRegex(ValueError,
                    "PROVIDER_QUOTE_ID_REUSED_ACROSS_GAMES"):
            run_slate(f)

    def test_duplicate_nested_json_key_aborts_before_output(self):
        with TemporaryDirectory() as d:
            src=Path(d)/"input.json";out=Path(d)/"out.json"
            src.write_text(json.dumps(fixture()).replace(
                '"slate_id": "SLATE-TEST"',
                '"slate_id": "SLATE-TEST", "slate_id": "FORGED"'))
            with self.assertRaisesRegex(ValueError,"RUN_MANIFEST_DUPLICATE_JSON_KEY"):
                main([str(src),str(out)])
            self.assertFalse(out.exists())

    def test_private_output_is_create_only(self):
        with TemporaryDirectory() as d:
            src=Path(d)/"manifest.json";out=Path(d)/"report.json"
            src.write_text(json.dumps(fixture()))
            self.assertEqual(main([str(src),str(out)]),0)
            result=json.loads(out.read_text())
            self.assertEqual(result["state"],"BLOCK_OFFICIAL_RELEASE_RESEARCH_ONLY")
            self.assertEqual(result["official_counted"],0)
            with self.assertRaises(FileExistsError):
                main([str(src),str(out)])

    def test_unregistered_sport_or_bad_date_is_block(self):
        f=fixture();f["sports"].append("NHL")
        with self.assertRaisesRegex(ValueError,"INVALID_REQUESTED_SPORTS"):
            run_slate(f)
        f=fixture();f["slate_date_ct"]="2026-13-01"
        with self.assertRaisesRegex(ValueError,"INVALID_SLATE_DATE"):
            run_slate(f)

    def test_extra_unapproved_secret_field_is_not_accepted(self):
        f=fixture();f["api_key"]="secret"
        with self.assertRaisesRegex(ValueError,"INVALID_SLATE_FIELDS"):
            run_slate(f)


if __name__=="__main__":
    unittest.main()
