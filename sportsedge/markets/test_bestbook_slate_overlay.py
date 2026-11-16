"""Synthetic RUN IT + BestBook public-reference integration tests. No live odds."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sportsedge.markets.bestbook_slate_overlay import (
    BestBookSlateError, MAP_SCHEMA, _reference_match,
    apply_bestbook_public_reference,
)
from sportsedge.markets.slate_orchestrator import run_slate, main
from sportsedge.markets.test_slate_orchestrator import fixture
from sportsedge.odds.bestbook_public_reference import analyze

PAGE = b"""Best NFL odds this week
Buffalo Bills at New York Jets odds
Sun, Nov 15, 1:00 PM ET
Spread: BUF -7.5 -102 at Novig; NYJ +7.5 +100 at FanDuel
Total: over 50.5 -102 at Bet105; under 50.5 +100 at Novig
Moneyline: BUF -388 at Novig; NYJ +380 at FanDuel
"""
LABEL = "Buffalo Bills at New York Jets odds"


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def mapping():
    return {
        "schema": MAP_SCHEMA,
        "events": [{
            "sport": "NFL",
            "event_id": "NFL-E2",
            "public_event_label": LABEL,
            "away_selection": "BUF",
            "home_selection": "NYJ",
        }],
    }


def report(when=None):
    return analyze(PAGE, read_at_utc=when or utcnow()-timedelta(minutes=1))


def setup(now=None):
    now = now or utcnow()
    slate = run_slate(fixture(), now=now)
    return slate, report(now-timedelta(minutes=1)), now


class BestBookSlateIntegration(unittest.TestCase):
    def test_public_source_attaches_to_existing_nfl_event_only(self):
        slate, source, now = setup()
        enhanced = apply_bestbook_public_reference(slate, source, mapping(), now_utc=now)
        self.assertNotIn("bestbook_public_research", slate)
        nfl = next(x for x in enhanced["events"] if x["sport"] == "NFL")
        cbb = next(x for x in enhanced["events"] if x["sport"] == "CBB")
        self.assertEqual(nfl["bestbook_public_research"]["status"],
                         "PAPER_PUBLIC_REFERENCE_MATCHED_IDENTITY_UNVERIFIED")
        self.assertEqual(len(nfl["bestbook_public_research"]["quoted_references"]), 6)
        self.assertEqual(nfl["bestbook_public_research"]["market_family_coverage"]["ML"],
                         "PUBLIC_RESEARCH_BEST_PRICE_NOT_BOOK_ORIGINAL")
        self.assertEqual(nfl["bestbook_public_research"]["market_family_coverage"]["PLAYER_PROP"],
                         "NOT_CAPTURED_IN_PUBLIC_BESTBOOK_VIEW")
        self.assertEqual(cbb["bestbook_public_research"]["status"],
                         "SPORT_NOT_PRESENT_ON_PUBLIC_BESTBOOK_HOMEPAGE")
        self.assertEqual(enhanced["approved_stake_u"], 0)
        self.assertIsNone(enhanced["card"])
        self.assertFalse(enhanced["bestbook_public_research"]["book_independent_origins_verified"])

    def test_existing_pricing_and_guards_unchanged(self):
        original, source, now = setup()
        integrated = run_slate(fixture(), now=now, bestbook_report=source,
                               bestbook_event_map=mapping())
        # No BestBook quote is sent to the DK pricer, model or v2.1 risk gate.
        for basic, enriched in zip(original["events"], integrated["events"]):
            for name in ("research_priced", "research_blocked", "status", "approved_stake_u",
                         "official_counted", "research_candidates"):
                self.assertEqual(basic[name], enriched[name])
            self.assertEqual(basic.get("research_rows"), enriched.get("research_rows"))
        self.assertEqual(original["counts"], integrated["counts"])
        self.assertEqual(integrated["status"] if "status" in integrated else
                         integrated["state"], "BLOCK_OFFICIAL_RELEASE_RESEARCH_ONLY")

    def test_exact_market_side_and_line_only(self):
        _, source, _ = setup()
        offers = source["rows"]
        map_item = mapping()["events"][0]
        market = ("NFL", "NFL-E2", "SPREAD", "FG", "HOME", "7.5",
                  "", "", "", "REGULATION")
        match, reason = _reference_match(market, map_item, offers)
        self.assertEqual(match["displayed_book_label"], "FanDuel")
        self.assertEqual(match["displayed_price_american"], 100)
        self.assertEqual(match["source_kind"], "BESTBOOK_PUBLIC_BEST_PRICE_NOT_DK_ORIGINAL")
        self.assertEqual(match["approved_stake_u"], 0)
        self.assertIn("NOT_AUTHENTICATED", reason)
        alternate = list(market)
        alternate[5] = "6.5"
        self.assertIsNone(_reference_match(alternate, map_item, offers)[0])
        alternate[5] = "7.5"
        alternate[3] = "1H"
        self.assertIsNone(_reference_match(alternate, map_item, offers)[0])

    def test_same_public_best_price_cannot_assert_draftkings(self):
        _, source, _ = setup()
        map_item = mapping()["events"][0]
        matched, _ = _reference_match(
            ("NFL","NFL-E2","ML","FG","HOME","","","","","REGULATION"),
            map_item, source["rows"])
        self.assertIsNotNone(matched)
        self.assertEqual(matched["displayed_book_label"], "FanDuel")
        self.assertIsNone(matched["external_provider_quote_id"])
        self.assertIsNone(matched["provider_publication_utc"])
        self.assertFalse(matched["source_authentication_verified"])

    def test_stale_page_does_not_match_research_candidates(self):
        slate, source, now = setup()
        source["local_page_read_utc"] = (now-timedelta(hours=1)).isoformat().replace("+00:00","Z")
        enriched = apply_bestbook_public_reference(slate, source, mapping(), now_utc=now)
        nfl = next(x for x in enriched["events"] if x["sport"] == "NFL")
        self.assertEqual(nfl["bestbook_public_research"]["status"],
                         "PUBLIC_REFERENCE_STALE_GT_300S")

    def test_future_timestamp_rejected(self):
        slate, source, now = setup()
        source["local_page_read_utc"]=(now+timedelta(hours=1)).isoformat().replace("+00:00","Z")
        with self.assertRaisesRegex(BestBookSlateError, "PUBLIC_PAGE_CAPTURE_IN_FUTURE"):
            apply_bestbook_public_reference(slate, source, mapping(), now_utc=now)

    def test_poststart_reference_blocked_even_if_page_captured_before_game(self):
        slate, source, now = setup()
        # Simulate earlier event kickoff while preserving same slate.
        nfl = next(x for x in slate["events"] if x["sport"] == "NFL")
        nfl["start_utc"]=(now-timedelta(minutes=1)).isoformat()
        enhanced=apply_bestbook_public_reference(slate, source, mapping(), now_utc=now)
        self.assertEqual(next(x for x in enhanced["events"] if x["sport"]=="NFL")[
            "bestbook_public_research"]["status"],"PUBLIC_REFERENCE_POST_START_OR_LIVE")

    def test_mapping_absent_not_silently_accepted(self):
        slate, source, now=setup()
        with self.assertRaisesRegex(ValueError, "BESTBOOK_EVENT_IDENTITY_MAPPING_REQUIRED"):
            run_slate(fixture(), now=now, bestbook_report=source)

    def test_duplicate_public_map_refused(self):
        slate, source, now=setup()
        bad=mapping()
        bad["events"].append(dict(bad["events"][0]))
        with self.assertRaisesRegex(BestBookSlateError,"DUPLICATE_MANUAL_EVENT_MAPPING"):
            apply_bestbook_public_reference(slate,source,bad,now_utc=now)

    def test_fake_or_mismatched_event_id_rejected(self):
        slate, source, now=setup()
        bad=mapping()
        bad["events"][0]["event_id"]="SOME-OTHER-EVENT"
        with self.assertRaisesRegex(BestBookSlateError,"MAPPED_EVENT_NOT_ON_RUN_IT_SLATE"):
            apply_bestbook_public_reference(slate,source,bad,now_utc=now)

    def test_cross_sport_map_cannot_use_nfl_pricing_for_cbb(self):
        slate, source, now=setup()
        bad=mapping()
        bad["events"][0].update(sport="CBB",event_id="GAME-1")
        with self.assertRaisesRegex(BestBookSlateError,"UNSUPPORTED_OR_EMPTY_PUBLIC_EVENT_MAP"):
            apply_bestbook_public_reference(slate,source,bad,now_utc=now)

    def test_forged_authenticated_report_rejected(self):
        slate, source, now=setup()
        bad=dict(source,source_account_authenticated=True)
        with self.assertRaisesRegex(BestBookSlateError,"BESTBOOK_REPORT_MUST_REMAIN_UNVERIFIED_0U"):
            apply_bestbook_public_reference(slate,bad,mapping(),now_utc=now)

    def test_report_with_fake_positive_units_or_quote_timestamp_rejected(self):
        slate, source, now=setup()
        bad=deepcopy(source)
        bad["rows"][0]["approved_stake_u"]=1
        with self.assertRaisesRegex(BestBookSlateError,"MALFORMED_OR_PROMOTED_PUBLIC_ROW"):
            apply_bestbook_public_reference(slate,bad,mapping(),now_utc=now)
        bad=deepcopy(source)
        bad["rows"][0]["provider_original_quote_utc"]=now.isoformat()
        with self.assertRaisesRegex(BestBookSlateError,"MALFORMED_OR_PROMOTED_PUBLIC_ROW"):
            apply_bestbook_public_reference(slate,bad,mapping(),now_utc=now)

    def test_map_no_match_keeps_public_event_label_unmatched(self):
        slate, source, now=setup()
        enriched=apply_bestbook_public_reference(slate,source,
            {"schema":MAP_SCHEMA,"events":[]},now_utc=now)
        self.assertIn(LABEL,enriched["bestbook_public_research"]["unmapped_public_event_labels"])
        nfl=next(e for e in enriched["events"] if e["sport"]=="NFL")
        self.assertEqual(nfl["bestbook_public_research"]["status"],
                         "NO_EXACT_PUBLIC_EVENT_IDENTITY_MAPPING")

    def test_duplicate_result_event_refused(self):
        slate, source, now=setup()
        slate["events"].append(deepcopy(slate["events"][0]))
        with self.assertRaisesRegex(BestBookSlateError,"DUPLICATE_SCHEDULE_EVENT_IN_OUTPUT"):
            apply_bestbook_public_reference(slate,source,mapping(),now_utc=now)

    def test_private_cli_uses_original_html_and_event_map(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            root.chmod(0o700)
            slab=root/"slate.json"
            page=root/"public_page.html"
            mapfile=root/"bestbook_map.json"
            dest=root/"slate_result.json"
            slab.write_text(json.dumps(fixture()))
            slab.chmod(0o600)
            page.write_bytes(PAGE)
            page.chmod(0o600)
            mapfile.write_text(json.dumps(mapping()))
            mapfile.chmod(0o600)
            self.assertEqual(main([str(slab),str(dest),"--bestbook-page",str(page),
                                   "--bestbook-event-map",str(mapfile)]),0)
            result=json.loads(dest.read_text())
            self.assertEqual(result["approved_stake_u"],0)
            self.assertFalse(result["source_authentication_verified"])
            self.assertEqual(result["bestbook_public_research"]["counts"]["mapped_nfl_events"],1)
            self.assertEqual(dest.stat().st_mode&0o077,0)
            with self.assertRaises(FileExistsError):
                main([str(slab),str(dest),"--bestbook-page",str(page),
                      "--bestbook-event-map",str(mapfile)])

    def test_cli_requires_page_and_map_together(self):
        with self.assertRaisesRegex(ValueError,"BESTBOOK_SOURCE_AND_EXPLICIT_EVENT_MAP_REQUIRED_TOGETHER"):
            main(["/tmp/nope.json","/tmp/out.json","--bestbook-page","/tmp/bestbook.html"])

    def test_private_cli_rejects_world_readable_bestbook_snapshot(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            root.chmod(0o700)
            slab=root/"slate.json"
            page=root/"public_page.html"
            mapfile=root/"bestbook_map.json"
            dest=root/"slate_result.json"
            slab.write_text(json.dumps(fixture()))
            slab.chmod(0o600)
            page.write_bytes(PAGE)
            page.chmod(0o644)
            mapfile.write_text(json.dumps(mapping()))
            mapfile.chmod(0o600)
            with self.assertRaisesRegex(ValueError,"PRIVATE_PAGE_FILE_0600_REQUIRED"):
                main([str(slab),str(dest),"--bestbook-page",str(page),
                      "--bestbook-event-map",str(mapfile)])
            self.assertFalse(dest.exists())


if __name__=="__main__":
    unittest.main()
