import unittest
from research_guardrails import Blocked,forbid_unvalidated_nfl_pace,shared_joint_draws,card_gate,assert_can_publish_as_official
class Tests(unittest.TestCase):
    def test_pace_disabled(self):
        with self.assertRaisesRegex(Blocked,"PACE"):forbid_unvalidated_nfl_pace(sport="NFL",pace_adjustment=True)
        self.assertTrue(forbid_unvalidated_nfl_pace(sport="NFL",pace_adjustment=False))
    def test_aligned_combo_keeps_correlation(self):
        x=shared_joint_draws({"pts":[("d1",22),("d2",30)],"reb":[("d1",11),("d2",4)]})
        self.assertEqual([row["sum"] for row in x],[33,34])
    def test_misalignment_fails(self):
        with self.assertRaisesRegex(Blocked,"MISALIGNED"):shared_joint_draws({
            "pts":[("d1",22),("d2",30)],"reb":[("z1",11),("z2",4)]})
    def test_missing_draw_ids_fail(self):
        with self.assertRaises(Blocked):shared_joint_draws({"pts":[22,30],"reb":[11,4]})
    def test_paper_only(self):
        r=card_gate({"sport":"NFL","market":"PRA","pace_adjustment":True,
                     "advertised_hit_rate":.91,"advertised_roi":2.44})
        self.assertEqual(r["stake_u"],0)
        self.assertIn("EXTRAORDINARY_PERFORMANCE_CLAIM_AUDIT",r["reasons"])
        self.assertIn("COMBO_NOT_JOINTLY_SIMULATED",r["reasons"])
        with self.assertRaises(Blocked):assert_can_publish_as_official({})
if __name__=="__main__":unittest.main()
