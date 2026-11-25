"""CBB re-pin evidence: pinned blob f02dd29e vs PR #292 candidate 8bbe83b7.

Fails closed if the pinned-blob copy is altered, if the live model is no longer the reviewed
candidate (a further change needs a NEW equivalence review), if the diff stops being exactly the two
reviewed prop-path hunks, if any game-path output differs bit for bit, or if the intended prop-path
differences stop behaving as documented. Also checks the PENDING_OWNER_MERGE record is consistent
with the immutable Nov 15 / Nov 18 pin manifests (which this change never edits).
"""
import difflib
import json
import unittest
from pathlib import Path

import cbb_repin_equivalence as E
from verify_code_freezes import git_blob_digest

HERE = Path(__file__).resolve().parent
RECORD = HERE / "repin_cbb_20261125.json"
EVIDENCE = HERE / "repin_cbb_20261125_equivalence.json"
LEGACY = HERE / "frozen_baselines_20261115.json"
TRANSITION = HERE / "code_identity_transitions_20261118.json"


class DiffShape(unittest.TestCase):
    def test_pinned_copy_and_candidate_identities(self):
        self.assertEqual(git_blob_digest(E.OLD_SRC.read_bytes()), E.PINNED_BLOB)
        self.assertEqual(git_blob_digest(E.NEW_SRC.read_bytes()), E.CANDIDATE_BLOB,
                         "live CBB model changed after the reviewed candidate: a new equivalence review is required")

    def test_diff_is_exactly_the_two_prop_path_hunks(self):
        old = E.OLD_SRC.read_text().splitlines()
        new = E.NEW_SRC.read_text().splitlines()
        ops = [o for o in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if o[0] != "equal"]
        # three opcodes = two unified-diff hunks (ops 2 and 3 sit two lines apart in run_card's prop loop)
        self.assertEqual(len(ops), 3)
        (t1, a1, a2, b1, b2), (t2, c1, c2, d1, d2), (t3, e1, e2, f1, f2) = ops
        # hunk 1: pure insertion of resolve_prop_player() between project_prop() and run_card()
        self.assertEqual((t1, a1, a2), ("insert", a1, a1))
        added1 = new[b1:b2]
        self.assertTrue(any(l.startswith("def resolve_prop_player(") for l in added1))
        self.assertEqual(sum(l.startswith("def ") for l in added1), 1)
        # hunk 2a: unknown game_id is recorded, not a KeyError abort
        self.assertEqual(t2, "insert")
        self.assertIn("PROP_EVENT_NOT_FOUND", "\n".join(new[d1:d2]))
        # hunk 2b: first-global-name-match lookup replaced by the event-scoped resolver
        removed = [l.strip() for l in old[e1:e2]]
        self.assertEqual(removed, ['pl = next((x for p_ in players.values() for x in p_ if x["player"] == p["player"]), None)',
                                   "if not pl: continue"])
        self.assertIn("resolve_prop_player(g, p, players)", "\n".join(new[f1:f2]))
        self.assertEqual(new[d2:f1], ['        g, pj = projs[p["game_id"]]'])
        # everything else, incl. every constant, projection, pricing and game-row line, is byte-identical
        self.assertEqual(old[:a1], new[:b1])
        self.assertEqual(old[a2:c1], new[b2:d1])
        self.assertEqual(old[c2:e1], new[d2:f1])
        self.assertEqual(old[e2:], new[f2:])


class Equivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep = E.build_report(quick=True)

    def test_game_path_bit_identical(self):
        r = self.rep
        self.assertEqual(r["old_blob_computed"], E.PINNED_BLOB)
        self.assertEqual(r["new_blob_computed"], E.CANDIDATE_BLOB)
        self.assertGreater(r["totals"]["games"], 500)
        self.assertGreater(r["totals"]["market_rows"], 10000)
        self.assertEqual(r["totals"]["game_proj_mismatch"], 0)
        self.assertEqual(r["totals"]["market_mismatch"], 0)
        for name, c in r["corpora"].items():
            p, rc = c["primitives"], c["run_card"]
            with self.subTest(corpus=name):
                self.assertEqual(p["game_projection_sha256_old"], p["game_projection_sha256_new"])
                self.assertEqual(p["market_sha256_old"], p["market_sha256_new"])
                for key in ("rows_identical", "game_rows_identical", "prop_rows_identical", "dropped_identical",
                            "projections_identical", "stacks_identical"):
                    self.assertTrue(rc[key], key)
                for f, v in rc["files"].items():
                    self.assertTrue(v["identical"], f)
        self.assertTrue(r["equivalent_game_path"])

    def test_uniquely_resolvable_props_unchanged(self):
        self.assertGreater(self.rep["totals"]["prop_rows"], 100)       # priced props agree bit for bit

    def test_intended_prop_differences(self):
        for c in self.rep["prop_cases"]:
            with self.subTest(case=c["name"]):
                self.assertEqual(c["actual"], c["expected"])
        by = {c["name"]: c for c in self.rep["prop_cases"]}
        self.assertEqual(by["unknown_game_id"]["old"]["status"], "crash")
        self.assertEqual(by["unknown_game_id"]["new"]["status"], "ok")
        self.assertTrue(by["same_name_on_both_event_teams_no_team_hint"]["new"]["dropped"][0].startswith("AMBIGUOUS_PROP_PLAYER"))
        self.assertTrue(self.rep["prop_cases_as_intended"])


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
        self.assertEqual(r["pinned_blob"], E.PINNED_BLOB)
        self.assertEqual(r["candidate_blob"], E.CANDIDATE_BLOB)
        self.assertEqual(r["change_pr"], 292)

    def test_record_matches_immutable_manifests_and_never_edits_them(self):
        legacy = json.loads(LEGACY.read_text())
        self.assertEqual(legacy["sports"]["CBB"]["sources"]["models/cbb/sportsedge_cbb_model.py"], E.PINNED_BLOB)
        self.assertEqual(git_blob_digest(LEGACY.read_bytes()), self.rec["immutable_inputs"]["legacy_manifest_git_blob_sha1"])
        self.assertEqual(git_blob_digest(TRANSITION.read_bytes()), self.rec["immutable_inputs"]["transition_manifest_git_blob_sha1"])
        cbb = [c for c in json.loads(TRANSITION.read_text())["candidates"] if c["sport"] == "CBB"][0]
        self.assertEqual((cbb["original_git_blob_sha1"], cbb["approved_candidate_git_blob_sha1"], cbb["change_pr"]),
                         (E.PINNED_BLOB, E.CANDIDATE_BLOB, 292))
        self.assertEqual(cbb["first_introducing_commit"], self.rec["first_introducing_commit"])

    def test_committed_full_evidence_is_clean_and_matches_record(self):
        ev = self.ev
        self.assertEqual(ev["mode"], "full")
        self.assertTrue(ev["equivalent_game_path"])
        self.assertTrue(ev["prop_cases_as_intended"])
        self.assertEqual(ev["totals"]["game_proj_mismatch"], 0)
        self.assertEqual(ev["totals"]["market_mismatch"], 0)
        self.assertEqual(ev["totals"], self.rec["equivalence"]["totals"])
        self.assertEqual(git_blob_digest(EVIDENCE.read_bytes()), self.rec["equivalence"]["evidence_git_blob_sha1"])

    def test_nba_mlb_drift_is_reported_not_repinned(self):
        self.assertFalse(self.rec["other_drift_not_repinned"]["repinned"])
        self.assertEqual(sorted(self.rec["other_drift_not_repinned"]["files"]), ["MLB", "NBA"])


if __name__ == "__main__":
    unittest.main()
