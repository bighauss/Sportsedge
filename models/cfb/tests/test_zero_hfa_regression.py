"""Regression for explicit zero venue HFA; synthetic only, no real-game validation."""
import ast
import pathlib
import unittest

MODEL = pathlib.Path(__file__).resolve().parents[1] / "sportsedge_cfb_model.py"


def venue_hfa_expression():
    tree = ast.parse(MODEL.read_text(encoding="utf-8"))
    run_game = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_game")
    matches = [
        n.value for n in ast.walk(run_game)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "hfa" for t in n.targets)
        and isinstance(n.value, ast.IfExp)
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one venue HFA assignment, found {len(matches)}")
    return compile(ast.Expression(matches[0]), str(MODEL), "eval")


class VenueHfaRegression(unittest.TestCase):
    def test_explicit_zero_preserved(self):
        expr = venue_hfa_expression()
        self.assertEqual(eval(expr, {"neutral": False, "ven": {"hfa": 0}, "HFA_DEFAULT": 2.5}), 0.0)

    def test_missing_and_null_use_default(self):
        expr = venue_hfa_expression()
        for venue in ({}, {"hfa": None}):
            with self.subTest(venue=venue):
                self.assertEqual(eval(expr, {"neutral": False, "ven": venue, "HFA_DEFAULT": 2.5}), 2.5)

    def test_positive_value_preserved(self):
        expr = venue_hfa_expression()
        self.assertEqual(eval(expr, {"neutral": False, "ven": {"hfa": 1.25}, "HFA_DEFAULT": 2.5}), 1.25)

    def test_neutral_override(self):
        expr = venue_hfa_expression()
        for venue in ({}, {"hfa": None}, {"hfa": 0}, {"hfa": 3.5}):
            with self.subTest(venue=venue):
                self.assertEqual(eval(expr, {"neutral": True, "ven": venue, "HFA_DEFAULT": 2.5}), 0.0)


if __name__ == "__main__":
    unittest.main()
