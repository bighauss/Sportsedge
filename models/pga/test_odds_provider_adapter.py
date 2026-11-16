import unittest
from odds_provider_adapter import parse_outrights

def data(price=3.5, updated="2026-11-14T10:00:00Z"):
    return [dict(id="evt1",commence_time="2026-11-16T12:00:00Z",
                 bookmakers=[dict(key="draftkings",markets=[
                     dict(key="outrights",last_update=updated,
                          outcomes=[dict(name="Golfer A",price=price)])])])]
def run(payload=None,**kw):
    args=dict(sport_key="golf_masters_tournament_winner",
              captured_utc="2026-11-15T10:00:00Z",asof_utc="2026-11-15T10:00:00Z")
    args.update(kw)
    return parse_outrights(data() if payload is None else payload,**args)
class TestOddsAdapter(unittest.TestCase):
    def test_valid_quote_still_unverified(self):
        r=run();self.assertEqual(len(r["rows"]),1)
        self.assertEqual(r["rows"][0]["status"],"UNVERIFIED_ID_AND_PROVIDER")
        self.assertEqual(r["status"],"PAPER_0U_NO_MODEL_EDGE")
    def test_future_quote_rejected(self):
        self.assertEqual(run(data(updated="2026-11-15T11:00:00Z"))["rows"],[])
    def test_invalid_price(self):
        for price in (1.0,float("nan"),True):
            with self.subTest(price=price):
                self.assertEqual(run(data(price))["rows"],[])
    def test_poststart(self):
        self.assertEqual(run(captured_utc="2026-11-17T10:00:00Z",asof_utc="2026-11-17T10:00:00Z")["rows"],[])
    def test_unsupported_market(self):
        with self.assertRaisesRegex(ValueError,"UNSUPPORTED_GOLF_MARKET"):
            run(sport_key="golf_regular_tour")
    def test_capture_after_asof(self):
        with self.assertRaisesRegex(ValueError,"CAPTURE_AFTER_ASOF"):
            run(asof_utc="2026-11-14T10:00:00Z")
    def test_invalid_payload(self):
        with self.assertRaisesRegex(ValueError,"INVALID_PAYLOAD"):
            run(payload={})
    def test_missing_identity(self):
        p=data();p[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["name"]=""
        self.assertEqual(run(p)["rows"],[])
if __name__=="__main__":
    unittest.main()
