"""Offline contract tests for public ESPN college availability intake; synthetic fixtures only."""
import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from espn_college_availability_intake import (
    Refused, get_bytes, make_report, persist, roster_athletes,
    slate_rows, url_for,
)


def enc(x):
    return json.dumps(x, separators=(",", ":")).encode("utf-8")


class Intake(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.at = datetime(2026, 11, 21, 13, 0, tzinfo=timezone.utc)
        self.games = [
            dict(sport="CFB", event_id="f1", kickoff_utc="2026-11-21T18:00:00Z",
                 home="Alpha State", away="Beta State", home_espn_id="1", away_espn_id="2"),
            dict(sport="CBB", event_id="b1", kickoff_utc="2026-11-21T19:00:00Z",
                 home="Hoops A", away="Hoops B", home_espn_id="3", away_espn_id="4"),
        ]
        self.sources = {
            "CFB:league_injuries:league": {"injuries": [
                {"team": {"id": "1"}, "athlete": {"id": "10", "displayName": "A QB"},
                 "status": "Out", "date": "2026-11-20T22:00:00Z", "injury": {"type": "Knee"}}]},
            "CBB:league_injuries:league": {"injuries": []},
            "CFB:roster:1": {"athletes": [{"position": "QB", "items": [
                {"id": "10", "displayName": "A QB", "position": {"abbreviation": "QB"}}]}]},
            "CFB:roster:2": {"athletes": [{"id": "20", "displayName": "B QB",
                                         "position": {"abbreviation": "QB"}}]},
            "CBB:roster:3": {"athletes": [{"id": "30", "displayName": "Hoops Star",
                                          "position": {"abbreviation": "G"}}]},
            "CBB:roster:4": {"athletes": [{"id": "40", "displayName": "Hoops Wing",
                                          "position": {"abbreviation": "F"}}]},
            "CFB:depthcharts:1": {"depthchart": {"QB": ["A QB"]}},
            "CFB:depthcharts:2": {},
            "CBB:injuries:3": {"injuries": [
                {"team": {"id": "3"}, "athlete": {"id": "30", "displayName": "Hoops Star"},
                 "status": "Questionable", "date": "2026-11-20T00:00:00Z"}]},
            "CBB:injuries:4": {"injuries": []}
        }

    def fetch(self, _url, key):
        return enc(self.sources[key])

    def report(self):
        return make_report(self.games, self.fetch, self.at, fixtures=True)

    def test_cbb_team_injury_captured_for_review(self):
        r, _ = self.report()
        q = [x for x in r["candidate_injuries"] if x["sport"] == "CBB"]
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["team"], "Hoops A")
        self.assertEqual(q[0]["athlete_id"], "30")
        self.assertEqual(q[0]["status"], "questionable")
        self.assertEqual(q[0]["model_role"], "")
        self.assertEqual(q[0]["approved_for_model"], "false")

    def test_qb_out_is_not_starter_confirmed_or_auto_penalized(self):
        r, _ = self.report()
        q = [x for x in r["candidate_injuries"] if x["sport"] == "CFB"]
        self.assertEqual(len(q), 1)
        self.assertIn("QB_STARTER_UNCONFIRMED", q[0]["reason_codes"])
        self.assertEqual(q[0]["impact"], "")
        self.assertTrue(all(x["starter_confirmed"] == "false" for x in r["qb_review"]))
        self.assertEqual(len(r["qb_review"]), 2)
        self.assertEqual(r["official_wagers"], 0)

    def test_empty_feed_is_unknown_not_healthy(self):
        r, _ = self.report()
        cbb = [x for x in r["coverage"] if x["sport"] == "CBB"]
        self.assertTrue(all(x["official_eligibility"] is False for x in cbb))
        self.assertIn("INJURY_FEED_EMPTY_UNKNOWN", cbb[0]["reason_codes"])
        self.assertEqual(len(r["coverage"]), 4)

    def test_roster_missing_blocks_auto_matching(self):
        self.sources["CFB:roster:1"] = {}
        r, _ = self.report()
        q = [x for x in r["candidate_injuries"] if x["team"] == "Alpha State"][0]
        self.assertIn("ROSTER_UNRECOGNIZED", q["reason_codes"])
        self.assertIn("ATHLETE_ID_OR_NAME_ROSTER_MISMATCH", q["reason_codes"])

    def test_reject_conflicting_injury_status(self):
        self.sources["CFB:league_injuries:league"]["injuries"].append({
            "team": {"id": "1"}, "athlete": {"id": "10", "displayName": "A QB"},
            "status": "Questionable", "date": "2026-11-20T22:00:00Z"})
        r, _ = self.report()
        q = [x for x in r["candidate_injuries"] if x["team"] == "Alpha State"]
        self.assertEqual(len(q), 2)
        self.assertTrue(all("CONFLICTING_INJURY_STATUSES" in x["reason_codes"] for x in q))

    def test_failure_is_not_empty_response(self):
        del self.sources["CFB:league_injuries:league"]
        r, _ = make_report(self.games, self.fetch, self.at, fixtures=True)
        c = [x for x in r["coverage"] if x["sport"] == "CFB"][0]
        self.assertIn("INJURY_ENDPOINT_UNAVAILABLE_OR_INVALID", c["reason_codes"])
        self.assertNotIn("INJURY_FEED_EMPTY_UNKNOWN", c["reason_codes"])

    def test_model_team_id_conflicts_refused(self):
        self.games.append(dict(sport="CFB", event_id="f2", kickoff_utc="2026-11-21T22:00:00Z",
                               home="Other Name", away="Beta State", home_espn_id="1", away_espn_id="2"))
        with self.assertRaisesRegex(Refused, "TEAM_ID_NAME_CONFLICT"):
            self.report()

    def test_late_source_labeled_not_pregame(self):
        self.games[0]["kickoff_utc"] = "2026-11-21T12:00:00Z"
        r, _ = self.report()
        q = [x for x in r["candidate_injuries"] if x["team"] == "Alpha State"][0]
        self.assertIn("CAPTURE_NOT_PREGAME", q["reason_codes"])
        self.assertFalse(r["coverage"][0]["official_eligibility"])

    def test_unknown_status_not_promoted(self):
        self.sources["CFB:league_injuries:league"]["injuries"][0]["status"] = "Clear"
        q = self.report()[0]["candidate_injuries"][0]
        self.assertIn("UNKNOWN_INJURY_STATUS", q["reason_codes"])

    def test_duplicate_roster_names_quarantined(self):
        self.sources["CFB:roster:1"]["athletes"][0]["items"].append(
            {"id": "11", "displayName": "A QB", "position": {"abbreviation": "QB"}})
        q = [x for x in self.report()[0]["candidate_injuries"] if x["team"] == "Alpha State"][0]
        self.assertIn("ROSTER_AMBIGUOUS", q["reason_codes"])

    def test_receipts_are_exact_bytes_and_create_only(self):
        r, sources = self.report()
        out = self.root / "run"
        persist(r, sources, out)
        contents = (out / "raw_espn" / "CFB__league_injuries__league.json").read_bytes()
        self.assertEqual(hashlib.sha256(contents).hexdigest(),
                         r["sources"]["CFB:league_injuries:league"]["sha256"])
        self.assertTrue((out / "injury_candidates_FOR_REVIEW.csv").exists())
        self.assertFalse((out / "injuries.csv").exists())
        with self.assertRaises(FileExistsError):
            persist(r, sources, out)

    def test_validate_slate_and_url(self):
        self.assertTrue(url_for("CFB", "league_injuries").endswith("/injuries"))
        with self.assertRaises(Refused):
            url_for("CFB", "roster", "1/../../secret")
        p = self.root / "slate.csv"
        with p.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(self.games[0].keys()))
            w.writeheader()
            w.writerow(self.games[0])
        self.assertEqual(len(slate_rows(p)), 1)
        p.write_text(p.read_text().replace("1,2", "1,1"))
        with self.assertRaisesRegex(Refused, "SAME_TEAM"):
            slate_rows(p)

    def test_malformed_roster_not_clean_health(self):
        players, state = roster_athletes({"athletes": [{}]})
        self.assertEqual(state, "ROSTER_UNRECOGNIZED")
        self.assertEqual(players, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
