"""Provenance classification regression (pure python; no v5 / numpy needed)."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nfl_provenance as P  # noqa: E402

H = "sport,home,away,home_proj,away_proj,proj_provenance,player,team,proj,market,line,price_a,price_b,sgp,side\n"
V = "PIT_VERIFIED"


def game(hp="27", ap="20", tag=V):
    return ["NFL,A,B,%s,%s,%s,,,,TOTAL,44.5,-110,-110,," % (hp, ap, tag), "NFL,A,B,,,,,,,SPREAD,-3.5,-110,-110,,"]


def prop(player="P1", market="REC_YDS", proj="70", tag=V, line="59.5", sgp="", side=""):
    return "NFL,A,B,,,%s,%s,A,%s,%s,%s,-110,-110,%s,%s" % (tag, player, proj, market, line, sgp, side)


def td(player="P1", share="0.3", tag=V):
    return "NFL,A,B,,,%s,%s,A,%s,ATD,,150,-190,," % (tag, player, share)


SGP = "NFL,A,B,,,,,,,SGP,,600,,S1,"


def run(*rows):
    p = os.path.join(tempfile.mkdtemp(), "b.csv")
    with open(p, "w", newline="") as f:
        f.write(H + "\n".join(rows) + "\n")
    return P.classify(p)


def cls(res, market, player="", sgp=""):
    return res[("B @ A", market, player, sgp)][0]


class Provenance(unittest.TestCase):
    def test_independent_game_vs_anchored_game(self):
        self.assertEqual(cls(run(*game()), "TOTAL"), P.VERIFIED)
        self.assertEqual(cls(run(*game("", "", "")), "TOTAL"), P.ANCHOR)

    def test_supplied_but_unverified_projection_is_held(self):
        for tag in ("", "UNVERIFIED"):
            self.assertEqual(cls(run(*game(tag=tag)), "TOTAL"), P.UNVERIFIED)
        self.assertFalse(P.eligible(P.UNVERIFIED))

    def test_unknown_tag_is_ambiguous(self):
        self.assertEqual(cls(run(*game(tag="TRUST_ME")), "TOTAL"), P.AMBIGUOUS)

    def test_partial_team_projection_falls_back_to_anchor(self):
        self.assertEqual(cls(run(*game("27", "", V)), "TOTAL"), P.ANCHOR)

    def test_conflicting_team_projections_are_ambiguous(self):
        rows = game() + ["NFL,A,B,30,10,%s,,,,ML,,-150,130,," % V]
        self.assertEqual(cls(run(*rows), "TOTAL"), P.AMBIGUOUS)

    def test_independent_game_with_anchored_player_prop(self):
        self.assertEqual(cls(run(*game(), prop(proj="", tag="")), "REC_YDS", "P1"), P.ANCHOR)

    def test_anchored_game_with_independent_stat_prop_depends_only_on_its_mean(self):
        r = run(*game("", "", ""), prop())
        self.assertEqual(cls(r, "REC_YDS", "P1"), P.VERIFIED)
        self.assertEqual(cls(r, "TOTAL"), P.ANCHOR)

    def test_td_prop_depends_on_game_simulation(self):
        self.assertEqual(cls(run(*game("", "", ""), td()), "ATD", "P1"), P.MIXED)
        self.assertEqual(cls(run(*game(), td()), "ATD", "P1"), P.VERIFIED)
        self.assertEqual(cls(run(*game(tag="UNVERIFIED"), td()), "ATD", "P1"), P.UNVERIFIED)

    def test_td_prop_without_share_is_ambiguous(self):
        self.assertEqual(cls(run(*game(), td(share="", tag="")), "ATD", "P1"), P.AMBIGUOUS)

    def test_sgp_all_verified_legs_is_verified(self):
        self.assertEqual(cls(run(*game(), prop(sgp="S1", side="A"), SGP), "SGP", "", "S1"), P.VERIFIED)

    def test_sgp_with_anchored_player_leg_is_held(self):
        r = run(*game(), prop(proj="", tag="", sgp="S1", side="A"), SGP)
        self.assertEqual(cls(r, "SGP", "", "S1"), P.MIXED)
        r2 = run(*game("", "", ""), prop(proj="", tag="", sgp="S1", side="A"), SGP)
        self.assertEqual(cls(r2, "SGP", "", "S1"), P.ANCHOR)
        self.assertFalse(P.eligible(cls(r, "SGP", "", "S1")))

    def test_sgp_over_anchored_game_with_verified_leg_is_mixed(self):
        r = run(*game("", "", ""), prop(sgp="S1", side="A"), SGP)
        self.assertEqual(cls(r, "SGP", "", "S1"), P.MIXED)

    def test_sgp_independent_game_anchored_leg_verified_leg_is_mixed(self):
        r = run(*game(), prop(sgp="S1", side="A"), prop("P2", proj="", tag="", sgp="S1", side="A"), SGP)
        self.assertEqual(cls(r, "SGP", "", "S1"), P.MIXED)

    def test_sgp_without_legs_is_ambiguous(self):
        self.assertEqual(cls(run(*game(), SGP.replace("S1", "S9")), "SGP", "", "S9"), P.AMBIGUOUS)

    def test_duplicate_quote_with_different_provenance_is_ambiguous(self):
        rows = game() + [prop(), prop(tag="UNVERIFIED")]
        self.assertEqual(cls(run(*rows), "REC_YDS", "P1"), P.AMBIGUOUS)

    def test_row_order_does_not_change_classification(self):
        rows = game() + [prop(), td()]
        self.assertEqual(run(*rows), run(*reversed(rows)))


if __name__ == "__main__":
    unittest.main()
