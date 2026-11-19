"""Nov 18 reported-row reconciliation + uppercase-team regressions.

The 32-row fixture is transcribed from the owner's paper report. It does not
authenticate provider odds or prove profitability.
"""
import unittest
from cbb_card_grading import (GradeIntegrityError, game_key,
                              match_card_games, summarize_delivered)

R = "Rutgers @ Notre Dame"
H = "Houston @ Florida"
B = "Jackson St. @ Baylor"
ROWS = [
    (B, -120, 'L'), (R, 431, 'W'), (B, -120, 'L'), (B, 515, 'L'),
    (R, 310, 'W'), (B, 2500, 'L'), (B, -120, 'L'), (R, 310, 'W'),
    (B, 310, 'L'), (H, 435, 'W'), (H, 275, 'L'), (B, -120, 'L'),
    (R, -115, 'W'), (R, -115, 'W'), (H, 310, 'W'), (H, 124, 'W'),
    (R, -105, 'W'), (H, -108, 'W'), (B, -125, 'L'), (R, -120, 'L'),
    (R, 410, 'W'), (H, -115, 'W'), (H, -115, 'W'), (R, 135, 'L'),
    (R, -112, 'L'), (R, 136, 'L'), (B, -110, 'L'), (H, -120, 'L'),
    (H, 110, 'L'), (R, -120, 'W'), (H, -115, 'W'), (H, 248, 'L')
]


def fixture():
    return [dict(bet_id=f"entry-{i:02d}", game=g, price_american=str(o),
                 result=result, role="CARD")
            for i, (g, o, result) in enumerate(ROWS, 1)]


class GradeTests(unittest.TestCase):
    def test_uppercase_team_tokens_not_trimmed(self):
        for game in ["VMI @ Longwood", "NJIT @ Fairleigh Dickinson",
                     "UNC Wilmington @ LIU"]:
            self.assertEqual(game_key("CBB " + game), game_key(game))
            self.assertEqual(match_card_games([game], [game])["matched"],
                             [game_key(game)])
        self.assertEqual(game_key("VMI @ Longwood"), "vmi @ longwood")
        self.assertNotEqual(game_key("UNC Wilmington @ LIU"), "wilmington @ liu")

    def test_no_substring_match_and_duplicate_finals(self):
        z = match_card_games(["VMI @ Longwood"], ["Other VMI @ Longwood"])
        self.assertEqual(z["matched"], [])
        self.assertEqual(len(z["pending"]), 1)
        with self.assertRaises(GradeIntegrityError):
            match_card_games(["VMI @ Longwood"],
                             ["VMI @ Longwood", "CBB VMI @ Longwood"])

    def test_nov18_full_row_reconciliation(self):
        z = summarize_delivered(fixture(), expected_rows=32)
        t = z["totals"]
        self.assertEqual((t["wins"], t["losses"], t["pending"]), (15, 17, 0))
        self.assertAlmostEqual(float(t["flat_1u_paper_net"]), 13.35946, places=4)
        self.assertEqual(t["plus_money_wins"], 7)
        self.assertEqual(t["plus_money_win_gross"], "23.30")
        self.assertAlmostEqual(float(t["gross_flat_1u_wins"]), 30.35946, places=4)
        by = z["by_game"]
        self.assertEqual((by[game_key(R)]["wins"], by[game_key(R)]["losses"]), (8, 4))
        self.assertEqual((by[game_key(H)]["wins"], by[game_key(H)]["losses"]), (7, 4))
        self.assertEqual((by[game_key(B)]["wins"], by[game_key(B)]["losses"]), (0, 9))
        self.assertAlmostEqual(float(by[game_key(R)]["flat_1u_paper_net"]),
                               14.134845, places=4)
        self.assertAlmostEqual(float(by[game_key(H)]["flat_1u_paper_net"]),
                               8.224622, places=4)
        self.assertEqual(z["approved_stake_u"], 0)

    def test_pending_not_loss(self):
        f = fixture()[:1]
        f[0]["result"] = "PENDING"
        z = summarize_delivered(f, expected_rows=1)
        self.assertEqual(z["totals"]["pending"], 1)
        self.assertEqual(z["totals"]["flat_1u_paper_net"], "0")

    def test_doubted_rows_cannot_leak(self):
        f = fixture()
        f[0]["role"] = "DOUBTED"
        with self.assertRaisesRegex(GradeIntegrityError, "NON_CARD_ROW"):
            summarize_delivered(f, expected_rows=32)

    def test_duplicates_count_price_fail_closed(self):
        f = fixture()
        f[1]["bet_id"] = f[0]["bet_id"]
        with self.assertRaisesRegex(GradeIntegrityError, "DUPLICATE"):
            summarize_delivered(f, expected_rows=32)
        f = fixture()
        f[0]["price_american"] = -99
        with self.assertRaisesRegex(GradeIntegrityError, "PRICE"):
            summarize_delivered(f)
        with self.assertRaisesRegex(GradeIntegrityError, "ROW_COUNT"):
            summarize_delivered(fixture(), expected_rows=31)

    def test_invalid_game_never_silently_skipped(self):
        f = fixture()[:1]
        f[0]["game"] = "Baylor"
        with self.assertRaisesRegex(GradeIntegrityError, "AWAY_AT_HOME"):
            summarize_delivered(f)


if __name__ == "__main__":
    unittest.main()
