"""Offline regression tests for the opt-in public-replay ratings bridge (PAPER/0u)."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import cbb_run_it_pipeline as PIPE
import cbbd_paper_synthetic as S
import public_replay_adapted as A

FREEZE = "2026-11-25T17:25:00Z"
FREEZE_DT = datetime(2026, 11, 25, 17, 25, tzinfo=timezone.utc)
CFG = {"sd_margin": 11.8, "sd_total": 17.2}


def game(gid, home="1", away="2", neutral=False):
    return {"id": gid, "home_id": home, "away_id": away, "neutral": neutral, "home_score": 70,
            "away_score": 60, "possessions": 68.0, "tip_utc": "2026-11-20T18:00Z"}


def evidence(kind, ids, **over):
    doc = {"schema": A.EVIDENCE_SCHEMA, "kind": kind, "season": 2027, "source": "SYNTHETIC_TEST",
           "source_sha256": "a" * 64, "captured_utc": "2026-11-24T00:00:00Z", "ids": list(ids)}
    doc.update(over)
    return doc


class Admission(unittest.TestCase):
    def test_evidence_is_required_not_inferred(self):
        with self.assertRaisesRegex(ValueError, "D1_MEMBERSHIP_EVIDENCE_REQUIRED"):
            A.admit([game("a")], d1_ids=None, verified_home_ids=set())
        with self.assertRaisesRegex(ValueError, "VENUE_EVIDENCE_REQUIRED"):
            A.admit([game("a")], d1_ids={"1", "2"}, verified_home_ids=None)

    def test_site_rules_and_counts(self):
        prior = [game("a", neutral=True), game("b"), game("c"), game("d", neutral=None),
                 game("e", home="x1")]
        games, by_id, census = A.admit(prior, d1_ids={"1", "2"}, verified_home_ids={"b"})
        sites = {g["game_id"]: g["site"] for g in games}
        self.assertEqual(sites, {"a": "NEUTRAL", "b": "HOME_VERIFIED"})
        self.assertEqual(census, {"dropped_bad_team_id": 1, "dropped_site_unknown": 1,
                                  "dropped_home_unverified": 1})
        self.assertEqual(set(by_id), {"a", "b"})
        self.assertEqual(games[0]["date"], "2026-11-20")


class EvidenceValidation(unittest.TestCase):
    def check(self, doc, kind=A.KIND_D1):
        return A.validate_evidence(doc, kind=kind, season=2027, freeze=FREEZE_DT)

    def test_valid_document_round_trips_through_builder(self):
        doc = A.build_evidence_doc(kind=A.KIND_D1, ids=["2", "1", "1"], season=2027,
                                   source_label="SYNTHETIC_TEST", source_bytes=b"id\n1\n2\n",
                                   captured_utc="2026-11-24T00:00:00Z")
        ids, meta = self.check(doc)
        self.assertEqual(ids, {"1", "2"})
        self.assertEqual(len(meta["source_sha256"]), 64)

    def test_each_provenance_field_is_enforced(self):
        cases = [(None, "D1_MEMBERSHIP_EVIDENCE_REQUIRED"),
                 (evidence(A.KIND_D1, ["1"], schema="X"), "EVIDENCE_SCHEMA_INVALID"),
                 (evidence(A.KIND_VENUE, ["1"]), "EVIDENCE_KIND_MISMATCH"),
                 (evidence(A.KIND_D1, ["1"], season=2026), "EVIDENCE_SEASON_MISMATCH"),
                 (evidence(A.KIND_D1, ["1"], source=" "), "EVIDENCE_SOURCE_MISSING"),
                 (evidence(A.KIND_D1, ["1"], source_sha256="abc"), "EVIDENCE_SOURCE_HASH_INVALID"),
                 (evidence(A.KIND_D1, ["1"], captured_utc="2026-11-24"), "EVIDENCE_CAPTURED_UTC_INVALID"),
                 (evidence(A.KIND_D1, ["1"], captured_utc=FREEZE), "EVIDENCE_AFTER_FREEZE"),
                 (evidence(A.KIND_D1, ["1", "1"]), "EVIDENCE_IDS_INVALID"),
                 (evidence(A.KIND_D1, []), "D1_MEMBERSHIP_EVIDENCE_REQUIRED")]
        for doc, code in cases:
            with self.subTest(code=code):
                with self.assertRaisesRegex(ValueError, code):
                    self.check(doc)


class LegacyBody(unittest.TestCase):
    def body(self, **over):
        rows = [{"team": "10", "teamId": 10, "offensiveRating": 105.12345, "defensiveRating": 100.0,
                 "netRating": 5.1, "pace": 69.0, "n_games": 3},
                {"team": "20", "teamId": 20, "offensiveRating": 101.0, "defensiveRating": 102.0,
                 "netRating": -1.0, "pace": 68.0, "n_games": 0}]
        rows[0].update(over)
        return json.dumps(rows).encode()

    def test_schema_and_zero_game_teams(self):
        legacy = json.loads(A.to_legacy_body(self.body(), 2027))
        self.assertEqual(legacy, [{"season": 2027, "teamId": 10, "team": "10", "offensiveRating": 105.123,
                                   "defensiveRating": 100.0, "netRating": 5.123, "games": 3}])
        both = json.loads(A.to_legacy_body(self.body(), 2027, include_zero_game_teams=True))
        self.assertEqual([r["teamId"] for r in both], [10, 20])

    def test_contract_violations_raise(self):
        with self.assertRaisesRegex(ValueError, "RATINGS_OUT_OF_CONTRACT"):
            A.to_legacy_body(self.body(offensiveRating=170.0), 2027)
        with self.assertRaisesRegex(ValueError, "RATINGS_BAD_TEAM_ID"):
            A.to_legacy_body(self.body(team="abc"), 2027)


class RuntimeIsolation(unittest.TestCase):
    def test_bridge_fails_closed_without_evidence(self):
        project = A.make_public_replay_project(d1_evidence=None, venue_evidence=None)
        out, leak, body = project({}, [], 2027, FREEZE, CFG)
        self.assertEqual(out, {})
        self.assertIn("D1_MEMBERSHIP_EVIDENCE_REQUIRED", leak["reason"])
        self.assertEqual(body, b"")

    def test_install_restores_legacy_function(self):
        original = PIPE.public_replay_project
        sentinel = lambda *a, **k: None
        previous = A.install(sentinel)
        try:
            self.assertIs(previous, original)
            self.assertIs(PIPE.public_replay_project, sentinel)
        finally:
            PIPE.public_replay_project = previous
        self.assertIs(PIPE.public_replay_project, original)
        self.assertTrue(callable(PIPE.d1_filter))
        self.assertTrue(callable(PIPE.public_ratings))


class PositivePath(unittest.TestCase):
    """Real adapter + real native fit_context + real projections on synthetic finals."""

    def setUp(self):
        self.games = {}
        for r in S.prior_games():
            self.games[r["game_id"]] = {
                "id": r["game_id"], "completed": True, "possessions": r["possessions"],
                "tip_utc": r["tipoff_utc"], "home_id": r["home_team_id"], "away_id": r["away_team_id"],
                "neutral": r["neutral"], "home_score": r["home_points"], "away_score": r["away_points"]}
        # tip + 3h == freeze exactly: must be excluded by the strict native cutoff.
        self.games["edge"] = {"id": "edge", "completed": True, "possessions": 68.0,
                              "tip_utc": "2026-11-25T14:25:00Z", "home_id": "11", "away_id": "12",
                              "neutral": True, "home_score": 70, "away_score": 60}
        slate = {"9001": ("1", "2", False), "9002": ("3", "4", True),
                 "9003": ("5", "6", False), "9004": ("7", "8", None)}
        for gid, (h, a, n) in slate.items():
            self.games[gid] = {"id": gid, "completed": False, "possessions": None,
                               "tip_utc": "2026-11-25T23:00:00Z", "home_id": h, "away_id": a,
                               "neutral": n, "home_score": None, "away_score": None}
        self.slate_ids = list(slate)
        prior_home = [g["id"] for g in self.games.values() if g["completed"] and g["neutral"] is False]
        self.d1 = evidence(A.KIND_D1, [str(i) for i in range(1, 41)])
        self.venue = evidence(A.KIND_VENUE, prior_home + ["9001"])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.finals = Path(self.tmp.name) / "finals.json"
        self.finals.write_text(json.dumps(
            {"2026": [{str(i): [0.0, 0.0, 0.0] for i in range(1, 41)}, 105.0, 69.0, 3.8]}))

    def run_bridge(self, finals=True):
        project = A.make_public_replay_project(
            d1_evidence=self.d1, venue_evidence=self.venue,
            finals_path=str(self.finals) if finals else None)
        return project(self.games, self.slate_ids, 2027, FREEZE, CFG)

    def test_projection_runs_end_to_end(self):
        out, leak, body = self.run_bridge()
        self.assertNotIn("reason", leak, leak.get("reason"))
        self.assertEqual(leak["ratings_engine"], A.ENGINE)
        self.assertEqual(leak["prior_raw"], 200)  # the freeze-boundary final is excluded
        self.assertGreater(leak["prior_finals_used"], 0)
        self.assertEqual(leak["sample_identity"]["status"], "MATCH", leak["sample_identity"])
        self.assertIn("ONCE", leak["hca_policy"])
        self.assertIsNotNone(leak["hca"]["value"])
        self.assertEqual(out["9001"].status, "PROJECTED", out["9001"])
        self.assertEqual(out["9002"].status, "PROJECTED", out["9002"])
        self.assertIsNotNone(out["9001"].margin)
        self.assertGreater(len(body), 0)

    def test_unverified_home_and_unknown_site_do_not_get_hca(self):
        out, leak, _ = self.run_bridge()
        self.assertEqual(out["9003"].status, "PASS")
        self.assertIn("HOME_VENUE_UNVERIFIED", out["9003"].reason_code)
        self.assertEqual(out["9004"].status, "PASS")
        self.assertIn("NEUTRAL_SITE_UNKNOWN", out["9004"].reason_code)


if __name__ == "__main__":
    unittest.main()
