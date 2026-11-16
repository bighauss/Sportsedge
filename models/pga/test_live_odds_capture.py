import hashlib
import io
import json
import unittest
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qs
from live_odds_capture import capture

NOW=datetime(2026,11,15,10,tzinfo=timezone.utc)
class FakeResponse:
    def __init__(self,raw):self.raw=raw
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self,n):return self.raw
def opener(req,timeout):
    parts=urlsplit(req.full_url)
    args=parse_qs(parts.query)
    assert args["apiKey"]==["secret"]
    assert args["markets"]==["outrights"]
    raw=json.dumps([{"id":"event","commence_time":"2026-11-17T12:00:00Z",
       "bookmakers":[{"key":"draftkings","markets":[{"key":"outrights",
       "last_update":"2026-11-15T09:00:00Z",
       "outcomes":[{"name":"Golfer A","price":15.0}]}]}]}]).encode()
    return FakeResponse(raw)
class LiveCaptureTests(unittest.TestCase):
    def test_fake_http_contract_and_digest(self):
        r=capture("golf_masters_tournament_winner",api_key="secret",opener=opener,clock=lambda:NOW)
        self.assertEqual(hashlib.sha256(r["raw_bytes"]).hexdigest(),r["source_sha256"])
        self.assertEqual(len(r["parsed"]["rows"]),1)
        self.assertEqual(r["status"],"UNVERIFIED_PLAYER_MAPPING_PAPER_0U")
    def test_no_key_blocks_before_http(self):
        with self.assertRaisesRegex(ValueError,"ODDS_API_KEY_REQUIRED"):
            capture("golf_masters_tournament_winner",api_key="",opener=opener)
    def test_bad_market_blocks(self):
        with self.assertRaisesRegex(ValueError,"UNSUPPORTED_GOLF_MARKET"):
            capture("golf_weekly",api_key="secret",opener=opener)
    def test_bad_region_blocks(self):
        with self.assertRaisesRegex(ValueError,"INVALID_REGION"):
            capture("golf_masters_tournament_winner",api_key="secret",regions="evil",opener=opener)
    def test_bad_timeout_blocks(self):
        with self.assertRaisesRegex(ValueError,"INVALID_TIMEOUT"):
            capture("golf_masters_tournament_winner",api_key="secret",timeout=0,opener=opener)
    def test_provider_error_not_accepted(self):
        def bad(req,timeout):return FakeResponse(b'{"message":"invalid api key"}')
        with self.assertRaisesRegex(ValueError,"INVALID_PROVIDER_PAYLOAD"):
            capture("golf_masters_tournament_winner",api_key="secret",opener=bad,clock=lambda:NOW)
if __name__=="__main__":unittest.main()
