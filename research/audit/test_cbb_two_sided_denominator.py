"""Synthetic CBB paired-outcome denominator tests; never real betting."""
import copy
import unittest

from research.audit.cbb_two_sided_denominator import reconcile


def board(market="ML", home="HOME", away="AWAY", a="-110", b="100"):
    return {"sport":"CBB", "home":home, "away":away,
            "home_proj":"73.0", "away_proj":"70.0", "market":market,
            "line":"" if market in ("ML","1H_ML") else "2.5",
            "price_a":a, "price_b":b}


def pick(quoted, index):
    return {"sport":"CBB", "game":quoted["away"]+" @ "+quoted["home"],
            "mode":"PROJECTION", "pick":"TEST_SYNTHETIC",
            "price":quoted["price_a"] if index==0 else quoted["price_b"],
            "model_p":"0.55", "fair_odds":"-122", "market_p":"0.5",
            "edge":"0.05", "ev":"0.05", "score":"73-70",
            "stars":"1", "player":"", "bet_type":f'{quoted["market"]}|{index}|'}


class ReconciliationTests(unittest.TestCase):
    def test_full_pair_retained(self):
        b=board()
        r=reconcile([b],[pick(b,0),pick(b,1)])
        self.assertTrue(r["complete_denominator"])
        self.assertEqual(r["expected_outcomes"],2)
        self.assertEqual(r["matched_outcomes"],2)
        self.assertEqual(r["approved_stake_u"],0)

    def test_one_missing_ml_side_is_flagged_not_inferred(self):
        b=board(a="-148",b="124")
        r=reconcile([b],[pick(b,0)])
        self.assertFalse(r["complete_denominator"])
        self.assertEqual(r["missing_outcomes"],1)
        self.assertEqual(r["missing_details_PRIVATE"][0]["side_index"],1)
        self.assertEqual(r["missing_details_PRIVATE"][0]["status"],
                         "BLOCKED_NO_RECORDED_PROJECTION")

    def test_multiple_markets_and_periods(self):
        a=board()
        b=board("1H_TOTAL")
        c=board("TOTAL")
        bs=[a,b,c]
        picks=[pick(m,i) for m in bs for i in (0,1)]
        r=reconcile(bs,picks)
        self.assertEqual(r["expected_outcomes"],6)
        self.assertEqual(r["matched_outcomes"],6)
        self.assertEqual(r["market_counts"],{"1H_TOTAL":1,"ML":1,"TOTAL":1})

    def test_missing_three_counterparts_reproduces_409_of_412_shape(self):
        bs=[board("ML",home=f"H{i}",away=f"A{i}")
            for i in range(206)]
        ps=[pick(b,0) for b in bs]+[pick(b,1) for b in bs[:203]]
        r=reconcile(bs,ps)
        self.assertEqual(r["board_markets"],206)
        self.assertEqual(r["supplied_predictions"],409)
        self.assertEqual(r["expected_outcomes"],412)
        self.assertEqual(r["missing_outcomes"],3)

    def test_duplicate_prediction_traced(self):
        b=board()
        r=reconcile([b],[pick(b,0),pick(b,0),pick(b,1)])
        self.assertEqual(r["duplicated_prediction_rows"],1)
        self.assertFalse(r["complete_denominator"])

    def test_orphan_prediction_traced(self):
        b=board()
        orphan=pick(board(home="OTHER"),0)
        r=reconcile([b],[pick(b,0),pick(b,1),orphan])
        self.assertEqual(r["orphan_prediction_rows"],1)
        self.assertEqual(r["matched_outcomes"],2)
        self.assertFalse(r["complete_denominator"])

    def test_price_change_refused(self):
        b=board()
        wrong=pick(b,1)
        wrong["price"]="+105"
        r=reconcile([b],[pick(b,0),wrong])
        self.assertEqual(r["price_mismatch_rows"],1)
        self.assertFalse(r["complete_denominator"])

    def test_duplicate_market_refused(self):
        b=board()
        with self.assertRaisesRegex(ValueError,"DUPLICATE_BOARD_MARKET"):
            reconcile([b,copy.deepcopy(b)],[pick(b,0),pick(b,1)])

    def test_ml_with_line_refused(self):
        b=board(); b["line"]="3.5"
        with self.assertRaisesRegex(ValueError,"ML_LINE_MUST_BE_EMPTY"):
            reconcile([b],[pick(b,0)])

    def test_future_or_fabricated_probability_rejected(self):
        b=board(); p=pick(b,0)
        for invalid in ("1.5","NaN","", "abc"):
            with self.subTest(invalid=invalid):
                p["model_p"]=invalid
                with self.assertRaisesRegex(ValueError,"INVALID_PROBABILITY"):
                    reconcile([b],[p])
        
    def test_unclassified_market_refused(self):
        b=board(market="PLAYER_PROP")
        with self.assertRaisesRegex(ValueError,"BOARD_SPORT_OR_MARKET_INVALID"):
            reconcile([b],[])


if __name__=="__main__":
    unittest.main()
