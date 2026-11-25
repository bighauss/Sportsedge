"""Offline regressions for the NBA behavioral transition da0c1503 -> b353de86 (PAPER_0U).

No network, no real boards, no wagers.  Synthetic inputs prove code behavior only.
"""
import difflib
import hashlib
import importlib.util
import json
import math
import subprocess
import unittest
from pathlib import Path

import nba_push_accounting_equivalence as eq
from verify_code_freezes import git_blob_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
V0 = '0036cb9a2a7eff9fed9b175a0175a963d20e6b3e'
V1 = 'da0c1503af5ed9ad548d1458588505f695b749e5'
V2 = 'b353de86445188288cab4050f6cae13eee76bff6'
V1_COMMIT = '098c92bfd538fbb664b1c8eccccf61779cabe2b2'
V2_COMMIT = '8537ae481a34fa6972a67389a6ac75172ee1f59c'
NBA_PATH = 'models/nba/sportsedge_nba_model.py'
PINNED_V1 = HERE / 'pinned_blobs' / 'da0c1503_sportsedge_nba_model.py.txt'
EVIDENCE = HERE / 'nba_push_accounting_20261125_equivalence.json'
RECORD = HERE / 'nba_push_accounting_transition_20261125.json'
CANDIDATE = HERE / 'code_identity_transitions_20261125_nba_candidate.json'


def diff_text(old: bytes, new: bytes) -> str:
    return ''.join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                        'da0c1503', 'b353de86', n=0))


def git(*a):
    return subprocess.check_output(['git', '-C', str(ROOT), *a], stderr=subprocess.PIPE)


