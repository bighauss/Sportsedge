"""CBB complete-board synthetic audit: mirrored rows, no made-up odds."""
import unittest
from cbb_forward_quality import Blocked,audit_full_cbb_board

H="a"*64

def pair(event="E",delta=0,selected=False,close=False,grade=True):
    base={
        "book":"DK","capture_state":"OFFERED",
        "model_sha256":H,"feature_sha256":H,
        "take_source_sha256":H,"final_source_sha256":H,
        "feature_published_utc":"2026-11-16T16:00:00Z",
        "feature_captured_utc":"2026-11-16T16:30:00Z",
        "forecast_frozen_utc":"2026-11-16T17:00:00Z",
        "take_published_utc":"2026-11-16T17:00:30Z",
        "take_observed_utc":"2026-11-16T17:01:00Z",
        "event_start_utc":"2026-11-16T20:00:00Z",
        "final_published_utc":"2026-11-16T22:00:00Z" if grade else None,
        "final_captured_utc":"2026-11-16T22:05:00Z" if grade else None,
    }
    rows=[]
    for side in ("OVER","UNDER"):
        x=dict(base)
        x["market"]=["CBB",event,"TOTAL","FG",side,"149.5","","","","INCLUDES_OT"]
        x["model_p"]=.55+delta if side=="OVER" else .45-delta
        x["outcome"]=(1 if side=="OVER" else 0) if grade else None
        x["selected"]=selected if side=="OVER" else False
        x["take_american"]=-110;x["take_opposite_american"]=-110
        if close:
            x.update(close_american=-115 if side=="OVER" else -105,
                     close_opposite_american=-105 if side=="OVER" else -115,
                     close_published_utc="2026-11-16T19:39:00Z",
                     close_observed_utc="2026-11-16T19:40:00Z",
                     close_source_sha256=H)
        rows.append(x)
    return rows

