"""Direct-model and card-level regressions for cfb_neutral_strict (issue #432)."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sportsedge_cfb_model as M
import cfb_neutral_strict as S


def _row(team):
    return {"team": team, "games": 10,
            "offense": {"plays": 700, "drives": 120, "ppa": 0.2, "successRate": 0.45,
                        "explosiveness": 1.2, "pointsPerOpportunity": 4.5,
                        "passingPlays": {"rate": 0.5, "ppa": 0.25},
                        "rushingPlays": {"ppa": 0.1}},
            "defense": {"ppa": 0.15, "successRate": 0.42, "explosiveness": 1.1,
                        "pointsPerOpportunity": 4.2, "havoc": {"total": 0.15},
                        "passingPlays": {"ppa": 0.2}, "rushingPlays": {"ppa": 0.1}}}


def _ctx():
    rows = [_row("Home U"), _row("Away U")]
    return {"adv": {r["team"]: r for r in rows}, "lm": M.league_means(rows), "talent": {},
            "ret": {}, "ratings": {}, "teams": {}, "venues": {}, "injuries": [],
            "weather": {}, "rest": {}, "cross": {}, "usage": []}


def _game(**kw):
    g = {"id": 1, "week": 10, "homeTeam": "Home U", "awayTeam": "Away U", "venue": "V"}
    g.update(kw)
    return g


class NeutralStrict(unittest.TestCase):
    def test_pinned_model_blob_unchanged(self):
        data = (HERE / "sportsedge_cfb_model.py").read_bytes()
        sha = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        self.assertEqual(sha, S.BASE_MODEL_BLOB_SHA)

    def test_invalid_flags_rejected(self):
        for bad in (None, "false", "true", "", 0, 1, [], {}):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(S.NeutralSiteError, "neutralSite"):
                    S.run_game_strict(_game(neutralSite=bad), _ctx())

    def test_missing_rejected(self):
        with self.assertRaises(S.NeutralSiteError):
            S.run_game_strict(_game(), _ctx())

    def test_pinned_model_defect_is_characterized(self):
        self.assertEqual(M.run_game(_game(), _ctx())["hfa"], M.HFA_DEFAULT)
        self.assertEqual(M.run_game(_game(neutralSite="false"), _ctx())["hfa"], 0.0)

    def test_true_gives_zero_hfa(self):
        p = S.run_game_strict(_game(neutralSite=True), _ctx())
        self.assertEqual(p["hfa"], 0.0)
        self.assertEqual(p["model_path"], S.STRICT_VERSION)

    def test_false_matches_pinned_model_exactly(self):
        a = S.run_game_strict(_game(neutralSite=False), _ctx())
        b = M.run_game(_game(neutralSite=False), _ctx())
        for k in ("pts_home", "pts_away", "margin", "total", "hfa"):
            self.assertEqual(a[k], b[k])

    def test_card_withholds_bad_game_and_keeps_good(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [_row("Home U"), _row("Away U")]
            games = [_game(id=1, neutralSite=False), _game(id=2, neutralSite="false")]
            paths = {}
            for name, data in (("advanced", rows), ("games", games)):
                p = os.path.join(d, name + ".json")
                with open(p, "w") as f:
                    json.dump(data, f)
                paths[name] = p
            card, projs, withheld = S.run_card_strict(paths, os.path.join(d, "out"))
            self.assertEqual([p["game"]["id"] for p in projs], [1])
            self.assertEqual([w[0] for w in withheld], [2])
            self.assertIn("neutralSite", withheld[0][1])
            self.assertTrue(os.path.exists(os.path.join(d, "out", "cfb_withheld.csv")))


if __name__ == "__main__":
    unittest.main()
