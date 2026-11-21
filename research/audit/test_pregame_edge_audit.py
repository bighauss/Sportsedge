import tempfile
import unittest
import csv
import io
import hashlib
from pathlib import Path
from pregame_edge_audit import audit_rows, audit_file, parse_original_csv

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
    def test_flagged_longshot_stays_visible_in_claimed_top(self):
        z=run(row(event_id='LONGSHOT',price_american='+1400',p_model='0.50'),
              row(event_id='SMALL',price_american='+105',p_model='0.52'))
        self.assertEqual(z['top_claimed_edges_including_flagged'][0]['identity'].split('|')[1],'longshot')
        self.assertIn('LONGSHOT_METHOD_SENSITIVITY_REQUIRED',
                      z['top_claimed_edges_including_flagged'][0]['flags'])
        self.assertEqual(z['top_edges'][0]['identity'].split('|')[1],'small')
        self.assertFalse(z['admission_allowed'])

    def test_invalid_quote_timestamp_cannot_hide_extreme_claim(self):
        z=run(row(event_id='LATE',captured_utc='2026-11-15T18:00:00Z',
                  price_american='+1400',p_model='0.40'))
        self.assertEqual(len(z['top_edges']),0)
        self.assertEqual(len(z['top_claimed_edges_including_flagged']),1)
        self.assertIn('QUOTE_NOT_PREGAME',
                      z['top_claimed_edges_including_flagged'][0]['flags'])

    def test_selection_time_not_attested_is_explicit(self):
        z=run(row())
        self.assertEqual(z['top_claimed_edges_including_flagged'][0]['selection_clock_status'],
                         'NOT_ATTESTED')
        self.assertEqual(z['quote_age_basis'],'KICKOFF_LOOKBACK_RESEARCH_NOT_SELECTION_FRESHNESS')

    def test_declared_selection_clock_checks_age_and_chronology(self):
        stale=run(row(selected_utc='2026-11-15T16:20:00Z'))
        self.assertIn('QUOTE_OLDER_THAN_300S_AT_SELECTION',stale['flagged'][0]['flags'])
        late=run(row(selected_utc='2026-11-15T16:09:00Z'))
        self.assertIn('QUOTE_AFTER_SELECTION',late['flagged'][0]['flags'])
        same=run(row(selected_utc='2026-11-15T16:11:00Z'))
        self.assertEqual(same['top_edges'][0]['quote_age_at_selection_seconds'],60.0)
        self.assertEqual(same['top_edges'][0]['selection_clock_status'],
                         'DECLARED_NOT_AUTHENTICATED')

    def test_ladder_cluster_dedup_preserves_all_claimed_rows(self):
        z=run(row(event_id='GAME',market='SPREAD',side='home',line='-3.5'),
              row(event_id='GAME',market='SPREAD',side='home',line='-4.5'),
              row(event_id='OTHER',market='ML',side='home',line='0'))
        self.assertEqual(len(z['top_claimed_edges_including_flagged']),3)
        self.assertEqual(z['claimed_clusters'],2)
        self.assertEqual(len(z['top_claimed_clusters_including_flagged']),2)

    def test_cluster_key_never_splits_raw_event_ids_on_delimiters(self):
        z=run(row(event_id='E|PIPE',market='SPREAD',side='home',line='-3.5'),
              row(event_id='E|PIPE',market='SPREAD',side='home',line='-4.5'))
        self.assertEqual(z['computable_claimed_edges'],2)
        self.assertEqual(z['claimed_clusters'],1)

    def test_file_hash_and_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'snap.csv';a=row()
            with f.open('w',newline='') as h:
                w=csv.DictWriter(h,fieldnames=list(a));w.writeheader();w.writerow(a)
            before=f.read_bytes();z=audit_file(f)
            self.assertEqual(f.read_bytes(),before)
            self.assertEqual(len(z['snapshot_sha256']),64)
            self.assertEqual(z['total_rows'],1)

    @staticmethod
    def original_csv(**changes):
        """Build one source row without changing historical loader semantics."""
        source_row=row(**changes)
        out=io.StringIO(newline='')
        writer=csv.writer(out)
        fields=list(source_row)
        writer.writerow(fields)
        writer.writerow([source_row[k] for k in fields])
        return out.getvalue().encode('utf-8')

    def test_duplicated_original_probability_headers_block_before_ev_ranking(self):
        # With DictReader, a later 0.95 silently overwrites 0.01, turning
        # -97% raw EV at +200 into +185%. No order is eligible as evidence.
        for alias in ('p_model', 'p_model ', 'P_MODEL', ' P_MODEL '):
            with self.subTest(alias=alias):
                d=row(p_model='0.01',price_american='+200')
                out=io.StringIO(newline='')
                writer=csv.writer(out)
                cols=list(d)
                writer.writerow(cols+[alias])
                writer.writerow([d[k] for k in cols]+['0.95'])
                with self.assertRaisesRegex(
                    ValueError,'ORIGINAL_CSV_DUPLICATE_NORMALIZED_HEADER'):
                    parse_original_csv(out.getvalue().encode())

    def test_unnormalized_nonduplicate_header_rejected_without_silent_renaming(self):
        original=self.original_csv()
        altered=original.replace(b'price_american,',b'price_american ,',1)
        with self.assertRaisesRegex(ValueError,'ORIGINAL_CSV_UNNORMALIZED_HEADER'):
            parse_original_csv(altered)

    def test_blank_logical_records_refused_without_dropping_denominator(self):
        original=self.original_csv()
        header,body=original.splitlines(keepends=True)
        for bad in (header+b'\n'+body,header+body+b'\n'):
            with self.subTest(length=len(bad)):
                with self.assertRaisesRegex(ValueError,'ORIGINAL_CSV_BLANK_LOGICAL_RECORD'):
                    parse_original_csv(bad)

    def test_ragged_short_or_extra_original_rows_are_never_ranked(self):
        d=row()
        cols=list(d)
        for trim in (1, -1):
            stream=io.StringIO(newline='')
            writer=csv.writer(stream)
            writer.writerow(cols)
            values=[d[k] for k in cols]
            writer.writerow(values[:-1] if trim==1 else values+['extra'])
            with self.subTest(trim=trim):
                with self.assertRaisesRegex(ValueError,'ORIGINAL_CSV_RAGGED_RECORD'):
                    parse_original_csv(stream.getvalue().encode())

    def test_valid_multiline_quoted_field_does_not_trigger_false_blank_record(self):
        # A quoted note containing an empty PHYSICAL line is one valid
        # LOGICAL CSV record, and its source byte hash must remain unchanged.
        d=row()
        d['notes']='first observation\n\nsecond observation'
        stream=io.StringIO(newline='')
        writer=csv.writer(stream)
        cols=list(d)
        writer.writerow(cols)
        writer.writerow([d[k] for k in cols])
        raw=stream.getvalue().encode()
        self.assertIn(b'\n\n',raw)
        self.assertEqual(parse_original_csv(raw)[0]['notes'],d['notes'])
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'original.csv'
            source.write_bytes(raw)
            result=audit_file(source)
            self.assertEqual(source.read_bytes(),raw)
            self.assertEqual(result['snapshot_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(result['total_rows'],1)
            self.assertEqual(result['diagnostic_eligible'],1)

    def test_invalid_utf8_and_unclosed_quoted_field_refused(self):
        with self.assertRaisesRegex(ValueError,'ORIGINAL_CSV_INVALID_UTF8'):
            parse_original_csv(b'\xff\xfe')
        broken=self.original_csv()+b'\"unterminated'
        with self.assertRaisesRegex(ValueError,'ORIGINAL_CSV_MALFORMED'):
            parse_original_csv(broken)

    def test_clean_original_rows_retained_and_top_edge_order_preserved(self):
        stream=io.StringIO(newline='')
        first=row(event_id='A',p_model='0.30')
        second=row(event_id='B',p_model='0.70')
        writer=csv.DictWriter(stream,fieldnames=list(first))
        writer.writeheader()
        writer.writerows((first,second))
        raw=stream.getvalue().encode()
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'original.csv'
            source.write_bytes(raw)
            result=audit_file(source)
            self.assertEqual(result['total_rows'],2)
            self.assertEqual(result['computable_claimed_edges'],2)
            self.assertEqual(result['top_edges'][0]['identity'].split('|')[1],'b')
            self.assertEqual(source.read_bytes(),raw)

if __name__=='__main__':unittest.main()
