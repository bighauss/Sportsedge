"""Offline tests for the public ESPN evidence capture helpers (no network)."""
import json
import unittest

from tools import cbb_fetch_evidence as E


def event(gid, neutral, venue, home_team="1"):
    comp = {"competitors": [{"homeAway": "away", "team": {"id": "2"}},
                            {"homeAway": "home", "team": {"id": home_team}}],
            "venue": {"id": venue} if venue else {}}
    if neutral is not None:
        comp["neutralSite"] = neutral
    return {"id": gid, "competitions": [comp]}


class Helpers(unittest.TestCase):
    def test_team_ids_and_count_range(self):
        raw = json.dumps({"sports": [{"leagues": [{"teams": [
            {"team": {"id": "5"}}, {"team": {"id": 3}}, {"team": {"id": "5"}}]}]}]}).encode()
        self.assertEqual(E.parse_team_ids(raw), ["3", "5"])
        self.assertFalse(E.d1_count_ok(2))
        self.assertTrue(E.d1_count_ok(362))

    def test_team_venue_parsing_uses_documented_fields_only(self):
        site = json.dumps({"team": {"franchise": {"venue": {"id": "77"}}}}).encode()
        self.assertEqual(E.parse_team_venue(site), "77")
        core = json.dumps({"venue": {"$ref": "http://sports.core.api.espn.com/v2/sports/basketball/"
                                              "leagues/mens-college-basketball/venues/3984?lang=en"}}).encode()
        self.assertEqual(E.parse_team_venue(core), "3984")
        self.assertEqual(E.parse_team_venue(json.dumps({"venue": {"id": 12}}).encode()), "12")
        self.assertIsNone(E.parse_team_venue(json.dumps({"team": {"name": "x"}}).encode()))
        self.assertIsNone(E.parse_team_venue(json.dumps({"venue": {"fullName": "Arena"}}).encode()))
        self.assertIsNone(E.parse_team_venue(json.dumps([1, 2]).encode()))

    def test_venue_key_paths_for_schema_inspection(self):
        doc = {"team": {"venue": {"id": "1"}, "links": [{"venueUrl": "x"}]}, "other": 1}
        paths = E.venue_key_paths(doc)
        self.assertIn("/team/venue", paths)
        self.assertIn("/team/links[]/venueUrl", paths)

    def test_home_verification_rules(self):
        doc = {"events": [
            event("a", False, "77"),      # verified
            event("b", True, "77"),       # neutral
            event("c", None, "77"),       # neutral flag absent -> unknown
            event("d", False, "99"),      # venue differs from the home team's venue
            event("e", False, None),      # event venue missing
            event("f", False, "77", home_team="9"),  # home team venue unknown
            {"id": "g", "competitions": []},
        ]}
        verified, census = E.classify_events(doc, {"1": "77"})
        self.assertEqual(verified, ["a"])
        self.assertEqual(census["neutral_or_unknown"], 2)
        self.assertEqual(census["venue_mismatch"], 1)
        self.assertEqual(census["venue_missing"], 2)
        self.assertEqual(census["no_competition"], 1)
        self.assertEqual(census["events"], 7)


if __name__ == "__main__":
    unittest.main()
