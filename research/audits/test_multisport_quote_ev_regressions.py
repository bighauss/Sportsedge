"""Regression probes against Claude 2026-11-15 multi-sport EV/quote adapters.

Synthetic-only. These tests prove failure paths, not sports-model calibration.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CFB = load("audited_cfb", "models/cfb/sportsedge_cfb_model.py")
CBB = load("audited_cbb", "models/cbb/sportsedge_cbb_model.py")
NBA = load("audited_nba", "models/nba/sportsedge_nba_model.py")
MLB = load("audited_mlb", "models/mlb/sportsedge_mlb_model.py")


class QuoteEVRegression(unittest.TestCase):
    def test_cfb_missing_spread_price_does_not_fabricate_minus_110(self):
        p = {"home":"Alpha", "away":"Beta","game":{"id":"e1"},
             "margin":3.0,"total":44.0,"pts_home":23.5,"pts_away":20.5}
        out = CFB.price_game(p,{"spread":-3.0})
        self.assertFalse(any(x["market"]=="Spread" for x in out))

    def test_cfb_missing_total_price_does_not_fabricate_minus_110(self):
        p = {"home":"Alpha", "away":"Beta","game":{"id":"e1"},
             "margin":3.0,"total":44.0,"pts_home":23.5,"pts_away":20.5}
        out = CFB.price_game(p,{"overUnder":44.5})
        self.assertFalse(any(x["market"]=="Total" for x in out))

    def test_cfb_two_sided_spread_still_priced(self):
        p = {"home":"Alpha", "away":"Beta","game":{"id":"e1"},
             "margin":3.0,"total":44.0,"pts_home":23.5,"pts_away":20.5}
        out = CFB.price_game(p,{"spread":-3.0,"spreadHomeOdds":-105,"spreadAwayOdds":-115})
        self.assertEqual(len([x for x in out if x["market"]=="Spread"]),2)

    def test_cbb_no_single_side_as_no_vig(self):
        with self.assertRaisesRegex(ValueError,"NO_VIG_REQUIRES_TWO_CAPTURED_PRICES"):
            CBB.price_row(.6,-110,None)

    def test_cbb_opposing_price_is_actual_captured_row(self):
        a={"game_id":"c1","market":"spread","side":"home","line":"-3.5",
           "price_american":"-110","opp_price_american":"-112"}
        b={"game_id":"c1","market":"spread","side":"away","line":"3.5",
           "price_american":"-112","opp_price_american":"-110"}
        self.assertEqual(CBB.captured_opposite(a,[a,b]),"-112")
        b["price_american"] = "-120"
        with self.assertRaisesRegex(ValueError,"DECLARED_OPPOSING_PRICE_MISMATCH"):
            CBB.captured_opposite(a,[a,b])

    def test_cbb_no_matching_other_market(self):
        a={"game_id":"c1","market":"total","side":"over","line":"145.5",
           "price_american":"-110"}
        b={"game_id":"c1","market":"total","side":"under","line":"146.5",
           "price_american":"-110"}
        with self.assertRaisesRegex(ValueError,"MISSING_OR_AMBIGUOUS_OPPOSITE_QUOTE"):
            CBB.captured_opposite(a,[a,b])

    def test_nba_push_probabilities_form_one_distribution(self):
        row = NBA._pick("g","TOTAL","UNDER",220.0,1.91,.45,.10,.50,
                        219.0,"UNDER","synthetic",("g","TOTAL"))
        expected_cond = .30 * (.45/.90) + .70*.50
        expected_win = expected_cond * .90
        expected_ev = expected_win * .91 - (.90-expected_win)
        self.assertAlmostEqual(row["blend_p"],round(expected_win,4),4)
        self.assertAlmostEqual(row["blend_ev"],round(expected_ev,4),4)

    def test_nba_missing_opposite_is_not_blended(self):
        with self.assertRaisesRegex(ValueError,"NO_VIG_OPPOSITE_PRICE_MISSING"):
            NBA._pick("g","TOTAL","OVER",220,1.91,.50,0,None,220,"OVER","",("g",))

    def test_nba_novig_requires_valid_complement(self):
        rows=[{"game_id":"g","market":"TOTAL","selection":"OVER","line":"220.5","price":"-110"},
              {"game_id":"g","market":"TOTAL","selection":"OVER","line":"220.5","price":"-110"}]
        out=NBA.novig(rows)
        self.assertTrue(all(r["nv_p"] is None for r in out))

    def test_mlb_push_aware_ev(self):
        result=MLB.ev_row(.6,100,.5,push=.2)
        self.assertAlmostEqual(result["ev_raw"],.16)
        self.assertAlmostEqual(result["ev_blend"],.048)
        self.assertAlmostEqual(result["p_push"],.2)

    def test_mlb_pair_rejects_same_selection(self):
        rows=[{"game_id":"g","market":"ML","selection":"home","line":"","price":"-110"},
              {"game_id":"g","market":"ML","selection":"home","line":"","price":"-110"}]
        self.assertEqual(MLB._pair_game_odds(rows,"g"),{})

    def test_mlb_pair_rejects_bad_spread_sign(self):
        rows=[{"game_id":"g","market":"RL","selection":"home","line":"-1.5","price":"-110"},
              {"game_id":"g","market":"RL","selection":"away","line":"-1.5","price":"-110"}]
        self.assertEqual(MLB._pair_game_odds(rows,"g"),{})

    def test_mlb_valid_total_pair(self):
        rows=[{"game_id":"g","market":"TOTAL","selection":"over","line":"8.5","price":"-110"},
              {"game_id":"g","market":"TOTAL","selection":"under","line":"8.5","price":"-110"}]
        self.assertEqual(len(MLB._pair_game_odds(rows,"g")),1)


if __name__=="__main__":
    unittest.main()
