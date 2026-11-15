import csv
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

P = Path(__file__).with_name('nfl_ratings_roster_bridge_r1.py')
spec = importlib.util.spec_from_file_location('bridge',P)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture=self.root/'capture.csv'
        self.fields=['captured_ct','sport','game_time_ct','away','home','game_key','market','period','side','player','line','price_american','raw_label_status']
        self.rows=[
            ['2026-11-15T14:15:24-06:00','NFL','2026-11-15T15:05:00-06:00','SEA','LV','SEA@LV','ml','FG','home','','','+240','EXACT_VISIBLE'],
            ['2026-11-15T14:15:24-06:00','NFL','2026-11-15T15:05:00-06:00','SEA','LV','SEA@LV','player_prop:passing_yards','FG','yes','Fernando…','189.5','+108','TRUNCATED_VISIBLE_LABEL'],
        ]
        self.write(self.capture,self.fields,self.rows)
        self.ratings=self.root/'ratings.csv'
        self.rf=['team','off','def','gp','lg','hfa','asof','half_life','ridge']
        self.rr=[['SEA','5','3','9','22.9','1.6','2026-11-10','45','5'],['LV','-3','-1','9','22.9','1.6','2026-11-10','45','5']]
        self.write(self.ratings,self.rf,self.rr)
        self.digest=b.sha256(self.ratings)
    def write(self,path,header,rows):
        with path.open('w',newline='') as f:
            w=csv.writer(f);w.writerow(header);w.writerows(rows)
    def test_no_source_no_fabricated_points(self):
        a,c,r=b.bridge(self.capture)
        self.assertEqual(r['capture_rows'],2)
        self.assertEqual(r['games_with_numeric_ratings'],0)
        self.assertEqual(r['participant_or_team_unbound'],1)
        self.assertEqual(a[0]['ratings_home_points'],'')
        self.assertIn('TRUNCATED',c[0]['reasons'])
    def test_valid_synthetic_ratings_only(self):
        a,c,r=b.bridge(self.capture,self.ratings,self.digest)
        self.assertEqual(r['games_with_numeric_ratings'],1)
        self.assertEqual(a[0]['ratings_home_points'],'17.700')
        self.assertEqual(a[0]['ratings_away_points'],'28.100')
        self.assertEqual(a[0]['status'],'PAPER_HOLD_0U')
    def test_hash_mismatch_blocks(self):
        a,_,r=b.bridge(self.capture,self.ratings,'0'*64)
        self.assertEqual(a[0]['reason'],'RATINGS_SHA256_MISMATCH')
        self.assertEqual(r['games_with_numeric_ratings'],0)
    def test_alias_exact_only(self):
        self.rr[1][0]='Las Vegas Raiders';self.write(self.ratings,self.rf,self.rr)
        a,_,_=b.bridge(self.capture,self.ratings,b.sha256(self.ratings))
        self.assertEqual(a[0]['reason'],'EXACT_TEAM_RATINGS_MAPPING_REQUIRED')
        a,_,_=b.bridge(self.capture,self.ratings,b.sha256(self.ratings),{'SEA@LV':{'home':'Las Vegas Raiders','away':'SEA'}})
        self.assertNotEqual(a[0]['ratings_home_points'],'')
    def test_duplicate_ratings_blocks(self):
        self.write(self.ratings,self.rf,self.rr+[self.rr[0]])
        a,_,_=b.bridge(self.capture,self.ratings,b.sha256(self.ratings))
        self.assertEqual(a[0]['reason'],'RATINGS_SCHEMA_OR_VALUES_INVALID')
    def test_date_only_asof_same_day_blocks(self):
        self.rr[0][6]=self.rr[1][6]='2026-11-15';self.write(self.ratings,self.rf,self.rr)
        a,_,_=b.bridge(self.capture,self.ratings,b.sha256(self.ratings))
        self.assertEqual(a[0]['reason'],'RATINGS_ASOF_TOO_RECENT_FOR_DATE_ONLY_PIT')
    def test_live_snapshot_blocks(self):
        self.rows[0][0]=self.rows[1][0]='2026-11-15T15:06:00-06:00';self.write(self.capture,self.fields,self.rows)
        a,_,_=b.bridge(self.capture,self.ratings,self.digest)
        self.assertEqual(a[0]['reason'],'SNAPSHOT_AFTER_EVENT_START')
    def test_proof_no_automatic_authentication(self):
        p={'capture_sha256':b.sha256(self.capture),'dk_outcome_id':'outcome-1','gsis_id':'00-0039999','team_id':'LV',
           'provider_receipt_id':'receipt-1','roster_receipt_id':'roster-1',
           'provider_observed_utc':'2026-11-15T20:10:00+00:00',
           'roster_observed_utc':'2026-11-15T20:00:00+00:00'}
        _,c,_=b.bridge(self.capture,evidence={'3':p})
        self.assertEqual(c[0]['binding_status'],'BLOCK_UNBOUND')
        self.assertIn('VISIBLE_LABEL_TRUNCATED',c[0]['reasons'])
    def test_future_proof_rejected(self):
        p={'capture_sha256':b.sha256(self.capture),'dk_outcome_id':'x','gsis_id':'y','team_id':'LV',
           'provider_receipt_id':'z','roster_receipt_id':'a',
           'provider_observed_utc':'2026-11-15T21:00:00+00:00','roster_observed_utc':'2026-11-15T20:00:00+00:00'}
        _,c,_=b.bridge(self.capture,evidence={'3':p})
        self.assertEqual(c[0]['binding_status'],'BLOCK_UNBOUND')
        self.assertIn('AFTER_SCREENSHOT',c[0]['reasons'])
    def test_dst_outcome_does_not_require_gsis(self):
        self.rows.append(['2026-11-15T14:15:24-06:00','NFL','2026-11-15T15:05:00-06:00','SEA','LV','SEA@LV','attd','FG','yes','SEA Seahawks D/ST','', '+475','VISIBLE_LABEL_NO_AUTH_PLAYER_ID'])
        self.write(self.capture,self.fields,self.rows)
        _,c,r=b.bridge(self.capture)
        self.assertEqual(r['team_dst_quotes'],1)
        dst=[x for x in c if x['selection_type']=='TEAM_DST']
        self.assertEqual(len(dst),1)
        self.assertNotIn('ROSTER_GSIS_ID_NOT_PROVEN',dst[0]['reasons'])
        self.assertIn('DK_OUTCOME_ID_NOT_PROVEN',dst[0]['reasons'])
    def test_source_file_unchanged(self):
        pre=b.sha256(self.capture);b.bridge(self.capture,self.ratings,self.digest)
        self.assertEqual(pre,b.sha256(self.capture))
    def test_malformed_header_rejected(self):
        self.write(self.capture,self.fields+[self.fields[0]],self.rows)
        with self.assertRaises(ValueError):b.bridge(self.capture)

if __name__=='__main__':unittest.main()
