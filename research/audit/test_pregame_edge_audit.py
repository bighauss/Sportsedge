import tempfile
import unittest
import csv
from pathlib import Path
from pregame_edge_audit import audit_rows, audit_file

H='a'*64
B='b'*64

def row(**override):
    d={'sport':'NFL','event_id':'2026-11-15-MATCH1','period':'FG','market':'ML',
       'side':'home','line':'0','price_american':'+120','p_model':'0.52',
       'model_asof_utc':'2026-11-15T16:00:00Z',
       'captured_utc':'2026-11-15T16:10:00Z',
       'game_start_utc':'2026-11-15T17:00:00Z',
       'quote_sha256':H,'model_sha256':B,'player_id':''}
    d.update(override)
    return d

def run(*rows):return audit_rows(list(rows),'c'*64)

class Validation(unittest.TestCase):
    def test_clean_row_ranked(self):
        z=run(row());self.assertEqual(z['diagnostic_eligible'],1)
        self.assertAlmostEqual(z['top_edges'][0]['raw_ev_per_dollar'],0.144)
        self.assertEqual(z['status'],'RESEARCH_ONLY_PAPER_0U')
    def test_duplicate_text_variant(self):
        a=row(market='ML',side='HOME');b=row(market='ml',side='home')
        z=run(a,b);self.assertEqual(z['diagnostic_eligible'],0)
        self.assertEqual(len(z['flagged']),2)
        self.assertTrue(all('DUPLICATE_CANONICAL_SELECTION' in r['flags'] for r in z['flagged']))
    def test_moneyline_blank_zero_and_alias_dedup(self):
        a=row(market='moneyline',period='full_game',line='')
        b=row(market='ML',period='FG',line='0')
        z=run(a,b);self.assertEqual(z['diagnostic_eligible'],0)
        self.assertEqual(len(z['flagged']),2)
        self.assertTrue(all('DUPLICATE_CANONICAL_SELECTION' in r['flags'] for r in z['flagged']))
    def test_malformed_duplicate_first_cannot_poison_rank(self):
        good=row()
        bad=row(p_model='nan', quote_sha256='')
        for rr in ((bad,good),(good,bad)):
            z=run(*rr)
            self.assertEqual(z['diagnostic_eligible'],0)
            self.assertEqual(len(z['flagged']),2)
            self.assertTrue(all('DUPLICATE_CANONICAL_SELECTION' in r['flags'] for r in z['flagged']))
    def test_cross_book_same_selection_not_two_bets(self):
        z=run(row(book='DK'),row(book='OTHER',price_american='+180'))
        self.assertEqual(z['diagnostic_eligible'],0)
        self.assertTrue(all('DUPLICATE_CANONICAL_SELECTION' in r['flags'] for r in z['flagged']))
    def test_alt_lines_are_distinct_selections(self):
        z=run(row(market='SPREAD',side='home',line='-5.5'),
              row(market='SPREAD',side='home',line='-6.5'))
        self.assertEqual(z['diagnostic_eligible'],2)
    def test_numeric_alt_line_format_duplicates_not_counted(self):
        a=row(market='SPREAD',side='HOME',line='+06.50')
        b=row(market='spread',side='home',line='6.5')
        z=run(a,b)
        self.assertEqual(z['diagnostic_eligible'],0)
        self.assertEqual(len(z['flagged']),2)
        self.assertTrue(all('DUPLICATE_CANONICAL_SELECTION' in x['flags'] for x in z['flagged']))
    def test_negative_line_format_duplicates_not_counted(self):
        a=row(market='TOTAL',side='under',line='−05.500')
        b=row(market='total',side='UNDER',line='-5.5')
        z=run(a,b)
        self.assertEqual(z['diagnostic_eligible'],0)
    def test_quote_not_pregame(self):
        z=run(row(captured_utc='2026-11-15T17:00:00Z'))
        self.assertIn('QUOTE_NOT_PREGAME',z['flagged'][0]['flags'])
    def test_stale_quote(self):
        z=run(row(captured_utc='2026-11-15T13:00:00Z',model_asof_utc='2026-11-15T12:00:00Z'))
        self.assertIn('QUOTE_OLDER_THAN_MAX_AGE',z['flagged'][0]['flags'])
    def test_model_after_capture(self):
        z=run(row(model_asof_utc='2026-11-15T16:11:00Z'))
        self.assertIn('MODEL_AFTER_CAPTURE',z['flagged'][0]['flags'])
    def test_missing_provenance(self):
        z=run(row(quote_sha256=''))
        self.assertIn('INVALID_OR_MISSING_QUOTE_SHA256',z['flagged'][0]['flags'])
    def test_no_player_identity(self):
        z=run(row(market='PLAYER_PROP:PASS_YDS',player_id='',side='over'))
        self.assertIn('MISSING_PLAYER_ID',z['flagged'][0]['flags'])
    def test_longshot_holds_for_sensitivity(self):
        z=run(row(price_american='+1400'))
        self.assertIn('LONGSHOT_METHOD_SENSITIVITY_REQUIRED',z['flagged'][0]['flags'])
    def test_naive_timestamp_and_probability(self):
        z=run(row(captured_utc='2026-11-15T16:10:00',p_model='nan'))
        self.assertTrue(any(x.startswith('INVALID_NUMERIC_OR_TIMESTAMP') for x in z['flagged'][0]['flags']))
    def test_missing_fields_not_silent(self):
        z=run(row(event_id=''))
        self.assertTrue(any(x.startswith('MISSING_FIELDS:') for x in z['flagged'][0]['flags']))
    def test_only_top20_and_no_results_exclusion(self):
        rr=[row(event_id=f'M{i}',p_model=f'{0.40+i*0.005:.3f}') for i in range(35)]
        z=run(*rr)
        self.assertEqual(z['diagnostic_eligible'],35)
        self.assertEqual(len(z['top_edges']),20)
    def test_file_hash_and_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'snap.csv';a=row()
            with f.open('w',newline='') as h:
                w=csv.DictWriter(h,fieldnames=list(a));w.writeheader();w.writerow(a)
            before=f.read_bytes();z=audit_file(f)
            self.assertEqual(f.read_bytes(),before)
            self.assertEqual(len(z['snapshot_sha256']),64)
            self.assertEqual(z['total_rows'],1)

if __name__=='__main__':unittest.main()
