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

    def test_zero_market_event_does_not_count_as_processed_game(self):
        out=run_slate(fixture())
        event=next(e for e in out["events"] if e["event_id"]=="NFL-E2")
        self.assertEqual(event["status"],"BLOCK")
        self.assertIn("NO_MARKETS_SUBMITTED_OR_OFFERED_UNVERIFIED",event["reasons"])
        self.assertEqual(out["counts"]["no_market_rows"],1)
        self.assertEqual(out["five_sports"]["NFL"]["research_processed_games"],0)
        self.assertEqual(event["research_candidates"],0)

    def test_sgp_inventory_keeps_valid_straight_research_alive(self):
        f=fixture()
        event=f["event_inputs"][0]["manifest"]
        event["markets"].insert(0,{"market":{
            "sport":"CBB","event_id":"GAME-1","kind":"SGP","period":"FG"}})
        out=run_slate(f)
        cbb=next(e for e in out["events"] if e["sport"]=="CBB")
        self.assertEqual(cbb["status"],"PAPER_0U_RESEARCH_ONLY")
        self.assertEqual(cbb["research_candidates"],2)
        self.assertEqual(cbb["research_priced"],1)
        self.assertEqual(cbb["research_blocked"],1)
        self.assertEqual(cbb["research_rows"][0]["research_state"],"BLOCK")
        self.assertIn("SGP_REQUIRES_POSTED_JOINT_QUOTE_AND_CALIBRATED_EVENTS",
                      cbb["research_rows"][0]["research_reasons"])
        self.assertEqual(cbb["research_rows"][1]["guard_state"],"BLOCK")
        self.assertEqual(out["counts"]["sgp_inventory_rows"],1)
        self.assertFalse(cbb["sgp_joint_pricing_certified"])
        self.assertEqual((out["approved_stake_u"],out["official_counted"]),(0,0))

    def test_sgp_only_is_block_not_false_priced_model(self):
        f=fixture()
        f["event_inputs"][1]["manifest"]["markets"]=[
            {"market":{"sport":"NFL","event_id":"NFL-E2",
                       "kind":"SGP","period":"FG"}}]
        out=run_slate(f)
        nfl=next(e for e in out["events"] if e["sport"]=="NFL")
        self.assertEqual(nfl["status"],"BLOCK")
        self.assertEqual(nfl["research_candidates"],1)
        self.assertEqual(nfl["research_priced"],0)
        self.assertEqual(nfl["research_blocked"],1)
        self.assertIn("ONLY_UNPRICED_SGP_INVENTORY_SUBMITTED",nfl["reasons"])
        self.assertEqual(out["counts"]["sgp_only_games"],1)
        self.assertEqual(out["five_sports"]["NFL"]["research_processed_games"],0)

    def test_sgp_fake_single_leg_price_is_rejected(self):
        f=fixture()
        quote=deepcopy(f["event_inputs"][0]["manifest"]["markets"][0]["dk_quote"])
        f["event_inputs"][0]["manifest"]["markets"].append({
            "market":{"sport":"CBB","event_id":"GAME-1","kind":"SGP","period":"FG"},
            "dk_quote":quote,
        })
        with self.assertRaisesRegex(ValueError,"SGP_INVENTORY_ONLY_NO_SINGLE_LEG_QUOTE"):
            run_slate(f)

    def test_non_full_game_sgp_placeholder_is_rejected(self):
        f=fixture()
        f["event_inputs"][0]["manifest"]["markets"].append({
            "market":{"sport":"CBB","event_id":"GAME-1","kind":"SGP","period":"1H"},
        })
        with self.assertRaisesRegex(ValueError,"SGP_INVENTORY_ONLY_NO_SINGLE_LEG_QUOTE"):
            run_slate(f)

    def test_sgp_cannot_claim_v21_guard_passed(self):
        f=fixture()
        f["event_inputs"][0]["manifest"]["markets"].append({
            "market":{"sport":"CBB","event_id":"GAME-1","kind":"SGP","period":"FG"},
            "v21_inputs":{"source_receipt_verified":True},
        })
        with self.assertRaisesRegex(ValueError,"SGP_INVENTORY_ONLY_NO_SINGLE_LEG_QUOTE"):
            run_slate(f)

    def test_duplicate_sgp_placeholders_refused_as_inflated_market_census(self):
        f=fixture()
        event=f["event_inputs"][0]["manifest"]
        sgp={"market":{"sport":"CBB","event_id":"GAME-1","kind":"SGP","period":"FG"}}
        event["markets"]=[deepcopy(sgp),*event["markets"],deepcopy(sgp)]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_UNPRICED_SGP_INVENTORY"):
            run_slate(f)

    def test_single_sgp_after_straight_keeps_original_order(self):
        f=fixture()
        event=f["event_inputs"][0]["manifest"]
        event["markets"].append({"market":{
            "sport":"CBB","event_id":"GAME-1","kind":"SGP","period":"FG"}})
        out=run_slate(f)
        rows=next(e for e in out["events"] if e["sport"]=="CBB")["research_rows"]
        self.assertEqual([r["research_state"] for r in rows],["PAPER_0U","BLOCK"])
        self.assertEqual(out["counts"]["sgp_inventory_rows"],1)
        self.assertEqual(out["counts"]["priced_research"],1)
        self.assertEqual(out["counts"]["blocked_research"],1)

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
        f=fixture();f["sports"].append("F1")
        with self.assertRaisesRegex(ValueError,"INVALID_REQUESTED_SPORTS"):
            run_slate(f)
        f=fixture();f["slate_date_ct"]="2026-13-01"
        with self.assertRaisesRegex(ValueError,"INVALID_SLATE_DATE"):
            run_slate(f)

    def test_nhl_and_pga_scheduled_events_are_visible_nonpricing_blocks(self):
        f=fixture()
        f["sports"].extend(("NHL","PGA"))
        kickoff=f["expected_events"][0]["start_utc"]
        f["expected_events"].extend((
            {"sport":"NHL","event_id":"NHL-ONE","start_utc":kickoff},
            {"sport":"PGA","event_id":"PGA-TOUR-ONE","start_utc":kickoff},
        ))
        result=run_slate(f)
        self.assertEqual(result["counts"]["expected"],4)
        self.assertEqual(result["counts"]["schedule_only_unpriced_events"],2)
        self.assertEqual(result["research_pricing_sports"],["CBB","CFB","MLB","NBA","NFL"])
        self.assertEqual(result["schedule_only_sports"],["NHL","PGA"])
        self.assertEqual(result["sport_coverage"]["NHL"]["status"],
                         "SCHEDULE_ONLY_NO_PRICING_KERNEL")
        self.assertEqual(result["sport_coverage"]["PGA"]["research_processed_games"],0)
        for sport in ("NHL","PGA"):
            event=next(x for x in result["events"] if x["sport"]==sport)
            self.assertEqual(event["status"],"BLOCK")
            self.assertIn("NO_SUPPORTED_NHL_OR_PGA_PRICING_KERNEL",event["reasons"])
            self.assertEqual(event["research_priced"],0)
            self.assertEqual(event["approved_stake_u"],0)
            self.assertIsNone(event["card"])
            self.assertTrue(event["families"])
            self.assertTrue(all(
                family["status"]=="NO_SUPPORTED_PRICING_ADAPTER"
                and family["submitted_research_candidates"]==0
                for family in event["families"].values()))
        self.assertIn("GOALIE_SAVES",next(x for x in result["events"]
                                            if x["sport"]=="NHL")["families"])
        self.assertIn("FIRST_ROUND_LEADER",next(x for x in result["events"]
                                            if x["sport"]=="PGA")["families"])

    def test_unpriced_sports_cannot_be_accidentally_sent_to_five_sport_kernel(self):
        f=fixture()
        f["sports"].append("NHL")
        f["expected_events"].append({
            "sport":"NHL","event_id":"NHL-ONE",
            "start_utc":f["expected_events"][0]["start_utc"]})
        f["event_inputs"].append({
            "sport":"NHL","event_id":"NHL-ONE",
            "manifest":deepcopy(f["event_inputs"][0]["manifest"])})
        with self.assertRaisesRegex(ValueError,
                                     "SCHEDULE_ONLY_SPORT_HAS_NO_VALIDATED_PRICER"):
            run_slate(f)

    def test_slate_cli_source_and_output_cannot_live_inside_public_repository(self):
        repo=Path(__file__).resolve().parents[2]
        with TemporaryDirectory() as d:
            source=Path(d)/"private_input.json"
            source.write_text(json.dumps(fixture()))
            bad=repo/"some_private_output_never_create.json"
            with self.assertRaisesRegex(ValueError,
                                         "RESEARCH_SLATE_OUTPUT_MUST_BE_PRIVATE"):
                main([str(source),str(bad)])
            with self.assertRaisesRegex(ValueError,
                                         "RESEARCH_SLATE_INPUT_MUST_BE_PRIVATE"):
                main([str(repo/"hidden_input_never_create.json"),
                      str(Path(d)/"output.json")])
            self.assertFalse(bad.exists())

    def test_extra_unapproved_secret_field_is_not_accepted(self):
        f=fixture();f["api_key"]="secret"
        with self.assertRaisesRegex(ValueError,"INVALID_SLATE_FIELDS"):
            run_slate(f)


if __name__=="__main__":
    unittest.main()
