import hashlib
import unittest
from datetime import datetime,timezone
from urllib.parse import urlsplit,parse_qs
from datagolf_client import capture

class Response:
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self,n):return b'{"players":[]}'
def fake(req,timeout):
    q=parse_qs(urlsplit(req.full_url).query)
    assert q["key"]==["fake-secret"]
    assert q["file_format"]==["json"]
    assert "feeds.datagolf.com" in req.full_url
    return Response()
class DataGolfTests(unittest.TestCase):
    def test_authorized_capture(self):
        r=capture("player_list",api_key="fake-secret",opener=fake,
                  clock=lambda:datetime(2026,11,15,tzinfo=timezone.utc))
        self.assertEqual(r["source_sha256"],hashlib.sha256(r["raw_bytes"]).hexdigest())
        self.assertEqual(r["status"],"PROVIDER_RESPONSE_UNVERIFIED_PAPER_0U")
    def test_missing_key(self):
        with self.assertRaisesRegex(ValueError,"DATAGOLF_API_KEY_REQUIRED"):
            capture("player_list",api_key="",opener=fake)
    def test_unrecognized_endpoint(self):
        with self.assertRaisesRegex(ValueError,"UNKNOWN_DATAGOLF_ENDPOINT"):
            capture("delete-all",api_key="fake-secret",opener=fake)
    def test_reject_unknown_parameter(self):
        with self.assertRaisesRegex(ValueError,"UNSUPPORTED_PARAMETER"):
            capture("player_list",api_key="fake-secret",params={"evil":"x"},opener=fake)
    def test_require_book_and_market(self):
        with self.assertRaisesRegex(ValueError,"MARKET_AND_BOOK_REQUIRED"):
            capture("historical_outrights",api_key="fake-secret",opener=fake)
    def test_require_round_coordinates(self):
        with self.assertRaisesRegex(ValueError,"ROUND_EVENT_YEAR_REQUIRED"):
            capture("rounds",api_key="fake-secret",opener=fake)
    def test_prevent_parameter_injection(self):
        with self.assertRaisesRegex(ValueError,"INVALID_PARAMETER_VALUE"):
            capture("schedule",api_key="fake-secret",params={"tour":"pga&key=other"},opener=fake)
    def test_reject_timeout(self):
        with self.assertRaisesRegex(ValueError,"INVALID_TIMEOUT"):
            capture("schedule",api_key="fake-secret",timeout=0,opener=fake)

if __name__=="__main__":unittest.main()