class TestForwardQuality(unittest.TestCase):
    def test_market_brier_once_per_pair_and_census_preserved(self):
        rows=pair(selected=True,close=True)+[{"capture_state":"NOT_OFFERED"}]
        out=audit_full_cbb_board(rows,expected_attempted_rows=3)
        self.assertEqual(out["input_rows"],out["output_rows"])
        self.assertEqual(out["paired_graded_markets"],1)
        self.assertEqual(out["paired_unique_market_rows"],1)
        self.assertEqual(out["matched_close_pairs"],1)
        self.assertEqual(out["counted_forward_rows"],0)
        self.assertEqual(out["row_states"]["NOT_OFFERED"],1)
        self.assertAlmostEqual(out["model_brier"],.45**2)
        self.assertAlmostEqual(out["no_vig_market_brier"],.25)

    def test_extreme_disagreement_not_removed_from_scoring(self):
        x=audit_full_cbb_board(pair(delta=.19),expected_attempted_rows=2)
        self.assertEqual(len(x["extreme_model_doubted"]),1)
        self.assertEqual(x["paired_graded_markets"],1)

    def test_missing_mirror_and_duplicate_all_copies_block(self):
        for rows in (pair()[:1],pair()+pair()):
            out=audit_full_cbb_board(rows,expected_attempted_rows=len(rows))
            self.assertEqual(out["paired_graded_markets"],0)
            self.assertEqual(out["row_states"]["BLOCK"],len(rows))

    def test_conflicting_prices_and_forecast_shas_block(self):
        rows=pair();rows[1]["take_american"]=-120
        self.assertEqual(audit_full_cbb_board(rows,expected_attempted_rows=2)["paired_graded_markets"],0)
        rows=pair();rows[1]["model_sha256"]="b"*64
        self.assertEqual(audit_full_cbb_board(rows,expected_attempted_rows=2)["paired_graded_markets"],0)

    def test_lookahead_future_feature_and_late_close_block(self):
        rows=pair(close=True);rows[0]["feature_published_utc"]="2026-11-16T18:00:00Z"
        self.assertEqual(audit_full_cbb_board(rows,expected_attempted_rows=2)["paired_graded_markets"],0)
        rows=pair(close=True);rows[0]["close_observed_utc"]="2026-11-16T20:01:00Z"
        self.assertEqual(audit_full_cbb_board(rows,expected_attempted_rows=2)["paired_graded_markets"],0)

    def test_reconstructed_or_unverified_final_not_counted(self):
        rows=pair();rows[0]["final_source_sha256"]=""
        self.assertEqual(audit_full_cbb_board(rows,expected_attempted_rows=2)["paired_graded_markets"],0)

    def test_double_selected_mirrors_not_counted_as_two_bets(self):
        rows=pair(selected=True);rows[1]["selected"]=True
        out=audit_full_cbb_board(rows,expected_attempted_rows=2)
        self.assertEqual(out["selected_scored_count"],0)
        self.assertEqual(out["paired_graded_markets"],1)
        self.assertIn("BOTH_MIRRORED_SIDES_SELECTED_NO_ROI_COUNT",out["rows"][0]["selection_warning"])

    def test_selected_close_tracks_presented_side_not_best_side(self):
        rows=pair(close=True)
        rows[1]["selected"]=True  # UNDER, although model prefers OVER
        out=audit_full_cbb_board(rows,expected_attempted_rows=2)
        self.assertLess(out["selected_close_no_vig_shift_pp_mean_research"],0)
        self.assertGreater(out["best_side_close_no_vig_shift_pp_mean_research"],0)
        self.assertEqual(out["selected_close_coverage"],1)
        self.assertAlmostEqual(out["selected_model_brier"],.45**2)

    def test_missing_and_blocked_closes_stay_in_selected_denominator(self):
        rows=pair("A",selected=True,close=True)+pair("B",selected=True)
        bad=pair("C",selected=True);bad[0]["feature_sha256"]=""
        rows+=bad
        out=audit_full_cbb_board(rows,expected_attempted_rows=len(rows))
        self.assertEqual(out["selected_attempted_rows"],3)
        self.assertEqual(out["selected_matched_close_rows"],1)
        self.assertAlmostEqual(out["selected_close_coverage"],1/3)
        self.assertEqual(out["selected_scored_count"],2)

    def test_event_weighting_and_direction_strata(self):
        rows=pair("A",selected=True)+pair("A",delta=.2,selected=True)+pair("B",delta=-.2,selected=True)
        for r in rows[2:4]:r["market"][5]="151.5"
        out=audit_full_cbb_board(rows,expected_attempted_rows=6)
        self.assertAlmostEqual(out["selected_event_weighted_model_brier"],((.45**2+.25**2)/2+.65**2)/2)
        self.assertEqual(out["selected_unique_events"],2)
        self.assertEqual(out["selected_direction_diagnostics"][0]["direction"],"OVER")
        self.assertEqual(out["selected_direction_diagnostics"][0]["graded_rows"],3)

    def test_no_selected_data_is_null_not_zero_edge(self):
        out=audit_full_cbb_board(pair(),expected_attempted_rows=2)
        self.assertIsNone(out["selected_close_coverage"])
        self.assertIsNone(out["selected_model_brier"])
        self.assertIsNone(out["selected_close_no_vig_shift_pp_mean_research"])

    def test_ambiguous_selected_pair_cannot_supply_close_evidence(self):
        rows=pair(selected=True,close=True);rows[1]["selected"]=True
        out=audit_full_cbb_board(rows,expected_attempted_rows=2)
        self.assertEqual(out["selected_attempted_rows"],2)
        self.assertEqual(out["selected_matched_close_rows"],0)
        self.assertEqual(out["selected_close_coverage"],0)

    def test_unsettled_selection_can_have_close_but_not_brier(self):
        rows=pair(selected=True,close=True,grade=False)
        out=audit_full_cbb_board(rows,expected_attempted_rows=2)
        self.assertEqual(out["selected_close_coverage"],1)
        self.assertIsNone(out["selected_model_brier"])
        self.assertEqual(out["counted_forward_rows"],0)

    def test_expected_full_board_denominator_must_match(self):
        with self.assertRaisesRegex(Blocked,"CENSUS_MISMATCH"):
            audit_full_cbb_board(pair(),expected_attempted_rows=3)

if __name__=="__main__":
    unittest.main()
