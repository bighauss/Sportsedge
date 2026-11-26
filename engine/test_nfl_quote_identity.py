"""Regression: NFL quote identity is order-independent, normalized, and conflict-safe."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_quote_identity as qi  # noqa: E402


def q(**kw):
    base = dict(home="Chiefs", away="Bills", event_date="2026-11-29", book="DraftKings",
                market="SPREAD", period="full", player="", line="-3.5", side="home",
                price="-110", captured_at="2026-11-26T01:00:00Z")
    base.update(kw)
    return base


def board():
    return [
        q(), q(side="away", line="3.5"), q(market="TOTAL", line="47.5", side="over"),
        q(market="TOTAL", line="47.5", side="under", price="-105"),
        q(market="ANYTIME_TD", player="Travis Kelce", line="", side="yes", price="+120"),
        q(period="1h", line="-1.5", price="-115"),
        q(book="FanDuel", price="-108"),
        q(captured_at="2026-11-26T02:00:00Z", price="-112"),
    ]


class QuoteIdentity(unittest.TestCase):
    def ids(self, rows):
        return [c["quote_id"] for c in qi.dedupe(rows)["accepted"]]

    def test_every_permutation_class_gives_identical_result(self):
        rows = board()
        ref = qi.dedupe(rows)
        rng = random.Random(20261125)
        for _ in range(200):
            shuffled = rows[:]
            rng.shuffle(shuffled)
            self.assertEqual(qi.dedupe(shuffled), ref)
        self.assertEqual(qi.dedupe(list(reversed(rows))), ref)

    def test_quote_id_independent_of_position_and_neighbours(self):
        alone = qi.canonical(q())["quote_id"]
        in_board = [c["quote_id"] for c in qi.dedupe(board())["accepted"]]
        self.assertIn(alone, in_board)

    def test_all_board_ids_are_distinct(self):
        ids = self.ids(board())
        self.assertEqual(len(ids), len(board()))
        self.assertEqual(len(set(ids)), len(ids))

    def test_formatting_variants_are_the_same_quote(self):
        a = qi.canonical(q(line="-3.5", price="-110", book="DraftKings"))
        b = qi.canonical(q(line="-3.50", price="-110.0", book="  draftkings ", home="CHIEFS"))
        self.assertEqual(a["quote_id"], b["quote_id"])
        self.assertEqual(qi.canonical(q(line="3"))["quote_id"], qi.canonical(q(line="+3.0"))["quote_id"])
        self.assertEqual(qi.canonical(q(line="0"))["quote_id"], qi.canonical(q(line="-0.0"))["quote_id"])
        self.assertEqual(qi.canonical(q(line="50"))["line"], "50")

    def test_each_field_changes_the_id(self):
        base = qi.canonical(q())["quote_id"]
        for field, value in ("home", "Jets"), ("away", "Jets"), ("event_date", "2026-12-06"), \
                ("book", "FanDuel"), ("market", "TOTAL"), ("period", "1h"), ("player", "X Y"), \
                ("line", "-4"), ("side", "away"), ("price", "-111"), ("captured_at", "2026-11-26T01:00:01Z"):
            self.assertNotEqual(qi.canonical(q(**{field: value}))["quote_id"], base, field)

    def test_price_change_keeps_selection_key_but_changes_quote_id(self):
        a, b = qi.canonical(q(price="-110")), qi.canonical(q(price="-120"))
        self.assertEqual(a["selection_key"], b["selection_key"])
        self.assertNotEqual(a["quote_id"], b["quote_id"])

    def test_exact_duplicates_collapse_to_one(self):
        out = qi.dedupe([q(), q(), q(book=" draftkings")])
        self.assertEqual(len(out["accepted"]), 1)
        self.assertEqual(out["conflicts"], [])

    def test_conflicting_prices_at_same_capture_are_excluded_in_any_order(self):
        rows = [q(price="-110"), q(price="-120"), q(side="away", line="3.5")]
        ref = qi.dedupe(rows)
        self.assertEqual(len(ref["conflicts"]), 1)
        self.assertEqual(len(ref["conflicts"][0]), 2)
        self.assertEqual(len(ref["accepted"]), 1)
        self.assertEqual(ref["accepted"][0]["side"], "away")
        for perm in ([rows[2], rows[1], rows[0]], [rows[1], rows[2], rows[0]]):
            self.assertEqual(qi.dedupe(perm), ref)

    def test_different_capture_times_are_not_a_conflict(self):
        out = qi.dedupe([q(price="-110"), q(price="-120", captured_at="2026-11-26T03:00:00Z")])
        self.assertEqual(len(out["accepted"]), 2)
        self.assertEqual(out["conflicts"], [])

    def test_missing_required_field_and_bad_values_raise(self):
        for field in qi.REQUIRED:
            row = q()
            row[field] = ""
            with self.assertRaises(ValueError, msg=field):
                qi.canonical(row)
        for bad in (dict(price="abc"), dict(price="-110.5"), dict(price="50"), dict(line="x"),
                    dict(line="nan"), dict(price="inf")):
            with self.assertRaises(ValueError, msg=str(bad)):
                qi.canonical(q(**bad))

    def test_blank_period_and_player_are_not_inferred(self):
        c = qi.canonical(q(period="", player=""))
        self.assertEqual((c["period"], c["player"]), ("", ""))
        self.assertNotEqual(c["quote_id"], qi.canonical(q(period="full"))["quote_id"])


if __name__ == "__main__":
    unittest.main()
