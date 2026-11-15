import unittest
from audit_1h import report,exact_binomial_vs_half

class AuditHarnessTests(unittest.TestCase):
    # Synthetic fixture proves only code shape, NOT betting validity.
    def row(self,gid='A',model=24.5,book=25.5,flag='Under',margin=2.0,spread=-3.5):
        return {'game_id':gid,'game_date':'2025-10-01','sport':'CFB','away':'A','home':'Boston College',
                'captured_ct':'2025-10-01T10:00:00-05:00','kickoff_ct':'2025-10-01T12:00:00-05:00',
                'model_1h_total':str(model),'book_1h_total':str(book),'model_1h_margin_home':str(margin),
                'book_1h_home_spread':str(spread),'flagged_1h_total':flag}
    def score(self,gid='A',h=14,a=10):
        return {'game_id':gid,'game_date':'2025-10-01','home_1h_points':str(h),'away_1h_points':str(a)}
    def test_total_calibration_and_joint(self):
        r=report([self.row()], [self.score()]);self.assertEqual(r['total_calibration']['CFB']['n'],1)
        self.assertEqual(r['total_calibration']['CFB']['model_minus_actual_mean'],0.5)
        self.assertEqual(r['total_direction']['CFB']['under_among_flagged']['yes'],1)
        self.assertEqual(r['underdog_cover_and_under_joint']['CFB']['under_count'],1)
    def test_drop_late(self):
        x=self.row();x['captured_ct']='2025-10-01T12:10:00-05:00'
        r=report([x],[self.score()]);self.assertEqual(r['sources']['unique_pregame_games'],0)
    def test_42_of_77(self):
        self.assertAlmostEqual(exact_binomial_vs_half(42,77),0.494382,places=5)

if __name__=='__main__':unittest.main()
