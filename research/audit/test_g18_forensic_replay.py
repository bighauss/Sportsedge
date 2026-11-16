"""Synthetic regression coverage for the historical bug, not claimed 496-row results."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from g18_forensic_replay import parse_selection, grade_one, replay, main, InvalidRecord

GAME = 'Mississippi Valley @ Washington'
FINAL = {'away': 64, 'home': 77, 'away_1h': 33, 'home_1h': 43,
         'source': 'illustrative synthetic finals only'}


def csv_bytes(rows):
    f = io.StringIO(newline='')
    w = csv.DictWriter(f, fieldnames=['game', 'pick', 'price'])
    w.writeheader()
    w.writerows({'game': GAME, 'pick': p, 'price': '-110'} for p in rows)
    return f.getvalue().encode()


class G18Tests(unittest.TestCase):
    def test_original_team_total_defect_spot(self):
        self.assertEqual(grade_one(GAME, 'Washington Under 82.5', FINAL, historic_bug=True), 'L')
        self.assertEqual(grade_one(GAME, 'Washington Under 82.5', FINAL, historic_bug=False), 'W')

    def test_first_half_team_total_defect(self):
        self.assertEqual(grade_one(GAME, '1H Washington Under 50.5', FINAL, historic_bug=True), 'L')
        self.assertEqual(grade_one(GAME, '1H Washington Under 50.5', FINAL, historic_bug=False), 'W')
        self.assertEqual(grade_one(GAME, '1H Washington Over 50.5', FINAL, historic_bug=True), 'W')
        self.assertEqual(grade_one(GAME, '1H Washington Over 50.5', FINAL, historic_bug=False), 'L')

    def test_other_markets_identical(self):
        for pick in ['Under 153.5', '1H Over 65.5', 'Washington ML',
                     'Mississippi Valley +13', '1H Washington -10']:
            self.assertEqual(grade_one(GAME, pick, FINAL, historic_bug=True),
                             grade_one(GAME, pick, FINAL, historic_bug=False), pick)

    def test_push_spread(self):
        self.assertEqual(grade_one(GAME, 'Mississippi Valley +13', FINAL,
                                   historic_bug=False), 'P')
        self.assertEqual(grade_one(GAME, '1H Mississippi Valley +10', FINAL,
                                   historic_bug=False), 'P')

    def test_missing_halftime_retained(self):
        no_half = {**FINAL, 'away_1h': None, 'home_1h': None}
        self.assertEqual(grade_one(GAME, '1H Washington Under 50.5', no_half,
                                   historic_bug=False), 'NOT_GRADED')

    def test_unknown_team_rejected(self):
        with self.assertRaises(InvalidRecord):
            parse_selection(GAME, 'Chicago Under 50.5')

    def test_invalid_game_rejected(self):
        with self.assertRaises(InvalidRecord):
            parse_selection('Washington vs Mississippi Valley', 'Washington ML')

    def test_no_silent_row_deletion(self):
        rows = ['Washington Under 82.5', '1H Washington Under 50.5',
                'Mississippi Valley +13', 'Invalid Player Over 20.5']
        r = replay(csv_bytes(rows), json.dumps({GAME: FINAL}).encode())
        self.assertEqual(r['counts']['total_rows'], 4)
        self.assertEqual(r['counts']['grade_flips'], 2)
        self.assertEqual(r['counts']['unresolved'], 1)
        self.assertEqual(len(r['row_audit']), 4)
        self.assertEqual(r['row_audit'][3]['status'], 'UNRESOLVED:UNPARSED_MARKET_OR_TEAM')
        self.assertNotIn('roi', r)

    def test_missing_final_retained(self):
        r = replay(csv_bytes(['Washington Under 82.5']), b'{}')
        self.assertEqual(r['counts']['not_graded'], 1)
        self.assertIsNone(r['row_audit'][0]['corrected'])

    def test_digest_mismatch_refused(self):
        b = csv_bytes(['Washington Under 82.5'])
        with self.assertRaisesRegex(InvalidRecord, 'PICKS_DIGEST_MISMATCH'):
            replay(b, b'{}', expected_picks_sha256='0'*64)

    def test_digest_correct(self):
        b = csv_bytes(['Washington Under 82.5'])
        r = replay(b, json.dumps({GAME: FINAL}).encode(),
                   expected_picks_sha256=hashlib.sha256(b).hexdigest())
        self.assertEqual(r['counts']['grade_flips'], 1)

    def test_final_scores_must_be_integer(self):
        f = {**FINAL, 'home': 77.1}
        r = replay(csv_bytes(['Washington Under 82.5']), json.dumps({GAME:f}).encode())
        self.assertEqual(r['counts']['unresolved'], 1)

    def test_quarantines_unknown_1h(self):
        r = replay(csv_bytes(['1H Washington Under 50.5']),
                   json.dumps({GAME:{**FINAL, 'away_1h': None}}).encode())
        self.assertEqual(r['row_audit'][0]['status'], 'HALFTIME_NOT_SUPPLIED')

    def test_duplicate_csv_header_is_not_silently_overwritten(self):
        raw = b'game,pick,price,pick\\nMississippi Valley @ Washington,Washington Under 82.5,-110,Washington Over 82.5\\n'
        raw = raw.replace(b'\\n', b'\n')
        with self.assertRaisesRegex(InvalidRecord, 'ORIGINAL_PICKS_SCHEMA_REQUIRED'):
            replay(raw, json.dumps({GAME: FINAL}).encode())

    def test_duplicate_final_json_key_is_rejected(self):
        # The duplicate second home result must not overwrite the first.
        raw = ('{"Mississippi Valley @ Washington":{"away":64,"home":77,"home":200,'
               '"away_1h":33,"home_1h":43}}').encode()
        with self.assertRaisesRegex(InvalidRecord, 'DUPLICATE_FINAL_JSON_KEY'):
            replay(csv_bytes(['Washington Under 82.5']), raw)

    def test_invalid_price_quarantined_and_original_row_retained(self):
        raw = csv_bytes(['Washington Under 82.5'])
        broken = raw.replace(b'-110', b'-99')
        report = replay(broken, json.dumps({GAME: FINAL}).encode())
        self.assertEqual(report['counts']['total_rows'], 1)
        self.assertEqual(report['counts']['unresolved'], 1)
        self.assertEqual(report['counts'].get('graded', 0), 0)
        self.assertEqual(report['row_audit'][0]['price'], '-99')
        self.assertEqual(report['row_audit'][0]['status'], 'UNRESOLVED:INVALID_OR_MISSING_AMERICAN_PRICE')
        self.assertFalse(report['row_audit'][0]['changed'])

    def test_missing_price_quarantined(self):
        raw = csv_bytes(['Washington Under 82.5']).replace(b'-110', b'')
        report = replay(raw, json.dumps({GAME: FINAL}).encode())
        self.assertEqual(report['counts']['unresolved'], 1)
        self.assertEqual(len(report['row_audit']), 1)

    def test_create_only_output(self):
        with tempfile.TemporaryDirectory() as d:
            picks = Path(d)/'picks.csv'; finals = Path(d)/'finals.json';out = Path(d)/'report.json'
            picks.write_bytes(csv_bytes(['Washington Under 82.5']))
            finals.write_text(json.dumps({GAME:FINAL}))
            self.assertEqual(main([str(picks),str(finals),'--report',str(out)]),0)
            self.assertEqual(json.loads(out.read_text())['counts']['grade_flips'],1)
            with self.assertRaises(FileExistsError):
                main([str(picks),str(finals),'--report',str(out)])


if __name__ == '__main__':
    unittest.main()
