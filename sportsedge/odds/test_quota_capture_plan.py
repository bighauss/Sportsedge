"""Synthetic budget-planning tests. No user account, network or betting data."""
from __future__ import annotations
import csv
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.odds.event_discovery import discover_events
from sportsedge.odds.free_odds_aggregator_intake import SPORTS
from sportsedge.odds.quota_capture_plan import (
    PlanningBlocked, build_plan, load_catalog,
)

NOW=datetime(2026,11,15,20,0,tzinfo=timezone.utc)
KEY="SYNTHETIC_PROVIDER_KEY_123456"


def provider_event(i,minutes, sport="NFL"):
    return {
        "id":f"{i+1:032x}",
        "sport_key":SPORTS[sport],
        "commence_time":(NOW+timedelta(minutes=minutes)).isoformat(),
        "home_team":f"Home {i}","away_team":f"Away {i}",
    }


class Response(io.BytesIO):
    def __init__(self,raw):
        super().__init__(raw)
        self.headers={"x-requests-last":"0","x-requests-remaining":"500"}


def opener_for(events):
    raw=json.dumps(events).encode()
    def opener(req,timeout):
        return Response(raw)
    return opener


class PlannerTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)/"private"

    def roster(self,minutes=(60,120,180),sport="NFL"):
        events=[provider_event(i,x,sport) for i,x in enumerate(minutes)]
        r=discover_events(sport,self.root,key=KEY,opener=opener_for(events),now=NOW)
        return self.root/r["manifest_filename"]

    def plan(self,manifest,credits=500,**kwargs):
        return build_plan(manifest,self.root/"plan.json",
                          credits_remaining=credits,now=NOW+timedelta(minutes=1),**kwargs)

    def test_full_three_game_slate_18_credits_and_0600(self):
        p=self.roster()
        result=self.plan(p,credits=18)
        self.assertEqual(result["catalog_event_denominator"],3)
        self.assertEqual(result["eligible_upcoming_events"],3)
        self.assertEqual(result["planned_events"],3)
        self.assertEqual(result["estimated_credits_per_snapshot"],3)
        self.assertEqual(result["estimated_credits_per_event_take_plus_close"],6)
        self.assertEqual(result["estimated_credits_needed"],18)
        self.assertEqual(result["state"],"PAPER_0U_FULL_ELIGIBLE_CATALOG_PLAN_ONLY")
        self.assertTrue(result["no_scheduler_or_network_calls_created"])
        self.assertEqual(result["official_counted"],0)
        self.assertEqual(result["approved_stake_u"],0)
        self.assertEqual((self.root/"plan.json").stat().st_mode & 0o777,0o600)
        rows=result["events"]
        self.assertTrue(all(x["plan_status"]=="PLANNED_RESEARCH_ONLY" for x in rows))
        self.assertEqual(rows[0]["close_at_utc"],
                         (NOW+timedelta(minutes=55)).isoformat())

    def test_budget_one_credit_short_blocks_entire_population(self):
        p=self.roster()
        result=self.plan(p,credits=17)
        self.assertEqual(result["state"],"BLOCK_INSUFFICIENT_CREDITS_FOR_COMPLETE_CATALOG")
        self.assertEqual(result["planned_events"],0)
        self.assertEqual(result["not_planned_events"],3)
        self.assertEqual(result["catalog_event_denominator"],3)
        self.assertEqual(result["estimated_credits_needed"],18)
        self.assertTrue(all(r["plan_status"]=="BLOCK_QUOTA_INSUFFICIENT_FULL_COVERAGE"
                            for r in result["events"]))

    def test_reserve_credits_not_spent(self):
        p=self.roster()
        result=self.plan(p,credits=23,reserve_credits=6)
        self.assertEqual(result["operator_available_credits_for_plan"],17)
        self.assertEqual(result["planned_events"],0)

    def test_one_market_reduces_credit_estimate_without_auth(self):
        p=self.roster()
        result=self.plan(p,credits=6,markets=("h2h",))
        self.assertEqual(result["estimated_credits_per_snapshot"],1)
        self.assertEqual(result["estimated_credits_needed"],6)
        self.assertEqual(result["planned_events"],3)
        self.assertTrue(result["actual_provider_charge_not_verified"])

    def test_single_eligible_and_too_late_events_preserve_denominator(self):
        p=self.roster(minutes=(-10,8,30))
        result=self.plan(p,credits=6)
        self.assertEqual(result["catalog_event_denominator"],3)
        self.assertEqual(result["eligible_upcoming_events"],1)
        self.assertEqual(result["planned_events"],1)
        states={r["plan_status"] for r in result["events"]}
        self.assertIn("BLOCK_EVENT_ALREADY_STARTED",states)
        self.assertIn("BLOCK_TOO_LATE_FOR_DISTINCT_SNAPSHOTS",states)
        self.assertIn("PLANNED_RESEARCH_ONLY",states)

    def test_no_events_is_not_a_clean_slate(self):
        p=self.roster(minutes=())
        result=self.plan(p,credits=500)
        self.assertEqual(result["state"],"BLOCK_NO_ELIGIBLE_UPCOMING_EVENTS")
        self.assertEqual(result["planned_events"],0)

    def test_older_than_one_hour_event_catalog_refused(self):
        p=self.roster()
        with self.assertRaisesRegex(PlanningBlocked,"EVENT_CATALOG_STALE_OR_FROM_FUTURE"):
            build_plan(p,self.root/"plan.json",credits_remaining=500,
                       now=NOW+timedelta(hours=2))
        self.assertFalse((self.root/"plan.json").exists())

    def test_future_catalog_relative_to_local_clock_rejected(self):
        p=self.roster()
        with self.assertRaisesRegex(PlanningBlocked,"EVENT_CATALOG_STALE_OR_FROM_FUTURE"):
            build_plan(p,self.root/"plan.json",credits_remaining=500,
                       now=NOW-timedelta(seconds=1))

    def test_raw_original_tampering_detected(self):
        p=self.roster()
        manifest=json.loads(p.read_text())
        (self.root/manifest["original_raw_filename"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(PlanningBlocked,"EVENT_ORIGINAL_HASH_MISMATCH"):
            self.plan(p)
        self.assertFalse((self.root/"plan.json").exists())

    def test_catalog_tampering_detected(self):
        p=self.roster()
        manifest=json.loads(p.read_text())
        (self.root/manifest["catalog_filename"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(PlanningBlocked,"EVENT_CATALOG_HASH_MISMATCH"):
            self.plan(p)

    def test_catalog_duplicate_id_refused_even_with_rehashed_manifest(self):
        p=self.roster()
        metadata=json.loads(p.read_text())
        target=self.root/metadata["catalog_filename"]
        with target.open(newline="") as f:
            rows=list(csv.DictReader(f))
        rows[1]["source_event_id"]=rows[0]["source_event_id"]
        b=io.StringIO()
        w=csv.DictWriter(b,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader();w.writerows(rows)
        data=b.getvalue().encode()
        target.write_bytes(data)
        metadata["catalog_sha256"]="sha256:"+sha256(data).hexdigest()
        p.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(PlanningBlocked,"ID_MISSING_OR_DUPLICATED"):
            self.plan(p)

    def test_catalog_lineage_capture_timestamp_rejected(self):
        p=self.roster()
        meta=json.loads(p.read_text())
        target=self.root/meta["catalog_filename"]
        data=target.read_bytes().decode().replace("2026-11-15T20:00:00+00:00",
                                                  "2026-11-15T19:00:00+00:00")
        target.write_text(data)
        meta["catalog_sha256"]="sha256:"+sha256(data.encode()).hexdigest()
        p.write_text(json.dumps(meta))
        with self.assertRaisesRegex(PlanningBlocked,"SPORT_OR_CAPTURE_CHANGED"):
            self.plan(p)

    def test_invalid_budget_fails_before_writing_plan(self):
        p=self.roster()
        for kw in ({"credits_remaining":-1},{"credits_remaining":True},
                   {"credits_remaining":10,"reserve_credits":11},
                   {"credits_remaining":10,"reserve_credits":-1}):
            with self.subTest(kw=kw):
                with self.assertRaisesRegex(PlanningBlocked,"CREDIT_INPUT_INVALID"):
                    build_plan(p,self.root/"plan.json",now=NOW,**kw)
        self.assertFalse((self.root/"plan.json").exists())

    def test_unsupported_props_or_books_refused_not_looked_up(self):
        p=self.roster()
        with self.assertRaisesRegex(PlanningBlocked,"CAPTURE_MARKETS_NOT_SUPPORTED"):
            self.plan(p,markets=("h2h","player_pass_yds"))
        with self.assertRaisesRegex(PlanningBlocked,"CAPTURE_BOOKS_NOT_SUPPORTED"):
            self.plan(p,bookmakers=("unknown","draftkings"))

    def test_file_is_create_only(self):
        p=self.roster()
        self.plan(p)
        with self.assertRaisesRegex(PlanningBlocked,"OUTPUT_MUST_BE_NEW_PRIVATE_JSON"):
            self.plan(p)
        self.assertEqual(json.loads((self.root/"plan.json").read_text())["official_counted"],0)

    def test_source_native_ids_stay_unchanged(self):
        p=self.roster()
        report=self.plan(p)
        self.assertEqual(report["events"][0]["source_event_id"],f"{1:032x}")
        self.assertEqual(report["source_event_manifest_filename"],p.name)
        self.assertEqual(report["sport"],"NFL")

if __name__=="__main__":
    unittest.main()
