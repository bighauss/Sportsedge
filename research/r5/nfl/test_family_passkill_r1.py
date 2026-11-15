#!/usr/bin/env python3
"""Synthetic-only acceptance: no historical sports outcomes asserted."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from sportsedge_family_passkill_r1 import evaluate
from sportsedge_close_pair_r2 import key, pow_devig

T_CAPTURE='2026-11-12T16:00:00-06:00'
T_PRE='2026-11-12T16:01:00-06:00'
T_CLOSE='2026-11-12T16:30:00-06:00'
T_START='2026-11-12T17:00:00-06:00'
QUOTE=['sport','home','away','player','team','market','line','sgp','side','price_a','price_b']

def write(path, data):
    headers=list(data[0])
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(data)

def prepare(folder, n, entry_a='+110', entry_b='-130', close_a='-110', close_b='-110', result=None, double_alt=False):
    raw_e=[];raw_c=[];counted=[]; pairs=[]
    for i in range(n):
        base={'sport':'NFL','home':f'HOME_{i}','away':f'AWAY_{i}',
              'player':'','team':'','market':'ML','line':'0','sgp':'','side':''}
        raw_e.append({**base,'price_a':entry_a,'price_b':entry_b})
        raw_c.append({**base,'price_a':close_a,'price_b':close_b})
    ep=folder/'entry.csv';cp=folder/'close.csv';pp=folder/'pairs.csv';ip=folder/'counted.csv';op=folder/'report.json'
    write(ep,raw_e);write(cp,raw_c)
    de=hashlib.sha256(ep.read_bytes()).hexdigest(); dc=hashlib.sha256(cp.read_bytes()).hexdigest()
    for i,(a,b) in enumerate(zip(raw_e,raw_c)):
        k=key(a);pa,pb=pow_devig(int(b['price_a']),int(b['price_b']))
        token=json.dumps({'close_sha256':dc,'identity':k,'line':a['line'],
                          'quote_a':int(b['price_a']),'quote_b':int(b['price_b'])},sort_keys=True,separators=(',',':'))
        sha=hashlib.sha256(token.encode()).hexdigest()
        market_key='|'.join(str(a[v]).casefold() for v in ('sport','away','home','market','line','player','team','sgp','side'))
        pairs.append({**{x:a[x] for x in QUOTE[:-2]},'market_key':market_key,
                      'entry_price_a':int(entry_a),'entry_price_b':int(entry_b),
                      'close_price_a':int(close_a),'close_price_b':int(close_b),
                      'p_devig_a':round(pa,12),'p_devig_b':round(pb,12),
                      'entry_file_sha256':de,'close_file_sha256':dc,
                      'close_asof_utc':T_CLOSE,'start_utc':T_START,
                      'verification':'PRE_GAME_IDENTICAL_MARKET_AND_LINE','close_pair_sha256':sha})
        counted.append({'sport':'NFL','game':f'AWAY_{i} @ HOME_{i}','bet_type':'ML|0',
                        'price':entry_a,'receipt_result':('W' if i%3 != 0 else 'L') if result is None else result,
                        'receipt_market_key':market_key,'receipt_close_pair_sha256':sha,
                        'receipt_closing_price_american':close_a,'receipt_close_p_devig':round(pa,12),
                        'receipt_close_line_matched':'YES','receipt_close_book':'DK',
                        'receipt_start_ct':T_START,'receipt_captured_ct':T_CAPTURE,
                        'precommit_ct':T_PRE,'evidence_label':'COUNTED_PRECOMMITTED_CANDIDATE',
                        'cohort_id':f'2026-11-12-NFL-{i}'})
    if double_alt:
        counted.append(dict(counted[0]))
    write(pp,pairs);write(ip,counted)
    return ip,pp,cp,ep,op

class TestPassKill(unittest.TestCase):
    def run_case(self,n,**kwargs):
        t=tempfile.TemporaryDirectory(); folder=Path(t.name)
        a=prepare(folder,n,**kwargs)
        z=evaluate(*a,draws=10_000,seed=20261110)
        return t,folder,a,z
    def test_pass_requires_positive_clv_and_roi_not_wholly_negative(self):
        t,folder,a,z=self.run_case(310)
        try:
            f=z['families']['NFL|ML']
            self.assertEqual(f['label'],'PASS')
            self.assertEqual(f['independent_game_clusters'],310)
            self.assertGreater(f['uncertainty']['clv_95ci'][0],0)
        finally:t.cleanup()
    def test_kill_candidate(self):
        t,folder,a,z=self.run_case(160,entry_a='-130',entry_b='+110',close_a='+110',close_b='-130',result='L')
        try:
            f=z['families']['NFL|ML']
            self.assertEqual(f['label'],'KILL-CANDIDATE')
            self.assertLess(f['uncertainty']['clv_95ci'][1],0)
        finally:t.cleanup()
    def test_insufficient(self):
        t,folder,a,z=self.run_case(40)
        try:self.assertIsNone(z['families']['NFL|ML']['label'])
        finally:t.cleanup()
    def test_alt_ladder_not_multicounted(self):
        t,folder,a,z=self.run_case(5,double_alt=True)
        try:
            self.assertEqual(z['families']['NFL|ML']['independent_game_clusters'],4)
            self.assertGreater(z['rejected_reasons']['MULTIPLE_RUNG_OR_OPINIONS_SAME_GAME_MARKET'],0)
        finally:t.cleanup()
    def test_raw_price_tamper_fails_closed(self):
        t,folder,a,z=self.run_case(4)
        try:
            ip,pp,cp,ep,op=a
            raw=cp.read_text().replace('-110,-110','+110,-110',1)
            cp.write_text(raw)
            with self.assertRaisesRegex(ValueError,'CLOSE_FILE_OR_PAIR_UNVERIFIED'):
                evaluate(ip,pp,cp,ep,op,draws=20)
        finally:t.cleanup()
    def test_mismatched_entry_price_refused(self):
        t,folder,a,z=self.run_case(3)
        try:
            ip,pp,cp,ep,op=a
            with ip.open() as f:v=list(csv.DictReader(f))
            v[0]['price']='+125';write(ip,v)
            r=evaluate(ip,pp,cp,ep,op,draws=20)
            self.assertEqual(r['admitted_after_dedupe'],2)
            self.assertEqual(r['rejected_reasons']['ENTRY_PRICE_NOT_BOUND_TO_RAW'],1)
        finally:t.cleanup()

if __name__=='__main__':unittest.main()
