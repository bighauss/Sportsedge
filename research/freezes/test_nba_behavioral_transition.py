"""Offline regressions for the NBA behavioral transition da0c1503 -> b353de86 (PAPER_0U).

No network, no real boards, no wagers.  Synthetic inputs prove code behavior only.
"""
import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

import nba_push_accounting_equivalence as eq
import verify_nba_behavioral_transition as vn
from verify_code_freezes import FreezeViolation, git_blob_digest

HERE = Path(__file__).resolve().parent


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
        d = vn.diff_text(vn.PINNED_V1.read_bytes(), eq.NEW_PATH.read_bytes()).splitlines()
        self.assertEqual(sum(1 for l in d if l.startswith('@@')), 1)
        added = [l[1:].strip() for l in d if l.startswith('+') and not l.startswith('+++')]
        removed = [l[1:].strip() for l in d if l.startswith('-') and not l.startswith('---')]
        self.assertEqual(len(added), 6)
        self.assertEqual(removed, ['p = 1 - N.cdf((0 - mu) / (SD["margin"] * sm))'])
        code = [a.split('#')[0].strip() for a in added if not a.startswith('#')]
        self.assertEqual(code, ['if seg != "FG":', 'po, push = p_over(mu, SD["margin"] * sm, 0)',
                                'return po, push, mu, "margin"', 'p = 1 - N.cdf((0 - mu) / (SD["margin"] * sm))'])

    def test_pinned_copy_and_current_blob(self):
        self.assertEqual(git_blob_digest(vn.PINNED_V1.read_bytes()), vn.V1)
        self.assertEqual(git_blob_digest(eq.NEW_PATH.read_bytes()), vn.V2)


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
        ev = json.loads(vn.EVIDENCE.read_text())
        self.assertEqual((ev['old_blob'], ev['new_blob']), (vn.V1, vn.V2))
        for grid in ev['normalization_grid'].values():
            self.assertLess(grid['max_abs_dev_win_home_plus_win_away_plus_push_minus_1'], 1e-12)


class Historical(unittest.TestCase):
    def test_committed_analysis_reproduces_from_committed_games(self):
        h = mod_hist()
        self.assertEqual(json.loads(json.dumps(h.analyze())), json.loads((HERE / 'nba_push_accounting_hist' / 'analysis.json').read_text()))


class Verifier(unittest.TestCase):
    def test_verifier_passes_for_nba_chain(self):
        r = vn.run()
        self.assertTrue(r['status'].startswith('NBA_BEHAVIORAL_TRANSITION_VERIFIED'))
        self.assertEqual(r['nba_chain'], [vn.V0, vn.V1, vn.V2])
        self.assertEqual((r['official_counted'], r['approved_stake_u']), (0, 0))
        self.assertFalse(r['model_release_certified'])

    def test_rejects_modified_entry(self):
        base = vn.expected_entry()
        for mutate in (lambda e: e.update(approved_stake_u=1), lambda e: e.update(status='MERGED'),
                       lambda e: e['candidates'][0].update(approved_candidate_git_blob_sha1='0' * 40),
                       lambda e: e['candidates'][0].update(first_introducing_commit='0' * 40),
                       lambda e: e['candidates'][0].update(previous_approved_candidate_git_blob_sha1='0' * 40),
                       lambda e: e['candidates'].append(dict(e['candidates'][0])),
                       lambda e: e.update(official_counted=1)):
            e = copy.deepcopy(base)
            mutate(e)
            with patch.object(vn, '_load', side_effect=lambda p, e=e: e if p == vn.ENTRY else json.loads(Path(p).read_text())):
                with self.assertRaisesRegex(FreezeViolation, 'UNAUTHORIZED'):
                    vn.run()

    def test_rejects_modified_record(self):
        rec = json.loads(vn.RECORD.read_text())
        for field, value in (('status', 'MERGED'), ('official_counted', 1), ('approved_stake_u', 1),
                             ('candidate_blob', '0' * 40), ('model_release_certified', True),
                             ('release', 'LIVE')):
            r = copy.deepcopy(rec)
            r[field] = value
            with patch.object(vn, '_load', side_effect=lambda p, r=r: r if p == vn.RECORD else json.loads(Path(p).read_text())):
                with self.assertRaisesRegex(FreezeViolation, 'RECORD_FIELD_INVALID'):
                    vn.check_record(vn.ROOT)

    def test_rejects_tampered_evidence_or_diff(self):
        rec = json.loads(vn.RECORD.read_text())
        r = copy.deepcopy(rec)
        r['equivalence']['evidence_git_blob_sha1'] = '0' * 40
        with patch.object(vn, '_load', side_effect=lambda p, r=r: r if p == vn.RECORD else json.loads(Path(p).read_text())):
            with self.assertRaisesRegex(FreezeViolation, 'EQUIVALENCE_EVIDENCE_MISMATCH'):
                vn.check_record(vn.ROOT)
        r = copy.deepcopy(rec)
        r['diff']['unified_diff_n0_sha256'] = '0' * 64
        with patch.object(vn, '_load', side_effect=lambda p, r=r: r if p == vn.RECORD else json.loads(Path(p).read_text())):
            with self.assertRaisesRegex(FreezeViolation, 'MODEL_DIFF_NOT_THE_RECORDED_DIFF'):
                vn.check_record(vn.ROOT)

    def test_rejects_non_first_introducing_commit_and_missing_history(self):
        real = vn.vt._git

        def fake(repo, *a):
            if a[:1] == ('rev-list',):
                return (vn.V2_COMMIT + ' parentA').encode()
            if a[:1] == ('show',) and a[1].startswith('parentA'):
                return b'something else'
            return real(repo, *a)
        with patch.object(vn.vt, '_git', side_effect=fake):
            with self.assertRaisesRegex(FreezeViolation, 'NOT_FIRST_INTRODUCING_COMMIT'):
                vn.check_chain_provenance(vn.ROOT)
        with patch.object(vn.vt, '_git', side_effect=FreezeViolation('UNVERIFIABLE_GIT_PROVENANCE:x')):
            with self.assertRaisesRegex(FreezeViolation, 'UNVERIFIABLE_GIT_PROVENANCE'):
                vn.check_chain_provenance(vn.ROOT)

    def test_rejects_changed_model_bytes(self):
        with patch.object(vn, 'verified_file', side_effect=FreezeViolation('CODE_CHANGED_SINCE_FREEZE:' + vn.NBA_PATH)):
            with self.assertRaisesRegex(FreezeViolation, 'CODE_CHANGED_SINCE_FREEZE'):
                vn.run()

    def test_nov15_and_nov18_authorities_are_untouched(self):
        self.assertEqual(git_blob_digest(vn.vt.LEGACY.read_bytes()), vn.vt.LEGACY_MANIFEST_BLOB)
        self.assertEqual(git_blob_digest(vn.vt.TRANSITION.read_bytes()), vn.NOV18_TRANSITION_BLOB)
        with patch.object(vn.vt, 'LEGACY', vn.vt.LEGACY):
            raw = vn.vt.LEGACY.read_bytes() + b' '
            with self.assertRaisesRegex(FreezeViolation, 'ORIGINAL_FREEZE_MANIFEST_MODIFIED'):
                vn.vt.checked_manifest(json.loads(raw), json.loads(vn.vt.TRANSITION.read_text()), raw)


if __name__ == '__main__':
    unittest.main()
