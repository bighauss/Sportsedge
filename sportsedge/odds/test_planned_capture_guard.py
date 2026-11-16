"""Adversarial plan-bound pre-HTTP capture checks, synthetic inputs only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sportsedge.odds.event_discovery import discover_events
from sportsedge.odds.free_odds_aggregator_intake import SPORTS
from sportsedge.odds.planned_capture_guard import CapturePlanBlocked, guard_plan
from sportsedge.odds.prospective_clv_cycle import capture_cycle
from sportsedge.odds.quota_capture_plan import build_plan

NOW=datetime(2026,11,15,20,0,tzinfo=timezone.utc)
KEY="DUMMY_LOCAL_KEY_20261115"
ID="0123456789abcdef0123456789abcdef"
MARKETS=("h2h","spreads","totals")
BOOKS=("draftkings","fanduel")


def event(kickoff, ident=ID):
    return {"sport_key":SPORTS["NFL"],"id":ident,
        "home_team":"Home Team","away_team":"Away Team",
        "commence_time":kickoff.isoformat()}


class Response(io.BytesIO):
    def __init__(self,payload):
        super().__init__(json.dumps(payload).encode())
        self.headers={"x-requests-remaining":"490","x-requests-last":"1"}


class PlanTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name)/"private"
        self.kickoff=NOW+timedelta(minutes=60)

    def create_plan(self,credits=6,kickoff=None):
        kickoff=kickoff or self.kickoff
        roster=discover_events(
            "NFL",self.root,key=KEY,now=NOW,
            opener=lambda req,timeout:Response([event(kickoff)]))
        src=self.root/roster["manifest_filename"]
        out=self.root/"approved.json"
        build_plan(src,out,credits_remaining=credits,now=NOW+timedelta(minutes=1))
        return out

    def check(self,plan,phase="TAKE",now=None,**kwargs):
        return guard_plan(plan,sport=kwargs.pop("sport","NFL"),
                          event_id=kwargs.pop("event_id",ID),
                          phase=phase,markets=kwargs.pop("markets",MARKETS),
                          bookmakers=kwargs.pop("bookmakers",BOOKS),
                          now=now or NOW+timedelta(minutes=1),**kwargs)

    def test_take_guard_before_http_and_exact_kickoff(self):
        p=self.create_plan()
        output=self.check(p)
        self.assertEqual(output["validation_state"],"PAPER_0U_PLAN_GUARD_PASSED")
        self.assertEqual(output["expected_kickoff_utc"],self.kickoff.isoformat())
        self.assertEqual(output["plan_event_count"],1)
        self.assertEqual(output["official_counted"],0)
        self.assertEqual(output["plan_sha256"],"sha256:"+sha256(p.read_bytes()).hexdigest())

    def test_close_at_t_minus_five_is_valid(self):
        p=self.create_plan()
        out=self.check(p,"CLOSE",now=self.kickoff-timedelta(minutes=5))
        self.assertEqual(out["expected_kickoff_utc"],self.kickoff.isoformat())

    def test_close_too_early_blocks_before_fetch(self):
        p=self.create_plan()
        with self.assertRaisesRegex(CapturePlanBlocked,"CLOSE_OUTSIDE"):
            self.check(p,"CLOSE",now=NOW+timedelta(minutes=20))

    def test_close_at_or_after_kickoff_blocks(self):
        p=self.create_plan()
        with self.assertRaisesRegex(CapturePlanBlocked,"CLOSE_OUTSIDE"):
            self.check(p,"CLOSE",now=self.kickoff)

    def test_take_late_outside_five_minute_grace_blocks(self):
        p=self.create_plan()
        with self.assertRaisesRegex(CapturePlanBlocked,"TAKE_OUTSIDE"):
            self.check(p,now=NOW+timedelta(minutes=6,seconds=1))

    def test_wrong_markets_cannot_spend_quota(self):
        p=self.create_plan()
        with self.assertRaisesRegex(CapturePlanBlocked,"MARKET_SET_MISMATCH"):
            self.check(p,markets=("h2h",))

    def test_wrong_bookmakers_cannot_spend_quota(self):
        p=self.create_plan()
        with self.assertRaisesRegex(CapturePlanBlocked,"BOOK_SET_MISMATCH"):
            self.check(p,bookmakers=("draftkings",))

    def test_wrong_provider_event_id_rejected(self):
        p=self.create_plan()
        with self.assertRaisesRegex(CapturePlanBlocked,"NOT_IN_APPROVED_PLAN"):
            self.check(p,event_id="f"*32)

    def test_budget_blocked_plan_cannot_authorize_capture(self):
        p=self.create_plan(credits=5)
        with self.assertRaisesRegex(CapturePlanBlocked,"NOT_APPROVED_FOR_RESEARCH"):
            self.check(p)

    def test_rewritten_event_census_cannot_hide_original_event(self):
        p=self.create_plan()
        data=json.loads(p.read_text())
        data["events"]=[]
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(CapturePlanBlocked,"POPULATION_MISMATCH"):
            self.check(p)

    def test_rewritten_event_time_refused(self):
        p=self.create_plan()
        data=json.loads(p.read_text())
        data["events"][0]["close_at_utc"]=(self.kickoff-timedelta(minutes=3)).isoformat()
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(CapturePlanBlocked,"PHASE_CLOCK_MODIFIED"):
            self.check(p)

    def test_forged_extra_credits_or_cost_refused(self):
        p=self.create_plan()
        data=json.loads(p.read_text())
        data["estimated_credits_per_snapshot"]=1
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(CapturePlanBlocked,"QUOTA_OR_DENOMINATOR_INVALID"):
            self.check(p)

    def test_source_provider_catalog_tamper_refused(self):
        p=self.create_plan()
        data=json.loads(p.read_text())
        source=self.root/data["source_event_manifest_filename"]
        manifest=json.loads(source.read_text())
        (self.root/manifest["original_raw_filename"]).write_text('[]')
        with self.assertRaisesRegex(CapturePlanBlocked,"CATALOG_INTEGRITY_INVALID"):
            self.check(p)

    def test_symlinked_plan_refused(self):
        p=self.create_plan()
        link=self.root/"link.json"
        link.symlink_to(p)
        with self.assertRaisesRegex(CapturePlanBlocked,"NOT_REGULAR_PRIVATE_FILE"):
            self.check(link)

    def test_world_readable_plan_refused(self):
        p=self.create_plan()
        p.chmod(0o644)
        with self.assertRaisesRegex(CapturePlanBlocked,"PERMISSIONS_TOO_OPEN"):
            self.check(p)

    def test_plan_path_inside_public_checkout_refused(self):
        from sportsedge.odds import planned_capture_guard as module
        p=self.create_plan()
        with patch.object(module,"private_archive_root",side_effect=ValueError("RAW_ODDS_ARCHIVE_MUST_BE_OUTSIDE_PUBLIC_REPO")):
            with self.assertRaisesRegex(ValueError,"RAW_ODDS_ARCHIVE_MUST"):
                self.check(p)

    def test_prehttp_rejects_before_spending_even_with_valid_key(self):
        p=self.create_plan(credits=5)
        calls=[]
        def opener(req,timeout):
            calls.append(req.full_url)
            raise AssertionError("No network on failed plan")
        with self.assertRaisesRegex(CapturePlanBlocked,"NOT_APPROVED_FOR_RESEARCH"):
            capture_cycle("NFL",self.root,ID,"TAKE",markets=MARKETS,
                          bookmakers=BOOKS,key=KEY,opener=opener,plan_path=p)
        self.assertEqual(calls,[])

    def test_posthttp_changed_kickoff_preserves_raw_but_no_pricing_csv(self):
        from sportsedge.odds import prospective_clv_cycle as module
        kickoff=datetime.now(timezone.utc)+timedelta(minutes=60)
        changed=kickoff+timedelta(minutes=20)
        payload=[{
            **event(changed),
            "bookmakers":[{"key":"draftkings","markets":[{
                "key":"h2h",
                "last_update":(datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat(),
                "outcomes":[
                    {"name":"Home Team","price":-110},
                    {"name":"Away Team","price":+105},
                ],
            }]}],
        }]
        fake_plan={"expected_kickoff_utc":kickoff.isoformat(),
                   "plan_sha256":"sha256:"+"a"*64}
        with patch.object(module,"guard_plan",return_value=fake_plan) as checked:
            out=capture_cycle("NFL",self.root,ID,"TAKE",key=KEY,
                              opener=lambda req,timeout:Response(payload),
                              plan_path=self.root/"injected-plan.json")
        self.assertEqual(checked.call_count,1)
        self.assertEqual(out["state"],"BLOCK_PROVIDER_KICKOFF_CHANGED_FROM_APPROVED_PLAN")
        self.assertEqual(out["capture_plan_guard"],"BLOCK_KICKOFF_CHANGED")
        self.assertTrue((self.root/out["original_json_filename"]).is_file())
        self.assertTrue((self.root/out["original_manifest_filename"]).is_file())
        self.assertFalse(list(self.root.glob("*.take.csv")))
        self.assertEqual(out["official_counted"],0)

if __name__=="__main__":
    unittest.main()
