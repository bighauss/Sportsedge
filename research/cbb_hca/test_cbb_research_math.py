import unittest
from research.cbb_hca.cbb_distribution_audit import probabilities,t_cdf,reliability
from research.cbb_hca.paired_score_audit import bootstrap,score_pairs
from research.cbb_hca.cbb_score_factorial import VARIANTS

class ResearchMath(unittest.TestCase):
    def test_common_zero_location(self):
        p=probabilities([8.,9.,10.,11.,12.],0.)
        for f in ("normal","student_t","empirical"):self.assertAlmostEqual(p[f],.5)
    def test_shift_invariance(self):
        a=probabilities([-2.,-1.,0.,1.,2.],1.);b=probabilities([8.,9.,10.,11.,12.],1.)
        for f in ("normal","student_t","empirical"):self.assertAlmostEqual(a[f],b[f])
    def test_explicit_prior_mean(self):
        p=probabilities([8.,9.,10.,11.,12.],0.,use_mean_location=True)
        self.assertEqual(p["location"],10.)
        self.assertTrue(all(p[f]>.5 for f in ("normal","student_t","empirical")))
    def test_degenerate_hold(self):
        with self.assertRaisesRegex(ValueError,"DEGENERATE"):probabilities([1.]*6,2.)
    def test_t_symmetry(self):self.assertAlmostEqual(t_cdf(2.,5.)+t_cdf(-2.,5.),1.)
    def test_t_small_nonzero(self):self.assertAlmostEqual(t_cdf(1e-12,5.),.5)
    def test_bootstrap_reproducible(self):self.assertEqual(bootstrap({"a":1.,"b":2.}),bootstrap({"a":1.,"b":2.}))
    def test_single_event_no_interval(self):self.assertIsNone(bootstrap({"a":1.})["ci95"])
    def test_calibration_bounds(self):self.assertEqual(sum(x["n"] for x in reliability([0.,1.],[0,1])),2)
    def test_calibration_mismatch_rejected(self):
        with self.assertRaises(ValueError):reliability([.5],[])
    def row(self):
        return dict(event_id="synthetic",actual=dict(home_points=80.,away_points=70.,possessions=70.),
                    forecasts={v:dict(home_points=80.+x,away_points=70.,possessions=70.) for v,x in zip(VARIANTS,(4.,3.,2.,0.))})
    def test_paired_interaction(self):
        r=score_pairs([self.row()]);self.assertEqual(r["loss_interaction"]["margin"]["mean"],-1.)
    def test_duplicate_pairs_rejected(self):
        with self.assertRaisesRegex(ValueError,"UNIQUE"):score_pairs([self.row(),self.row()])

if __name__=="__main__":unittest.main()
