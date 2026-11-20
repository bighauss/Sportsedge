"""Synthetic CBB/CFB/NFL source-history ledger → player means → screenshot quotes."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from hashlib import sha256
from tempfile import TemporaryDirectory
import csv
import io
import json
import unittest

from sportsedge.markets.screenshot_line_handoff import run_line_capture
from sportsedge.markets.test_screenshot_line_handoff import fixture
from sportsedge.markets.cli import run_from_manifest
from sportsedge.markets.pit_player_history_fit import SCHEMA, CSV_COLUMNS


def history_refs(directory, slate):
    event=slate["event_inputs"][0]
    p=event["manifest"]
    asof=datetime.fromisoformat(p["projection_ref"]["asof_utc"])
    old=p.pop("player_features_ref")
    roster={"QB-1":"Alpha","WR-1":"Beta"}
    ctx={
        "schema":SCHEMA,"sport":"NFL","event_id":"NFL-TEST",
        "home_id":"Alpha","away_id":"Beta",
        "event_start_utc":slate["expected_events"][0]["start_utc"],
        "forecast_asof_utc":asof.isoformat(),
        "source_published_utc":(asof-timedelta(hours=3)).isoformat(),
        "source_captured_utc":(asof-timedelta(hours=2)).isoformat(),
        "normalized_history_sha256":"",
        "original_provider_sha256":"sha256:"+"a"*64,
        "source_id":"NFLVERSE_WEEKLY",
        "frozen_roster":roster,
        "confirmed_activity":{"QB-1":True,"WR-1":True},
    }
    rows=[]
    for i,(att,yds,targets,rec_yds) in enumerate(
        [(30,180,6,42),(32,210,7,57),(34,239,8,72),(36,250,9,67)],1):
        for pid,team,stat,unit,opp,value in (
            ("QB-1","Alpha","PASS_YDS","PASS_ATT",att,yds),
            ("WR-1","Beta","REC_YDS","TARGETS",targets,rec_yds),
        ):
            rows.append({
                "sport":"NFL","game_id":"WEEK-"+str(i),
                "game_end_utc":(asof-timedelta(days=7*i)).isoformat(),
                "player_id":pid,"team_id":team,"stat":stat,
                "opportunity_unit":unit,
                "opportunities":str(opp),"actual_stat":str(value),
            })
    out=io.StringIO(newline="")
    writer=csv.DictWriter(out,fieldnames=CSV_COLUMNS,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    raw=out.getvalue().encode()
    ctx["normalized_history_sha256"]="sha256:"+sha256(raw).hexdigest()
    raw_path=Path(directory)/"private_history.csv"
    context_path=Path(directory)/"private_history_context.json"
    raw_path.write_bytes(raw)
    ctx_raw=json.dumps(ctx,sort_keys=True).encode()
    context_path.write_bytes(ctx_raw)
    p["player_history_ref"]={
        "history_path":str(raw_path),
        "history_sha256":"sha256:"+sha256(raw).hexdigest(),
        "context_path":str(context_path),
        "context_sha256":"sha256:"+sha256(ctx_raw).hexdigest(),
        "odds_observed_at_utc":old["odds_observed_at_utc"],
    }
    return p,ctx,raw_path,context_path


def rehash(p, context, path):
    data=json.dumps(context,sort_keys=True).encode()
    path.write_bytes(data)
    p["player_history_ref"]["context_sha256"]="sha256:"+sha256(data).hexdigest()


class FullHistoryToScreenHandoff(unittest.TestCase):
    def test_one_screen_only_after_stored_nfl_history_and_team_projection(self):
        with TemporaryDirectory() as d:
            slate,snap,now=fixture(d)
            p,context,hist,context_path=history_refs(d,slate)
            result=run_line_capture(slate,snap,now=now)
            self.assertEqual(result["paired_markets"],2)
            self.assertEqual(result["captured_offers"],4)
            self.assertEqual((result["official_counted"],result["approved_stake_u"]),(0,0))
            for orientation in result["orientations"]:
                e=orientation["events"][0]
                self.assertEqual(e["model_method"],"RECOVERED_MODEL_FUNCTION")
                self.assertEqual(e["player_projection_producer"],
                                 "THREE_SPORT_PRIOR_GAME_HISTORY_UNCALIBRATED")
                self.assertEqual(e["player_projection_builder_census"]["produced"],2)
                self.assertEqual(e["player_projection_builder_census"]
                                 ["history_fit"]["forecast_rows"],2)
                self.assertFalse(e["player_projection_builder_census"]
                                 ["history_fit"]["source_authenticated"])
                self.assertEqual(e["research_candidates"],2)
                self.assertTrue(all(x["guard_state"]=="BLOCK" for x in e["research_rows"]))

    def test_archived_history_can_feed_research_without_screenshot_pricing(self):
        with TemporaryDirectory() as d:
            slate,snap,_=fixture(d)
            p,_,_,_=history_refs(d,slate)
            out=run_from_manifest(p)
            self.assertEqual(out["player_projection_builder_census"]["produced"],2)
            self.assertEqual(out["approved_stake_u"],0)

    def test_source_byte_mutation_fails_closed(self):
        with TemporaryDirectory() as d:
            slate,snap,_=fixture(d)
            p,_,history,_=history_refs(d,slate)
            history.write_bytes(history.read_bytes()+b"\n")
            with self.assertRaisesRegex(ValueError,"PLAYER_HISTORY_ORIGINAL_SOURCE_HASH_MISMATCH"):
                run_from_manifest(p)

    def test_context_changed_after_original_sha_is_rejected(self):
        with TemporaryDirectory() as d:
            slate,snap,_=fixture(d)
            p,ctx,hist,context_path=history_refs(d,slate)
            ctx["confirmed_activity"]["QB-1"]=False
            context_path.write_text(json.dumps(ctx))
            with self.assertRaisesRegex(ValueError,"PLAYER_HISTORY_ORIGINAL_SOURCE_HASH_MISMATCH"):
                run_from_manifest(p)

    def test_future_player_source_rejected_not_reused(self):
        with TemporaryDirectory() as d:
            slate,snap,_=fixture(d)
            p,ctx,hist,context_path=history_refs(d,slate)
            ctx["source_captured_utc"]=(datetime.now(timezone.utc)+
                                        timedelta(hours=4)).isoformat()
            rehash(p,ctx,context_path)
            with self.assertRaisesRegex(ValueError,"HISTORY_SOURCE_PUBLICATION_OR_FREEZE_LOOKAHEAD"):
                run_from_manifest(p)

    def test_same_player_id_wrong_team_is_not_implicitly_rebound(self):
        with TemporaryDirectory() as d:
            slate,snap,_=fixture(d)
            p,ctx,hist,context_path=history_refs(d,slate)
            ctx["frozen_roster"]["QB-1"]="Beta"
            rehash(p,ctx,context_path)
            with self.assertRaisesRegex(ValueError,"HISTORY_PLAYER_CHANGED_TEAM_IDENTITY"):
                run_from_manifest(p)

    def test_missing_frozen_roster_identity_blocks(self):
        with TemporaryDirectory() as d:
            slate,snap,_=fixture(d)
            p,ctx,hist,context_path=history_refs(d,slate)
            ctx["frozen_roster"].pop("WR-1")
            rehash(p,ctx,context_path)
            with self.assertRaisesRegex(ValueError,"PLAYER_HISTORY_FROZEN_ROSTER_MISMATCH"):
                run_from_manifest(p)

    def test_no_dual_player_sources_possible(self):
        with TemporaryDirectory() as d:
            slate,snap,_=fixture(d)
            p,_,_,_=history_refs(d,slate)
            p["player_file"]={"path":"/private/dummy"}
            with self.assertRaisesRegex(ValueError,"ONLY_ONE_PLAYER_FORECAST_SOURCE_ALLOWED"):
                run_from_manifest(p)

    def test_unverified_caller_team_scores_cannot_enter_history_mode(self):
        with TemporaryDirectory() as d:
            slate,snap,_=fixture(d)
            p,_,_,_=history_refs(d,slate)
            from sportsedge.markets.test_cli import manifest
            p["projection"]={
                **manifest()["projection"],
                "sport":"NFL","event_id":"NFL-TEST",
                "home_id":"Alpha","away_id":"Beta",
            }
            del p["projection_ref"]
            with self.assertRaisesRegex(ValueError,"PLAYER_HISTORY_REQUIRES_DIRECT_OWN_TEAM_MODEL"):
                run_from_manifest(p)


if __name__=="__main__":
    unittest.main()
