import io
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.error import HTTPError

from sportsedge.odds.free_odds_aggregator_intake import capture, strict_json, SPORTS

KEY='TEST_FREE_TIER_API_KEY_123456789'
EVENT='0123456789abcdef0123456789abcdef'


def event(start=None,sport='americanfootball_nfl'):
    t=start or (datetime.now(timezone.utc)+timedelta(days=2))
    return {'id':EVENT,'sport_key':sport,'commence_time':t.isoformat(),
         'home_team':'Baltimore Ravens','away_team':'Los Angeles Chargers',
         'bookmakers':[{'key':book,'markets':[
             {'key':'h2h','last_update':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
              'outcomes':[{'name':'Baltimore Ravens','price':-110},
                          {'name':'Los Angeles Chargers','price':+110}]}]}
          for book in ('draftkings','fanduel')]}


class Response(io.BytesIO):
    def __init__(self,bytes_):
        super().__init__(bytes_)
        self.headers={'Date':'Sun, 15 Nov 2026 22:31:00 GMT',
                      'x-requests-remaining':'400','x-requests-last':'1'}


def opener_for(payload):
    raw=json.dumps(payload).encode()
    def opener(request,timeout):
        assert timeout<=30
        assert 'apiKey='+KEY in request.full_url
        return Response(raw)
    return opener


class OddsAPIIntakeTests(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory();self.addCleanup(self.d.cleanup)
        self.root=Path(self.d.name)/'restricted'

    def run_capture(self,payload=None,**kw):
        return capture(kw.pop('sport','NFL'),self.root,key=kw.pop('key',KEY),
                       opener=kw.pop('opener',opener_for([event()] if payload is None else payload)),**kw)

    def test_two_book_research_never_upstream_auth(self):
        out=self.run_capture()
        self.assertEqual(out['events_returned'],1)
        self.assertEqual(out['outcomes_returned'],4)
        self.assertFalse(out['bookmakers_are_independently_authenticated'])
        self.assertEqual(out['official_counted'],0)
        self.assertEqual(out['approved_stake_u'],0)
        self.assertIn('spreads',out['missing_requested_market_keys_unverified'])
        self.assertIn('totals',out['missing_requested_market_keys_unverified'])
        p=self.root/out['raw_filename'];self.assertTrue(p.is_file())
        self.assertNotIn(KEY,(self.root/(p.stem+'.manifest.json')).read_text())

    def test_after_start_raw_is_retained_but_blocked(self):
        out=self.run_capture([event(datetime.now(timezone.utc)-timedelta(minutes=1))])
        self.assertEqual(out['live_poststart_outcomes_blocked'],4)
        self.assertEqual(out['official_counted'],0)

    def test_missing_key_rejected(self):
        with self.assertRaisesRegex(ValueError,'USER_API_KEY_MISSING_OR_UNSAFE'):
            self.run_capture(key='')

    def test_event_mismatch_blocks(self):
        with self.assertRaisesRegex(ValueError,'EVENT_ID_RESPONSE_MISMATCH'):
            self.run_capture(event_id='b'*32)

    def test_cbb_key(self):
        e=event(sport='basketball_ncaab')
        out=self.run_capture([e],sport='CBB')
        self.assertEqual(out['sport'],'CBB')

    def test_invalid_market_name_rejected(self):
        with self.assertRaises(ValueError):
            self.run_capture(markets=('h2h','../secret'))

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE_PROVIDER_JSON_KEY'):
            strict_json(b'{"x":1,"x":2}')

    def test_duplicate_outcome_rejected(self):
        e=event();e['bookmakers'][0]['markets'][0]['outcomes'].append(
            dict(e['bookmakers'][0]['markets'][0]['outcomes'][0]))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_AGGREGATOR_OUTCOME'):
            self.run_capture([e])

    def test_secret_echo_refused(self):
        def echo(req,timeout):return Response(('"'+KEY+'"').encode())
        with self.assertRaisesRegex(ValueError,'AGGREGATOR_ECHOED_SECRET'):
            self.run_capture(opener=echo)
        self.assertFalse(self.root.exists())

    def test_http_error_does_not_expose_key(self):
        def fail(req,timeout):
            raise HTTPError(req.full_url,401,'secret_url:'+KEY,{},None)
        with self.assertRaises(ValueError) as ctx:self.run_capture(opener=fail)
        self.assertEqual(str(ctx.exception),'AGGREGATOR_HTTP_ERROR_CODE:401')
        self.assertNotIn(KEY,str(ctx.exception))

    def test_bad_provider_market_key_rejected(self):
        e=event();e['bookmakers'][0]['markets'][0]['key']='unknown'
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_MARKET'):
            self.run_capture([e])

    def test_negative_american_value_allowed_if_valid(self):
        e=event();e['bookmakers'][0]['markets'][0]['outcomes'][0]['price']=-120
        self.assertEqual(self.run_capture([e])['outcomes_returned'],4)

    def test_old_market_timestamp_is_quarantined(self):
        e=event()
        for book in e['bookmakers']:
            book['markets'][0]['last_update']=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
        out=self.run_capture([e])
        self.assertEqual(out['stale_or_missing_aggregator_market_timestamp_outcomes'],4)
        self.assertEqual(out['approved_stake_u'],0)

    def test_empty_response_not_a_clean_card(self):
        out=self.run_capture([])
        self.assertEqual(out['state'],'BLOCK_EMPTY_AGGREGATOR_RESPONSE')
        self.assertEqual(out['outcomes_returned'],0)

    def test_provider_weeks_not_certified(self):
        out=self.run_capture()
        self.assertFalse(out['original_source_chain_certified'])
        self.assertEqual(out['matched_clv_triplets'],0)


if __name__=='__main__':unittest.main()
