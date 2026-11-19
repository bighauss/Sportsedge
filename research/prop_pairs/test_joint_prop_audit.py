import unittest
from research.prop_pairs.joint_prop_audit import evaluate

class TestJointProps(unittest.TestCase):
    def row(self,game="g1",**kw):
        return dict(event_id=game,a="p1:PTS:20.5:over",b="p2:AST:5.5:over",pa=.5,pb=.5,ya=1,yb=1,**kw)
    def test_independence_brier(self):
        x=evaluate([self.row(),dict(self.row("g2"),ya=0)])
        self.assertEqual(x["games"],2)
        self.assertAlmostEqual(x["independence_brier"],(.75**2+.25**2)/2)
        self.assertIsNone(x["joint_model_brier"])
    def test_duplicate_game(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_EVENT"):evaluate([self.row(),self.row()])
    def test_missing_outcome(self):
        with self.assertRaisesRegex(ValueError,"MISSING_REQUIRED"):evaluate([dict(self.row(),yb=None)])
    def test_joint_brier(self):
        self.assertAlmostEqual(evaluate([self.row(joint_p=.3)])["joint_model_brier"],.49)
    def test_partial_joint(self):
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_JOINT_FORECASTS"):
            evaluate([self.row(joint_p=.3),self.row("g2")])
    def test_frechet_violation(self):
        with self.assertRaisesRegex(ValueError,"INCOHERENT_JOINT_PROBABILITY"):
            evaluate([self.row(joint_p=.8)])
    def test_no_data(self):
        self.assertEqual(evaluate([])["status"],"NO_DATA")
        self.assertIs(evaluate([])["certified"],False)
        self.assertEqual(evaluate([])["approved_stake_u"],0)
        self.assertIsNone(evaluate([])["pair"])
    def test_leg_reversal_is_invariant(self):
        rows=[dict(self.row("g1"),pa=.2,pb=.7,ya=1,yb=0),
              dict(self.row("g2"),pa=.8,pb=.3,ya=1,yb=1)]
        def swap(row):
            row=dict(row)
            row["a"],row["b"]=row["b"],row["a"]
            row["pa"],row["pb"]=row["pb"],row["pa"]
            row["ya"],row["yb"]=row["yb"],row["ya"]
            return row
        for with_joint in (False,True):
            case=[dict(row,joint_p=.15 if i==0 else .2) if with_joint else row
                  for i,row in enumerate(rows)]
            expected=evaluate(case)
            self.assertEqual(expected,evaluate([swap(row) for row in case]))
            self.assertEqual(expected,evaluate([swap(case[0]),case[1]]))
    def test_alt_lines_not_mixed(self):
        with self.assertRaisesRegex(ValueError,"MIXED_PROP_PAIRS"):
            evaluate([self.row(),dict(self.row("g2"),a="p1:PTS:21.5:over")])

if __name__=="__main__":unittest.main()
