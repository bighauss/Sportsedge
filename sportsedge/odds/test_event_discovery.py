"""Synthetic, no-credential event discovery contracts."""
from __future__ import annotations

import csv
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from sportsedge.odds.event_discovery import discover_events
from sportsedge.odds.free_odds_aggregator_intake import SPORTS

KEY="SYNTHETIC_KEY_0123456789"
NOW=datetime(2026,11,15,20,0,tzinfo=timezone.utc)
IDENT="0123456789abcdef0123456789abcdef"


def event(sport="NFL",minutes=60,ident=IDENT):
    return {
        "id":ident,"sport_key":SPORTS[sport],
        "commence_time":(NOW+timedelta(minutes=minutes)).isoformat(),
        "home_team":"Home, Wildcats","away_team":"Away Eagles",
    }


class Response(io.BytesIO):
    status=200
    def __init__(self,data):
        super().__init__(data)
        self.headers={"Date":"Sun, 15 Nov 2026 20:00:00 GMT",
                      "x-requests-last":"0","x-requests-remaining":"500"}


def fake(payload,saw=None):
    raw=json.dumps(payload).encode()
    def opener(request,timeout):
        if saw is not None:
            saw.append(request.full_url)
        assert timeout==25
        assert request.full_url.startswith("https://api.the-odds-api.com/v4/sports/")
        assert request.full_url.endswith("dateFormat=iso")
        assert "apiKey="+KEY in request.full_url
        assert "/events?" in request.full_url and "/odds?" not in request.full_url
        return Response(raw)
    return opener


class DiscoverTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)/"private"

    def run_discovery(self,payload=None,sport="NFL",**kwargs):
        if payload is None:
            payload=[event(sport)]
        return discover_events(
            sport,self.root,key=kwargs.pop("key",KEY),
            opener=kwargs.pop("opener",fake(payload)),
            now=kwargs.pop("now",NOW),**kwargs,
        )

    def test_event_id_catalog_raw_archive_and_0600(self):
        saw=[]
        result=self.run_discovery(opener=fake([event()],saw))
        self.assertEqual(len(saw),1)
        self.assertEqual(result["events_returned"],1)
        self.assertEqual(result["upcoming_pregame_events"],1)
        self.assertEqual(result["provider_credits_last_claim"],"0")
        self.assertFalse(result["has_bookmaker_prices"])
        self.assertEqual(result["official_counted"],0)
        self.assertEqual(result["approved_stake_u"],0)
        self.assertTrue(result["source_event_ids_provider_claim_only"])
        self.assertEqual(result["events"][0]["source_event_id"],IDENT)
        self.assertEqual(result["events"][0]["suggested_close_capture_utc"],
                         (NOW+timedelta(minutes=55)).isoformat())
        raw=(self.root/result["original_raw_filename"]).read_bytes()
        self.assertEqual("sha256:"+sha256(raw).hexdigest(),result["original_raw_sha256"])
        for item in self.root.iterdir():
            self.assertEqual(item.stat().st_mode & 0o777,0o600)
            self.assertNotIn(KEY,item.read_text())
        with (self.root/result["catalog_filename"]).open(newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(rows[0]["home_team"],"Home, Wildcats")
        self.assertEqual(rows[0]["source_event_id"],IDENT)

    def test_all_six_provider_sport_keys(self):
        self.assertEqual(set(SPORTS),{"NFL","CFB","CBB","NBA","MLB","NHL"})
        for sport in SPORTS:
            with self.subTest(sport=sport):
                out=self.run_discovery(sport=sport)
                self.assertEqual(out["sport"],sport)
                self.assertEqual(out["events"][0]["sport"],sport)

    def test_live_event_kept_but_never_suggested_pregame(self):
        out=self.run_discovery(payload=[event(minutes=-10)])
        self.assertEqual(out["upcoming_pregame_events"],0)
        self.assertEqual(out["live_or_started_events"],1)
        self.assertEqual(out["events"][0]["capture_state"],"ALREADY_STARTED_NO_PREGAME")
        self.assertEqual(out["events"][0]["suggested_close_capture_utc"],"")

    def test_empty_feed_is_preserved_not_fabricated(self):
        out=self.run_discovery(payload=[])
        self.assertEqual(out["events"],[])
        self.assertEqual(out["events_returned"],0)
        self.assertTrue((self.root/out["catalog_filename"]).exists())

    def test_two_events_sorted_by_start_and_id(self):
        earlier=event(minutes=10,ident="b"*32)
        later=event(minutes=60)
        out=self.run_discovery(payload=[later,earlier])
        self.assertEqual([x["source_event_id"] for x in out["events"]],
                         ["b"*32,IDENT])

    def test_duplicate_event_id_fails_all_copies(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_PROVIDER_EVENT_ID"):
            self.run_discovery(payload=[event(),event()])
        self.assertFalse(self.root.exists())

    def test_wrong_sport_and_empty_teams_fail(self):
        with self.assertRaisesRegex(ValueError,"EVENT_SPORT_MISMATCH"):
            self.run_discovery(payload=[event("NBA")])
        self.assertFalse(self.root.exists())
        bad=event();bad["home_team"]=""
        with self.assertRaisesRegex(ValueError,"EVENT_TEAMS_INVALID"):
            self.run_discovery(payload=[bad])

    def test_bad_event_clock_and_id_rejected(self):
        bad=event();bad["commence_time"]="not UTC"
        with self.assertRaisesRegex(ValueError,"START_TIMESTAMP_INVALID"):
            self.run_discovery(payload=[bad])
        bad=event();bad["id"]="guess"
        with self.assertRaisesRegex(ValueError,"PROVIDER_EVENT_ID_INVALID"):
            self.run_discovery(payload=[bad])

    def test_api_key_required_before_http(self):
        contacted=[]
        def forbidden(*args,**kw):
            contacted.append(True)
            raise AssertionError("Do not call provider")
        with self.assertRaisesRegex(ValueError,"USER_API_KEY_MISSING_OR_UNSAFE"):
            self.run_discovery(key="",opener=forbidden)
        self.assertFalse(contacted)
        self.assertFalse(self.root.exists())

    def test_public_repo_dest_refused_before_http(self):
        from sportsedge.odds import event_discovery
        contacted=[]
        def forbidden(*args,**kw):
            contacted.append(True)
            raise AssertionError("Do not call provider")
        with self.assertRaisesRegex(ValueError,"RAW_ODDS_ARCHIVE_MUST_BE_OUTSIDE_PUBLIC_REPO"):
            discover_events("NFL",event_discovery.__file__,key=KEY,opener=forbidden,now=NOW)
        self.assertFalse(contacted)

    def test_redirect_response_rejected_without_storing_key(self):
        class Redirect(Response):
            def geturl(self):
                return "https://wrong.host/redirect"
        with self.assertRaisesRegex(ValueError,"DISCOVERY_REDIRECT_REFUSED"):
            self.run_discovery(opener=lambda req,timeout: Redirect(b"[]"))
        self.assertFalse(self.root.exists())

    def test_http_error_redacts_secret_url(self):
        def forbidden(req,timeout):
            raise HTTPError(req.full_url,401,"contains:"+KEY,{},None)
        with self.assertRaisesRegex(ValueError,"DISCOVERY_HTTP_ERROR_CODE:401") as ctx:
            self.run_discovery(opener=forbidden)
        self.assertNotIn(KEY,str(ctx.exception))
        self.assertFalse(self.root.exists())

    def test_provider_body_echoing_key_refused(self):
        def echo(req,timeout):
            return Response(('["'+KEY+'"]').encode())
        with self.assertRaisesRegex(ValueError,"DISCOVERY_RESPONSE_ECHOED_API_KEY"):
            self.run_discovery(opener=echo)
        self.assertFalse(self.root.exists())

    def test_duplicate_json_object_keys_blocked(self):
        def bad(req,timeout):
            return Response(b'[{"sport_key":"x","sport_key":"y"}]')
        with self.assertRaisesRegex(ValueError,"DUPLICATE_PROVIDER_JSON_KEY"):
            self.run_discovery(opener=bad)
        self.assertFalse(self.root.exists())

    def test_defaults_use_secure_no_redirect_transport(self):
        from sportsedge.odds import event_discovery as module
        with patch.object(module,"_secure_open",side_effect=ValueError("INTERCEPTED")) as opened:
            with self.assertRaisesRegex(ValueError,"INTERCEPTED"):
                discover_events("NFL",self.root,key=KEY,now=NOW)
        self.assertEqual(opened.call_count,1)

    def test_manifest_write_failure_rolls_back_private_owned_raw(self):
        from sportsedge.odds import event_discovery as module
        original=module._write_private
        def fail_manifest(path,data):
            if str(path).endswith(".manifest.json"):
                raise OSError("injected disk failure")
            return original(path,data)
        with patch.object(module,"_write_private",side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError,"injected disk failure"):
                self.run_discovery()
        self.assertTrue(self.root.exists())
        self.assertEqual(list(self.root.iterdir()),[])

    def test_clock_must_be_aware_utc(self):
        contacted=[]
        def no_call(req,timeout):
            contacted.append(True)
            raise AssertionError()
        with self.assertRaisesRegex(ValueError,"CLOCK_MUST_BE_UTC"):
            self.run_discovery(opener=no_call,now=datetime(2026,11,15,20,0))
        self.assertFalse(contacted)

    def test_untrusted_quota_headers_never_written(self):
        class BadHeaders(Response):
            def __init__(self,raw):
                super().__init__(raw)
                self.headers["x-requests-last"]="secret_"+KEY
        out=self.run_discovery(opener=lambda req,timeout:BadHeaders(json.dumps([event()]).encode()))
        self.assertIsNone(out["provider_credits_last_claim"])
        self.assertNotIn(KEY,(self.root/out["manifest_filename"]).read_text())

if __name__=="__main__":
    unittest.main()
