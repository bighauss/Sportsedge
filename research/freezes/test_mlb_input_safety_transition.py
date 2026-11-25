"""MLB input-safety transition evidence: approved blob 3f630532 -> current 30c6cb33 (commit b73874a, pr-446).

Fails closed if the pinned-blob copy is altered, if the live MLB model is no longer the reviewed candidate (a
further change needs a NEW review), if the diff stops being exactly the two reviewed loader hunks, if any
valid-input output differs bit for bit, if the fail-closed contract weakens, if the candidate manifest or record is
inconsistent with the immutable Nov 15 / Nov 18 manifests and stock verifiers (which this change never edits), or
if the additive verifier stops reporting every sport honestly.
"""
import copy
import csv
import difflib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import mlb_input_safety_equivalence as E
import verify_versioned_transition as VT
from verify_code_freezes import FreezeViolation, git_blob_digest, verified_file

HERE = Path(__file__).resolve().parent
RECORD = HERE / "transition_mlb_input_safety_20261125.json"
EVIDENCE = HERE / "transition_mlb_input_safety_20261125_equivalence.json"
CANDIDATE = HERE / "code_identity_transitions_20261125_mlb_candidate.json"
LEGACY = HERE / "frozen_baselines_20261115.json"
NOV18 = HERE / "code_identity_transitions_20261118.json"
MODEL_PATH = "models/mlb/sportsedge_mlb_model.py"


def _csv(td, name, body):
    p = os.path.join(td, name)
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    return p


class DiffShape(unittest.TestCase):
    def test_pinned_copy_and_candidate_identities(self):
        self.assertEqual(git_blob_digest(E.OLD_SRC.read_bytes()), E.APPROVED_BLOB)
        self.assertEqual(git_blob_digest(E.NEW_SRC.read_bytes()), E.CURRENT_BLOB,
                         "live MLB model changed after the reviewed candidate: a new equivalence review is required")

    def test_diff_is_exactly_the_two_loader_hunks(self):
        old = E.OLD_SRC.read_text().splitlines()
        new = E.NEW_SRC.read_text().splitlines()
        ops = [o for o in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if o[0] != "equal"]
        self.assertEqual(len(ops), 2)
        (t1, a1, a2, b1, b2), (t2, c1, c2, d1, d2) = ops
        # hunk 1: pure insertion of class DuplicateInputKey
        self.assertEqual((t1, a1, a2), ("insert", a1, a1))
        self.assertEqual(new[b1:b2], ['class DuplicateInputKey(ValueError):',
                                      '    """A keyed input file repeats a key; never let the later row silently win."""',
                                      '', ''])
        # hunk 2: load_keyed's one-line body replaced
        self.assertEqual(t2, "replace")
        self.assertEqual([l.strip() for l in old[c1:c2]], ["return {r[key]: r for r in load_csv(path)}"])
        self.assertEqual(new[d1], "    out = {}")
        self.assertEqual(new[d2 - 1], "    return out")
        self.assertEqual(d2 - d1, 9)
        # every other line, incl. all constants, projection, pricing and prop code, is byte-identical
        self.assertEqual(old[:a1], new[:b1])
        self.assertEqual(old[a2:c1], new[b2:d1])
        self.assertEqual(old[c2:], new[d2:])
        self.assertEqual((b2 - b1) + (d2 - d1), 13)

    def test_only_load_keyed_is_touched(self):
        old = E.OLD_SRC.read_text()
        new = E.NEW_SRC.read_text()
        for name in ("def pitcher_profile", "def project_game", "def price_game", "def run_card", "def prop_models",
                     "def _pair_game_odds", "def preflight_game_inputs", "def load_csv", "def load_inputs"):
            a = old[old.index(name):].split("\n\n\n")[0]
            b = new[new.index(name):].split("\n\n\n")[0]
            self.assertEqual(a, b, name)


class FailClosedContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.new = E.load_module(E.NEW_SRC, "mlb_current_for_tests")[0]
        cls.old = E.load_module(E.OLD_SRC, "mlb_approved_for_tests")[0]

    def test_exception_is_a_valueerror(self):
        self.assertTrue(issubclass(self.new.DuplicateInputKey, ValueError))

    def test_duplicate_key_refused_with_line_number_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            p = _csv(td, "pitchers.csv", "player_id,team,k9\na,A,9.1\nb,H,7.0\na,A,4.0\n")
            with self.assertRaisesRegex(self.new.DuplicateInputKey, r"pitchers\.csv line 4: duplicate player_id=a"):
                self.new.load_keyed(p, "player_id")
            old = self.old.load_keyed(p, "player_id")           # the defect being closed: later row silently wins
            self.assertEqual(old["a"]["k9"], "4.0")

    def test_duplicate_after_whitespace_strip_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p = _csv(td, "bullpen.csv", "team,ip\nBOS,400\n BOS ,300\n")
            with self.assertRaisesRegex(self.new.DuplicateInputKey, "duplicate team=BOS"):
                self.new.load_keyed(p, "team")

    def test_blank_missing_and_whitespace_keys_refused(self):
        cases = {"blank first row": "player_id,team\n,A\n", "blank after good row": "player_id,team\na,A\n,H\n",
                 "whitespace only": "player_id,team\n   ,A\n", "short row, key cell absent": "team,player_id\nA\n"}
        for label, body in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as td:
                p = _csv(td, "batters.csv", body)
                with self.assertRaisesRegex(self.new.DuplicateInputKey, "missing player_id"):
                    self.new.load_keyed(p, "player_id")
                self.assertIn(None if "absent" in label else "", self.old.load_keyed(p, "player_id"))   # old stored junk key

    def test_key_column_absent_from_header_refused_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = _csv(td, "parks.csv", "name,pf_hr\nPark A,100\n")
            with self.assertRaises(self.new.DuplicateInputKey):
                self.new.load_keyed(p, "park")
            with self.assertRaises(KeyError):                    # already failed closed (differently) before
                self.old.load_keyed(p, "park")

    def test_malformed_files_still_fail_closed_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            ragged = _csv(td, "r.csv", "player_id,team\na,A,EXTRA\n")
            bad = os.path.join(td, "u.csv")
            Path(bad).write_bytes(b"player_id,team\na\xff\xfeb,A\n")
            for mod in (self.old, self.new):
                with self.assertRaises(AttributeError):
                    mod.load_keyed(ragged, "player_id")
                with self.assertRaises(UnicodeDecodeError):
                    mod.load_keyed(bad, "player_id")

    def test_valid_files_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            for body in ("player_id,team\na,A\nb,H\n", "player_id,team\na,A\nA,H\n", "player_id,team\n",
                         "\ufeffplayer_id,team\n a ,A\nb,H\n"):
                p = _csv(td, "x.csv", body)
                self.assertEqual(E.digest(self.old.load_keyed(p, "player_id")), E.digest(self.new.load_keyed(p, "player_id")))
            self.assertEqual(self.new.load_keyed(os.path.join(td, "nope.csv"), "player_id"), {})

    def test_every_keyed_input_file_is_guarded_through_load_inputs_and_run_card(self):
        files = {"pitchers.csv": "player_id", "batters.csv": "player_id", "bullpen.csv": "team",
                 "parks.csv": "park", "defense.csv": "team"}
        for fname, key in files.items():
            for defect in ("duplicate", "blank"):
                with self.subTest(file=fname, defect=defect), tempfile.TemporaryDirectory() as td:
                    sdir = E.make_sample_folder(Path(td))
                    with open(sdir / fname, newline="") as fh:
                        rows = list(csv.DictReader(fh))
                    bad = dict(rows[0])
                    if defect == "blank":
                        bad[key] = ""
                    E.write_csv(sdir / fname, rows + [bad], cols=list(rows[0].keys()))
                    with self.assertRaises(self.new.DuplicateInputKey):
                        self.new.load_inputs(str(sdir))
                    with self.assertRaises(self.new.DuplicateInputKey):
                        self.new.run_card(str(sdir), out_dir=os.path.join(td, "out"))
                    self.old.run_card(str(sdir), out_dir=os.path.join(td, "oldout"))   # old silently priced it

    def test_negative_matrix_and_duplicate_starter_demo(self):
        rep_old, _, rep_new, _ = E.load_pair()
        for c in E.NEG_CASES:
            r = E.run_neg_case(rep_old, rep_new, *c)
            with self.subTest(case=c[0]):
                self.assertTrue(r["as_intended"], r)
        self.assertTrue(E.run_card_duplicate_demo(rep_old, rep_new)["as_intended"])


class Equivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep = E.build_report(quick=True)

    def test_valid_input_bit_identical(self):
        r = self.rep
        self.assertEqual(r["old_blob_computed"], E.APPROVED_BLOB)
        self.assertEqual(r["new_blob_computed"], E.CURRENT_BLOB)
        t = r["totals"]
        self.assertGreater(t["games_priced"], 100)
        self.assertGreater(t["market_evals"], 1000)
        self.assertGreater(t["card_rows"], 500)
        self.assertGreater(t["prop_rows"], 100)
        self.assertEqual((t["folders_not_identical"], t["projection_mismatches"], t["market_eval_mismatches"]), (0, 0, 0))
        self.assertTrue(r["valid_input_bit_identical"])
        self.assertTrue(r["negative_cases_as_intended"])


class RecordConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = json.loads(RECORD.read_text())
        cls.ev = json.loads(EVIDENCE.read_text())

    def test_record_is_pending_and_zero_release(self):
        r = self.rec
        self.assertEqual(r["status"], "PENDING_OWNER_MERGE")
        self.assertEqual(r["recording_act"], "OWNER_MERGE")
        self.assertEqual((r["official_counted"], r["approved_stake_u"]), (0, 0))
        self.assertEqual(r["release"], "PAPER_0U")
        self.assertFalse(r["model_release_certified"])
        self.assertFalse(r["source_authenticated"])
        self.assertEqual(r["approved_blob"], E.APPROVED_BLOB)
        self.assertEqual(r["candidate_blob"], E.CURRENT_BLOB)
        self.assertEqual(r["change_pr"], 446)
        self.assertEqual(r["diff_classification"]["coefficients"], 0)
        self.assertEqual(r["diff_classification"]["pricing_path"], 0)
        self.assertEqual(r["diff_classification"]["game_projection_path"], 0)

    def test_committed_full_evidence_is_clean_and_matches_record(self):
        ev = self.ev
        self.assertEqual(ev["mode"], "full")
        self.assertTrue(ev["valid_input_bit_identical"])
        self.assertTrue(ev["negative_cases_as_intended"])
        self.assertTrue(ev["run_card_duplicate_demo"]["as_intended"])
        self.assertEqual(ev["totals"]["folders_not_identical"], 0)
        self.assertEqual(ev["totals"]["projection_mismatches"], 0)
        self.assertEqual(ev["totals"]["market_eval_mismatches"], 0)
        self.assertEqual(ev["totals"], self.rec["equivalence"]["totals"])
        self.assertEqual(git_blob_digest(EVIDENCE.read_bytes()), self.rec["equivalence"]["evidence_git_blob_sha1"])

    def test_immutable_inputs_never_edited(self):
        i = self.rec["immutable_inputs"]
        self.assertEqual(git_blob_digest(LEGACY.read_bytes()), i["legacy_manifest_git_blob_sha1"])
        self.assertEqual(git_blob_digest(NOV18.read_bytes()), i["nov18_transition_manifest_git_blob_sha1"])
        self.assertEqual(git_blob_digest((HERE / "verify_code_freezes.py").read_bytes()), i["verify_code_freezes_git_blob_sha1"])
        self.assertFalse(i["nov15_and_nov18_and_code_freezes_verifier_edited_by_this_change"])
        # The stock verifier is the reviewed Option B edit; its hash is pinned in the hops file.
        self.assertEqual(git_blob_digest((HERE / "verify_versioned_transition.py").read_bytes()),
                         i["verify_versioned_transition_git_blob_sha1"])
        hops = json.loads((HERE / "code_identity_transitions_20261125.json").read_text())
        self.assertEqual(hops["verify_versioned_transition_git_blob_sha1"],
                         i["verify_versioned_transition_git_blob_sha1"])

    def test_candidate_manifest_chains_to_nov18_manifest(self):
        cand = json.loads(CANDIDATE.read_text())
        self.assertEqual(cand["status"], "PENDING_OWNER_MERGE")
        nov18 = {c["sport"]: c for c in json.loads(NOV18.read_text())["candidates"]}["MLB"]
        c = cand["candidates"][0]
        self.assertEqual(c["original_git_blob_sha1"], nov18["original_git_blob_sha1"])
        self.assertEqual(c["prior_approved_candidate_git_blob_sha1"], nov18["approved_candidate_git_blob_sha1"])
        self.assertEqual(c["prior_first_introducing_commit"], nov18["first_introducing_commit"])
        self.assertEqual(c["prior_change_pr"], nov18["change_pr"])
        self.assertEqual(c["approved_candidate_git_blob_sha1"], self.rec["candidate_blob"])
        self.assertEqual(c["first_introducing_commit"], self.rec["first_introducing_commit"])
        legacy = json.loads(LEGACY.read_text())
        self.assertEqual(legacy["sports"]["MLB"]["sources"][MODEL_PATH], c["original_git_blob_sha1"])

    def test_nba_hop_is_registered_with_evidence_cited(self):
        nba = self.rec["other_drift_not_handled"]["NBA"]
        self.assertTrue(nba["incorporated_on_this_branch"])
        self.assertIn("737dd2a3", nba["evidence_source"])
        hops = json.loads((HERE / "code_identity_transitions_20261125.json").read_text())
        sports = {c["sport"]: c for c in hops["candidates"]}
        self.assertEqual(sports["NBA"]["approved_candidate_git_blob_sha1"], nba["approved_candidate"])
        self.assertEqual(sports["NBA"]["first_introducing_commit"], nba["commit"])


class UnifiedVerifierHook(unittest.TestCase):
    """The standalone MLB verifier is retired; the stock verifier is the only gate."""

    def test_stock_verifier_accepts_mlb_hop(self):
        rec = json.loads(RECORD.read_text())
        rep = VT.run()
        self.assertEqual(rep['status'], 'VERSIONED_CODE_IDENTITY_ONLY_PAPER_0U')
        mlb = [h for h in rep['additional_hops'] if h['sport'] == 'MLB'][0]
        self.assertEqual(mlb['candidate_git_blob_sha1'], E.CURRENT_BLOB)
        self.assertEqual(mlb['from_git_blob_sha1'], E.APPROVED_BLOB)
        self.assertEqual(mlb['introducing_commit'], rec['first_introducing_commit'])

    def test_standalone_mlb_verifier_is_not_the_gate(self):
        workflow = (HERE.parents[1] / '.github/workflows/risk-lock-research.yml').read_text()
        self.assertIn('verify_versioned_transition.py', workflow)
        self.assertNotIn('verify_mlb_input_safety_transition.py', workflow)



if __name__ == "__main__":
    unittest.main()
