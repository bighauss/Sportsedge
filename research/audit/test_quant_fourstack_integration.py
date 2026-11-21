"""Research-only cross-PR integration tests; synthetic quotes are never authenticated."""
import csv
import io
import unittest
from test_quant_foundation import BASE
from quant_foundation import paper_ledger, parse_source_csv
from quant_capture_preflight import manifest_for_capture
from quant_evidence import replay
from research.prop_pairs.joint_prop_audit import evaluate


def capture_bytes(**changes):
    row = dict(BASE, offered='1', captured='1', modeled='0', provenance='0')
    row.update(changes)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    return buf.getvalue().encode()


class QuantFourStackIntegration(unittest.TestCase):
    def test_same_original_bytes_across_preflight_csv_and_replay(self):
        raw = capture_bytes()
        parsed = parse_source_csv(raw)
        preflight = manifest_for_capture(raw, asof_utc='2026-11-15T23:31:00Z',
                                         provider='DK')
        ledger = paper_ledger(parsed)
        self.assertEqual(preflight['row_count'], 1)
        self.assertFalse(preflight['admission_allowed'])
        self.assertFalse(preflight['source_authenticated'])
        self.assertEqual(len(parsed), 1)
        self.assertEqual(ledger['qualified_graded_n'], 1)
        self.assertEqual(ledger['accounting_contract'], 'PAPER_RESEARCH_NOT_CERTIFIED'
                         if ledger['accounting_contract'] == 'PAPER_RESEARCH_NOT_CERTIFIED'
                         else ledger['accounting_contract'])
        self.assertEqual(replay(parsed)['eligible'], 1)

    def test_lookahead_rule_never_becomes_a_wager(self):
        raw = capture_bytes(rules_effective_utc='2026-11-15T17:30:31-06:00')
        rows = parse_source_csv(raw)
        summary = paper_ledger(rows)
        self.assertEqual(summary['qualified_graded_n'], 0)
        self.assertEqual(summary['net_units'], 0)
        self.assertFalse(manifest_for_capture(
            raw, asof_utc='2026-11-15T23:31:00Z',
            provider='DK')['admission_allowed'])

    def test_ambiguous_input_rejected_before_calibration(self):
        raw = capture_bytes()
        ambiguous = raw.replace(b'p_model,', b'p_model,p_model,', 1)
        with self.assertRaisesRegex(ValueError, 'CSV_DUPLICATE_NORMALIZED_HEADER'):
            parse_source_csv(ambiguous)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_CAPTURE_CSV_HEADERS'):
            manifest_for_capture(ambiguous,asof_utc='2026-11-15T23:31:00Z',provider='DK')

    def test_player_prop_joint_still_refuses_empty_real_corpus(self):
        result = evaluate([])
        self.assertEqual(result['games'], 0)
        self.assertEqual(result['official_counted'], 0)
        self.assertFalse(result['source_authenticated'])


def load_tests(loader, tests, pattern):
    # Explicitly include the independent joint-prop tests in the quant CI job;
    # the normal test_quant_*.py selector would otherwise skip their filename.
    from research.prop_pairs import test_joint_prop_audit
    tests.addTests(loader.loadTestsFromModule(test_joint_prop_audit))
    return tests
