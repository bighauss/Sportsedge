import unittest
from research.cbb_hca.half_forward_calibration import Regression as FirstHalfRegression
from research.cbb_hca.reconcile_outcomes import reconcile
from research.cbb_hca.distribution_driver import evaluate, smooth

def forecast(i, margin=2.0):
    return dict(freeze_utc=f"2026-11-{i:02d}T12:00:00Z", built_utc=f"2026-11-{i:02d}T12:00:01Z", parent_card_sha256="a"*64, source_receipts={"ratings":"b"*64,"prior_games":"c"*64}, game=dict(game_id=str(i), season=2027, tipoff_utc=f"2026-11-{i:02d}T18:00:00Z", home_team_id="1", away_team_id="2", neutral=False), forecasts={k:dict(home_points=80+margin, away_points=80, margin=margin, total=160+margin, possessions=70) for k in ("additive_product","additive_arithmetic","multiplicative_product","multiplicative_arithmetic")})

def final(i, hp=84):
    return dict(game_id=str(i), season=2027, home_team_id="1", away_team_id="2", home_points=hp, away_points=80, possessions=71.0, final_observed_utc=f"2026-11-{i:02d}T21:00:00Z", settlement="FG_INCL_OT", source_sha256="d"*64)

class CriticalPath(unittest.TestCase):
    def test_bound_chronology_eligible(self):
        self.assertEqual(len(reconcile([forecast(2)],[final(2)])["eligible"]),1)
    def test_missing_binding_quarantined(self):
        f=forecast(2); del f["source_receipts"]
        self.assertEqual(reconcile([f],[final(2)])["holds"][0]["reason"],"SOURCE_OR_PARENT_BINDING_MISSING")
    def test_receipt_subset_and_nonfinite_possessions(self):
        for missing in ("ratings","prior_games"):
            f=forecast(2);del f["source_receipts"][missing];f["source_receipts"]["extra"]="e"*64
            self.assertEqual(reconcile([f],[final(2)])["holds"][0]["reason"],"SOURCE_OR_PARENT_BINDING_MISSING")
        f=forecast(2);f["source_receipts"]["extra"]="e"*64
        self.assertEqual(len(reconcile([f],[final(2)])["eligible"]),1)
        for p in (float("inf"),float("nan"),True,201):
            y=final(2);y["possessions"]=p
            self.assertEqual(reconcile([forecast(2)],[y])["holds"][0]["reason"],"POSSESSIONS_INVALID")
    def test_incoherent_forecast_quarantined(self):
        for key,val in (("margin",999),("total",float("nan")),("possessions",float("inf")),("home_points",True)):
            f=forecast(2);f["forecasts"]["additive_product"][key]=val
            self.assertEqual(reconcile([f],[final(2)])["holds"][0]["reason"],"INCOHERENT_FORECAST")
    def test_tie_identity_and_clock_quarantined(self):
        self.assertEqual(reconcile([forecast(2)],[final(2,80)])["holds"][0]["reason"],"FINAL_SCORE_INVALID_OR_TIED")
        y=final(2); y["away_team_id"]="9"
        self.assertEqual(reconcile([forecast(2)],[y])["holds"][0]["reason"],"IDENTITY_MISMATCH")
        y=final(2); y["final_observed_utc"]="2026-11-02T17:00:00Z"
        self.assertEqual(reconcile([forecast(2)],[y])["holds"][0]["reason"],"INVALID_CHRONOLOGY")
    def test_duplicates_all_quarantined(self):
        self.assertEqual(len(reconcile([forecast(2),forecast(2)],[final(2)])["holds"]),2)
    def test_smoothing_is_common_and_finite(self):
        self.assertGreater(smooth(0,5),0); self.assertLess(smooth(1,5),1); self.assertAlmostEqual(smooth(.5,5),.5)
    def test_distribution_prior_only_and_degenerate_hold(self):
        rows=[dict(event_id=str(i), freeze_utc=f"2026-11-{i:02d}T12:00:00Z", final_observed_utc=f"2026-11-{i:02d}T21:00:00Z", settlement="FG_INCL_OT", projected_margin=1.0, actual_margin=1+i%3) for i in range(3,16)]
        result=evaluate(rows,min_train=5)
        self.assertGreater(result["evaluated"],0)
        self.assertEqual(result["approved_stake_u"],0)
        constant=[dict(event_id=str(i), freeze_utc=f"2026-12-{i:02d}T12:00:00Z", final_observed_utc=f"2026-12-{i:02d}T21:00:00Z", settlement="FG_INCL_OT", projected_margin=1, actual_margin=2) for i in range(3,12)]
        self.assertIn("DEGENERATE_RESIDUAL_VARIANCE",[h["reason"] for h in evaluate(constant,min_train=5)["holds"]])

if __name__=="__main__": unittest.main()
