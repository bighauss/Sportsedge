"""Offline complete-slate TAKE/CLOSE provenance tests using only fake provider bytes."""
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
from sportsedge.odds.free_odds_aggregator_intake import SPORTS, BASE
from sportsedge.odds.quota_capture_plan import build_plan
from sportsedge.odds.the_odds_api_clv_export import write_export
from sportsedge.odds.capture_plan_reconciliation import (
    ReconciliationBlocked, reconcile,
)

NOW=datetime(2026,11,15,20,0,tzinfo=timezone.utc)
KICKOFF=NOW+timedelta(hours=1)
ID="0123456789abcdef0123456789abcdef"
KEY="ONLY_SYNTHETIC_API_KEY_12345678"


class Response(io.BytesIO):
    def __init__(self,raw):
        super().__init__(raw)
        self.headers={"x-requests-last":"0","x-requests-remaining":"500"}


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)/"private"
        event={"id":ID,"sport_key":SPORTS["NFL"],"commence_time":KICKOFF.isoformat(),
               "home_team":"Home Team","away_team":"Away Team"}
        out=discover_events("NFL",self.root,key=KEY,now=NOW,
                            opener=lambda req,timeout:Response(json.dumps([event]).encode()))
        self.plan=self.root/"approved.json"
        build_plan(self.root/out["manifest_filename"],self.plan,
                   credits_remaining=6,now=NOW+timedelta(minutes=1))
        self.output=self.root/"reconciled.json"

    def snapshot(self,role,clock=None,observed=None,changed_kickoff=None,
                 name=None,make_csv=True,source_id=ID,price_shift=0):
        clock=clock or (NOW+timedelta(minutes=1) if role=="TAKE"
                        else NOW+timedelta(minutes=55))
        observed=observed or clock-timedelta(seconds=30)
        kickoff=changed_kickoff or KICKOFF
        events=[{
            "id":source_id,"sport_key":SPORTS["NFL"],
            "commence_time":kickoff.isoformat(),"home_team":"Home Team",
            "away_team":"Away Team",
            "bookmakers":[
                {"key":book,"markets":[
                    {"key":"h2h","last_update":observed.isoformat(),
                     "outcomes":[
                         {"name":"Home Team","price":-110-price_shift},
                         {"name":"Away Team","price":105+price_shift}]},
                    {"key":"spreads","last_update":observed.isoformat(),
                     "outcomes":[
                         {"name":"Home Team","point":-3.5,"price":-110},
                         {"name":"Away Team","point":3.5,"price":105}]},
                    {"key":"totals","last_update":observed.isoformat(),
                     "outcomes":[
                         {"name":"Over","point":44.5,"price":-110},
                         {"name":"Under","point":44.5,"price":-110}]},
                ]} for book in ("draftkings","fanduel")
            ],
        }]
        raw=json.dumps(events).encode()
        stem=name or ("aggregator_NFL_"+role.lower()+"_"+str(len(list(self.root.glob("aggregator_*")))))
        raw_name=stem+".json"
        manifest_name=stem+".manifest.json"
        (self.root/raw_name).write_bytes(raw)
        meta={
            "schema":"sportsedge-oddsapi-aggregator-raw-v1",
            "sport":"NFL",
            "read_only_endpoint":BASE+SPORTS["NFL"]+"/events/"+ID+"/odds",
            "raw_filename":raw_name,"events_returned":1,
            "requested_event_id":ID,
            "requested_markets":["h2h","spreads","totals"],
            "requested_books":["draftkings","fanduel"],
            "captured_utc":clock.isoformat(),
            "original_raw_sha256":"sha256:"+sha256(raw).hexdigest(),
        }
        manifest=self.root/manifest_name
        manifest.write_text(json.dumps(meta))
        if make_csv:
            write_export(manifest,self.root/(stem+"."+role.lower()+".csv"),
                         "TAKE" if role=="TAKE" else "HISTORY")
        return manifest

    def both(self):
        self.snapshot("TAKE")
        self.snapshot("CLOSE")

    def test_complete_source_consistent_pair_with_every_game_retained(self):
        self.both()
        out=reconcile(self.plan,self.output)
        self.assertEqual(out["state"],"PAPER_0U_ALL_PLAN_CAPTURE_FILES_CONSISTENT")
        self.assertEqual(out["source_plan_event_denominator"],1)
        self.assertEqual(out["planned_event_denominator"],1)
        self.assertEqual(out["reconciled_planned_events"],1)
        self.assertTrue(out["all_plan_rows_retained"])
        self.assertEqual(out["events"][0]["take_status"],"PAPER_0U_SOURCE_CONSISTENT_CAPTURE")
        self.assertEqual(out["events"][0]["close_status"],"PAPER_0U_SOURCE_CONSISTENT_CAPTURE")
        self.assertEqual(out["events"][0]["take"]["quote_rows"],12)
        self.assertEqual(out["events"][0]["close"]["quote_rows"],12)
        self.assertEqual(out["official_counted"],0)
        self.assertEqual(out["matched_actual_clv_bets"],0)
        self.assertEqual(self.output.stat().st_mode & 0o777,0o600)

    def test_missing_close_retains_denominator(self):
        self.snapshot("TAKE")
        r=reconcile(self.plan,self.output)
        self.assertEqual(r["state"],"BLOCK_INCOMPLETE_OR_INVALID_PLAN_CAPTURE_COVERAGE")
        self.assertEqual(r["events"][0]["close_status"],"BLOCK_MISSING_CLOSE")
        self.assertEqual(r["reconciled_planned_events"],0)
        self.assertEqual(r["source_plan_event_denominator"],1)

    def test_missing_take_retains_denominator(self):
        self.snapshot("CLOSE")
        r=reconcile(self.plan,self.output)
        self.assertEqual(r["events"][0]["take_status"],"BLOCK_MISSING_TAKE")

    def test_duplicate_take_quarantines_all_copies(self):
        self.snapshot("TAKE",name="aggregator_NFL_take_a")
        self.snapshot("TAKE",name="aggregator_NFL_take_b")
        self.snapshot("CLOSE")
        r=reconcile(self.plan,self.output)
        self.assertEqual(r["events"][0]["take_status"],"BLOCK_DUPLICATE_TAKE_ALL_COPIES")
        self.assertEqual(r["reconciled_planned_events"],0)
        self.assertIn("BLOCK_DUPLICATE_TAKE_ALL_COPIES",r["status_counts"])

    def test_double_phase_same_raw_not_cherry_picked(self):
        take=self.snapshot("TAKE")
        stem=take.name[:-len(".manifest.json")]
        write_export(take,self.root/(stem+".close.csv"),"HISTORY")
        self.snapshot("CLOSE")
        r=reconcile(self.plan,self.output)
        self.assertIn(take.name,r["events"][0]["unlabeled_original_manifests"])
        self.assertEqual(r["state"],"BLOCK_INCOMPLETE_OR_INVALID_PLAN_CAPTURE_COVERAGE")

    def test_corrupted_original_hash_rejected(self):
        take=self.snapshot("TAKE")
        self.snapshot("CLOSE")
        info=json.loads(take.read_text())
        (self.root/info["raw_filename"]).write_text("{}")
        r=reconcile(self.plan,self.output)
        self.assertEqual(r["events"][0]["take_status"],"BLOCK_ORIGINAL_HASH_OR_SCHEMA")

    def test_source_price_rewrite_even_with_rehashed_audit_refused(self):
        take=self.snapshot("TAKE")
        self.snapshot("CLOSE")
        stem=take.name[:-len(".manifest.json")]
        csv_path=self.root/(stem+".take.csv")
        with csv_path.open(newline="") as f:
            records=list(csv.DictReader(f))
        records[0]["price_american"]="-125"
        buf=io.StringIO()
        w=csv.DictWriter(buf,fieldnames=list(records[0]),lineterminator="\n")
        w.writeheader();w.writerows(records)
        new_bytes=buf.getvalue().encode()
        csv_path.write_bytes(new_bytes)
        audit=self.root/(stem+".take.csv.audit.json")
        data=json.loads(audit.read_text())
        data["normalized_csv_sha256"]="sha256:"+sha256(new_bytes).hexdigest()
        audit.write_text(json.dumps(data))
        r=reconcile(self.plan,self.output)
        self.assertEqual(r["events"][0]["take_status"],"BLOCK_NORMALIZED_QUOTES_DISAGREE_WITH_ORIGINAL")

    def test_missing_audit_sidecar_invalidates_capture(self):
        take=self.snapshot("TAKE")
        self.snapshot("CLOSE")
        stem=take.name[:-len(".manifest.json")]
        (self.root/(stem+".take.csv.audit.json")).unlink()
        r=reconcile(self.plan,self.output)
        self.assertEqual(r["events"][0]["take_status"],"BLOCK_MISSING_NORMALIZED_CSV_OR_AUDIT")

    def test_changed_kickoff_is_not_matched(self):
        self.snapshot("TAKE",changed_kickoff=KICKOFF+timedelta(minutes=20))
        self.snapshot("CLOSE")
        r=reconcile(self.plan,self.output)
        self.assertEqual(r["events"][0]["take_status"],"BLOCK_CHANGED_PROVIDER_KICKOFF")

    def test_late_close_not_counted_even_if_normalized(self):
        self.snapshot("TAKE")
        self.snapshot("CLOSE",clock=KICKOFF-timedelta(minutes=11))
        r=reconcile(self.plan,self.output)
        self.assertEqual(r["events"][0]["close_status"],"BLOCK_CLOSE_OUTSIDE_T_MINUS_TEN")

    def test_one_sided_unsupported_empty_source_is_not_success(self):
        self.snapshot("TAKE",observed=NOW-timedelta(hours=5))
        self.snapshot("CLOSE")
        r=reconcile(self.plan,self.output)
        self.assertEqual(r["events"][0]["take_status"],"BLOCK_NO_TWO_SIDED_QUOTES")

    def test_unlabeled_raw_manifest_stays_visible(self):
        self.snapshot("TAKE",make_csv=False)
        self.snapshot("CLOSE")
        r=reconcile(self.plan,self.output)
        self.assertEqual(r["events"][0]["take_status"],"BLOCK_MISSING_TAKE")
        self.assertEqual(len(r["events"][0]["unlabeled_original_manifests"]),1)
        self.assertEqual(r["state"],"BLOCK_INCOMPLETE_OR_INVALID_PLAN_CAPTURE_COVERAGE")

    def test_off_plan_raw_event_blocks_complete_status(self):
        self.both()
        self.snapshot("TAKE",source_id="f"*32,name="aggregator_NFL_unplanned",
                      make_csv=False)
        r=reconcile(self.plan,self.output)
        self.assertEqual(len(r["unassigned_original_manifests"]),1)
        self.assertEqual(r["state"],"BLOCK_INCOMPLETE_OR_INVALID_PLAN_CAPTURE_COVERAGE")

    def test_create_only_output_cannot_overwrite_previous_audit(self):
        self.both()
        reconcile(self.plan,self.output)
        with self.assertRaises(Exception):
            reconcile(self.plan,self.output)
        self.assertEqual(json.loads(self.output.read_text())["official_counted"],0)

    def test_no_quotes_does_not_become_zero_clv(self):
        r=reconcile(self.plan,self.output)
        self.assertIsNone(r["events"][0]["take"])
        self.assertIsNone(r["events"][0]["close"])
        self.assertEqual(r["reconciled_planned_events"],0)
        self.assertEqual(r["matched_actual_clv_bets"],0)

if __name__=="__main__":
    unittest.main()