def mod_hist():
    spec = importlib.util.spec_from_file_location('analyze_hist', HERE / 'nba_push_accounting_hist' / 'analyze_hist.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Models(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = eq.load(eq.OLD_PATH, eq.OLD_BLOB, 'nba_old')
        cls.new = eq.load(eq.NEW_PATH, eq.NEW_BLOB, 'nba_new')

    def price(self, mod, mk, sel, margin, seg_mean=1.0):
        proj = {'margin': margin, 'total': 226.0, 'home': 'H', 'away': 'A', 'home_pts': 113.0, 'away_pts': 113.0}
        return mod.price_game_market({'market': mk, 'selection': sel, 'line': ''}, proj)


class Diff(Models):
    def test_diff_is_exactly_one_hunk_plus6_minus1_with_expected_lines(self):
        d = diff_text(PINNED_V1.read_bytes(), eq.NEW_PATH.read_bytes()).splitlines()
        self.assertEqual(sum(1 for l in d if l.startswith('@@')), 1)
        added = [l[1:].strip() for l in d if l.startswith('+') and not l.startswith('+++')]
        removed = [l[1:].strip() for l in d if l.startswith('-') and not l.startswith('---')]
        self.assertEqual(len(added), 6)
        self.assertEqual(removed, ['p = 1 - N.cdf((0 - mu) / (SD["margin"] * sm))'])
        code = [a.split('#')[0].strip() for a in added if not a.startswith('#')]
        self.assertEqual(code, ['if seg != "FG":', 'po, push = p_over(mu, SD["margin"] * sm, 0)',
                                'return po, push, mu, "margin"', 'p = 1 - N.cdf((0 - mu) / (SD["margin"] * sm))'])

    def test_pinned_copy_and_current_blob(self):
        self.assertEqual(git_blob_digest(PINNED_V1.read_bytes()), V1)
        self.assertEqual(git_blob_digest(eq.NEW_PATH.read_bytes()), V2)


class Normalization(Models):
    def test_win_loss_push_sum_to_one_and_push_is_tie_band(self):
        N = self.new.N
        for seg, mk in (('1H', '1H_ML'), ('1Q', '1Q_ML')):
            sd = self.new.SD['margin'] * self.new.SEG[seg][1]
            for i in range(-400, 401, 7):
                mu = i * 0.1
                m = mu / self.new.SEG[seg][0]
                h = self.price(self.new, mk, 'H', m)
                a = self.price(self.new, mk, 'A', m)
                self.assertAlmostEqual(h[0] + a[0] + h[1], 1.0, places=12)
                self.assertAlmostEqual(h[1], a[1], places=12)
                self.assertAlmostEqual(h[1], N.cdf((0.5 - mu) / sd) - N.cdf((-0.5 - mu) / sd), places=12)
                self.assertTrue(0 <= h[1] < 0.07 and all(math.isfinite(x) for x in (*h[:3], *a[:3])))
                o = self.price(self.old, mk, 'H', m)
                self.assertEqual(o[1], 0.0)             # previous version: no push mass at all

    def test_full_game_ml_bit_identical_no_push(self):
        for mu in (-30, -7.5, -0.2, 0, 0.2, 3, 12, 40):
            for sel in ('H', 'A'):
                a, b = self.price(self.old, 'ML', sel, mu), self.price(self.new, 'ML', sel, mu)
                self.assertEqual(tuple(map(eq.hx, a)), tuple(map(eq.hx, b)))
                self.assertEqual(b[1], 0.0)

    def test_ev_shift_identity_exact_and_near_even_push_form(self):
        for seg, mk in (('1H', '1H_ML'), ('1Q', '1Q_ML')):
            for mu in (-6.0, 0.0, 2.5):
                m = mu / self.new.SEG[seg][0]
                for dec in (1.3, 1.909, 2.0, 2.5, 4.0):
                    o, n = self.price(self.old, mk, 'H', m), self.price(self.new, mk, 'H', m)
                    shift = self.new.ev(n[0], dec, n[1]) - self.old.ev(o[0], dec, o[1])
                    # exact: EV = p*dec - 1 + push  =>  shift = dp*dec + push
                    self.assertAlmostEqual(shift, (n[0] - o[0]) * dec + n[1], places=12)
                    if mu == 0.0:   # at an even matchup old p credited exactly half the tie band
                        self.assertAlmostEqual(shift, n[1] * (1 - dec / 2), places=12)

    def test_three_way_boards_fail_closed_in_both_versions(self):
        probes = eq.contract_probes(self.old, self.new)
        for k in ('three_way_H_A_TIE_under_1H_ML', 'three_way_labelled_1H_ML_3WAY_H_A',
                  'three_way_labelled_1H_ML_3WAY_H_A_TIE'):
            self.assertEqual(probes[k]['old'], [])
            self.assertEqual(probes[k]['new'], [])
        self.assertEqual(len(probes['two_way_H_A']['new']), 2)

    def test_known_gap_partial_three_way_capture_is_priced_as_two_way_in_both_versions(self):
        # Documents a PRE-EXISTING hazard (not introduced by this transition): H + TIE rows pair as
        # a two-way market and the TIE row is priced as the away side. Needs a capture/adapter guard.
        p = eq.contract_probes(self.old, self.new)['PARTIAL_capture_H_plus_TIE_only_under_1H_ML']
        self.assertEqual([r['selection'] for r in p['old']], ['H', 'TIE'])
        self.assertEqual([r['selection'] for r in p['new']], ['H', 'TIE'])


class Equivalence(Models):
    def test_unaffected_markets_bit_identical_and_affected_normalised(self):
        out = eq.run(n_games=150)
        self.assertEqual(len(out['results']), 3)
        for r in out['results']:
            self.assertEqual(r['unaffected_mismatch'], 0)
            self.assertEqual(r['projection_mismatch'], 0)
            self.assertEqual(r['prop_mismatch'], 0)
            self.assertEqual(r['card_unaffected_mismatch'], 0)
            self.assertTrue(r['card_run_unaffected_identical'])
            self.assertEqual(r['affected_norm_violations'], 0)
            self.assertEqual(r['affected_changed'], r['affected_rows'])
            self.assertEqual(r['affected_new_push_zero'], 0)
            self.assertEqual(r['affected_old_push_nonzero'], 0)
        base = out['results'][0]
        self.assertEqual(base['affected_rows'], 0)
        self.assertTrue(base['card_byte_identical'])          # committed-style sample board: no 1H/1Q ML rows

    def test_committed_evidence_is_consistent(self):
        ev = json.loads(EVIDENCE.read_text())
        self.assertEqual((ev['old_blob'], ev['new_blob']), (V1, V2))
        for grid in ev['normalization_grid'].values():
            self.assertLess(grid['max_abs_dev_win_home_plus_win_away_plus_push_minus_1'], 1e-12)


class Historical(unittest.TestCase):
    def test_committed_analysis_reproduces_from_committed_games(self):
        h = mod_hist()
        self.assertEqual(json.loads(json.dumps(h.analyze())), json.loads((HERE / 'nba_push_accounting_hist' / 'analysis.json').read_text()))


class StandInLabels(unittest.TestCase):
    """Owner ruling on the #536 review: historical projections are market-derived stand-ins and every
    output must say so (not independent-model evidence). The limitation is preserved, not hidden."""
    FLAG = 'MARKET_STAND_IN_NOT_INDEPENDENT_MODEL_EVIDENCE'

    def test_analysis_output_carries_flag_everywhere(self):
        a = json.loads((HERE / 'nba_push_accounting_hist' / 'analysis.json').read_text())
        for node in (a, a['model_replay_on_market_implied_margin'], a['ev_shift_hypothetical_minus110']):
            self.assertEqual(node['projection_basis'], 'MARKET_DERIVED_STAND_IN')
            self.assertIs(node['independent_model_evidence'], False)
            self.assertEqual(node['flag'], self.FLAG)

    def test_regenerated_analysis_carries_flag(self):
        out = mod_hist().analyze()
        self.assertEqual(out['flag'], self.FLAG)
        self.assertIs(out['independent_model_evidence'], False)

    def test_record_and_markdown_label_the_limitation(self):
        r = json.loads(RECORD.read_text())
        self.assertEqual(r['evidence_labels']['flag'], self.FLAG)
        self.assertIs(r['evidence_labels']['independent_model_evidence'], False)
        self.assertEqual(r['historical_backtest']['projection_basis'], 'MARKET_DERIVED_STAND_IN')
        self.assertIn('NOT independent-model evidence', r['historical_backtest']['projection_stand_in'])
        md = (HERE / 'nba_push_accounting_transition_20261125.md').read_text()
        self.assertIn(self.FLAG, md.split('**Status:')[0])
        self.assertIn('MARKET_DERIVED_STAND_IN', md)

    def test_governance_record_labels_the_limitation(self):
        g = json.loads((ROOT / 'docs' / 'governance' / 'changes' / 'pr-536.json').read_text())
        text = ' '.join(g['assumptions'])
        self.assertIn('MARKET_DERIVED_STAND_IN', text)
        self.assertIn('not independent-model evidence', text)


class Consistency(unittest.TestCase):
    """Data-consistency checks for the record and the candidate entry. NOT a verifier: the owner chose
    one unified verifier (stock verify_versioned_transition.py extended in #535) to enforce these."""

    @classmethod
    def setUpClass(cls):
        cls.rec = json.loads(RECORD.read_text())
        cls.cand = json.loads(CANDIDATE.read_text())

    def test_candidate_entry_has_mlb_candidate_format_and_nba_values(self):
        c = self.cand
        self.assertEqual(c['schema'], 'sportsedge-code-identity-transitions-v1')
        self.assertEqual((c['status'], c['recording_act']), ('PENDING_OWNER_MERGE', 'OWNER_MERGE'))
        self.assertEqual((c['official_counted'], c['approved_stake_u']), (0, 0))
        self.assertFalse(c['supplements_manifest']['edited_by_this_change'])
        self.assertEqual(len(c['candidates']), 1)
        e = c['candidates'][0]
        self.assertEqual((e['sport'], e['path']), ('NBA', NBA_PATH))
        self.assertEqual((e['original_git_blob_sha1'], e['prior_approved_candidate_git_blob_sha1'],
                          e['approved_candidate_git_blob_sha1']), (V0, V1, V2))
        self.assertEqual((e['prior_first_introducing_commit'], e['first_introducing_commit']), (V1_COMMIT, V2_COMMIT))
        self.assertEqual((e['prior_change_pr'], e['change_pr']), (294, 460))
        gov = ROOT / e['governance_record']
        self.assertEqual(git_blob_digest(gov.read_bytes()), self.rec['governance_record_git_blob_sha1'])

    def test_record_is_paper_0u_pending_and_content_addressed(self):
        r = self.rec
        for k, v in (('status', 'PENDING_OWNER_MERGE'), ('release', 'PAPER_0U'), ('official_counted', 0),
                     ('approved_stake_u', 0), ('model_release_certified', False), ('source_authenticated', False),
                     ('candidate_blob', V2), ('previous_approved_blob', V1), ('first_introducing_commit', V2_COMMIT)):
            self.assertEqual(r[k], v, k)
        self.assertEqual(git_blob_digest(EVIDENCE.read_bytes()), r['equivalence']['evidence_git_blob_sha1'])
        for key, rel in (('hist_analysis_git_blob_sha1', 'nba_push_accounting_hist/analysis.json'),
                         ('hist_games_csv_git_blob_sha1', 'nba_push_accounting_hist/games.csv')):
            self.assertEqual(git_blob_digest((HERE / rel).read_bytes()), r['historical_backtest'][key], key)
        d = diff_text(PINNED_V1.read_bytes(), (ROOT / NBA_PATH).read_bytes())
        self.assertEqual(hashlib.sha256(d.encode()).hexdigest(), r['diff']['unified_diff_n0_sha256'])

    def test_git_provenance_first_introducing_commit(self):
        try:
            git('cat-file', '-e', V2_COMMIT)
        except subprocess.CalledProcessError:
            self.skipTest('full git history unavailable (CI uses fetch-depth: 0)')
        self.assertEqual(git_blob_digest(git('show', V2_COMMIT + ':' + NBA_PATH)), V2)
        git('merge-base', '--is-ancestor', V2_COMMIT, 'HEAD')
        git('merge-base', '--is-ancestor', V1_COMMIT, V2_COMMIT)
        parents = git('rev-list', '--parents', '-n', '1', V2_COMMIT).decode().split()[1:]
        self.assertTrue(parents)
        for p in parents:
            self.assertEqual(git_blob_digest(git('show', p + ':' + NBA_PATH)), V1)

    def test_evidence_reports_isolated_behavior_change(self):
        ev = json.loads(EVIDENCE.read_text())
        for r in ev['results']:
            self.assertEqual((r['unaffected_mismatch'], r['projection_mismatch'], r['prop_mismatch'],
                              r['card_unaffected_mismatch'], r['affected_norm_violations']), (0, 0, 0, 0, 0))
            self.assertTrue(r['card_run_unaffected_identical'])


if __name__ == '__main__':
    unittest.main()
