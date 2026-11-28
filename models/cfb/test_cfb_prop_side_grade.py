"""CFB RUN IT grader must respect the prop side (Under picks were graded as Over)."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfb_run_it_grade as G

GAME = {"id": 1, "homeTeam": "Michigan", "awayTeam": "UCLA", "homePoints": 30, "awayPoints": 20,
        "completed": True}
PST = {("1", "77"): {"rushing.YDS": 40.0}}


def row(pick, line=29.5):
    return {"market": "Prop rush_yds", "pick": pick, "line": line, "player_id": "77"}


class PropSide(unittest.TestCase):
    def test_over_pick(self):
        self.assertEqual(G.result(row("Anthony Woods Over 29.5"), GAME, PST), ("W", None))

    def test_under_pick_is_graded_as_under(self):
        self.assertEqual(G.result(row("Anthony Woods Under 29.5"), GAME, PST), ("L", None))
        self.assertEqual(G.result(row("Anthony Woods Under 45.5", 45.5), GAME, PST), ("W", None))

    def test_integer_line_pushes_either_side(self):
        self.assertEqual(G.result(row("Anthony Woods Under 40", 40), GAME, PST), ("P", None))

    def test_pick_without_side_refused(self):
        self.assertEqual(G.result(row("Anthony Woods 29.5"), GAME, PST), (None, "PROP_SIDE_UNKNOWN"))


if __name__ == "__main__":
    unittest.main()
