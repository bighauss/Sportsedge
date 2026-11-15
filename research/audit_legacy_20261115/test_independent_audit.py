import unittest,sys,json,tempfile,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from independent_audit import grade,ev,implied,parse_card,main
from prospective_controls import check
BASE=Path(__file__).resolve().parent
class AuditTests(unittest.TestCase):
    def test_american_odds(self):
        self.assertAlmostEqual(implied(1300),1/14)
        self.assertAlmostEqual(implied(-115),115/215)
        self.assertAlmostEqual(ev(.2268,1300),2.1752)
    def test_correct_team_total(self):
        f={'away':'MVSU','home':'Washington','away_final':64,'home_final':77,'away_1h':33,'home_1h':43}
        r={'bet_type':'HOME_TT|1|','pick':'Washington Under 82.5'}
        self.assertEqual(grade(r,f),'W')
        self.assertEqual(grade({'bet_type':'TOTAL|1|','pick':'Under 82.5'},f),'L')
    def test_half_and_spread_grading(self):
        f={'away':'Cal Poly','home':'Grand Canyon','away_final':71,'home_final':99,'away_1h':29,'home_1h':37}
        self.assertEqual(grade({'bet_type':'1H_TOTAL|1|','pick':'1H Under 86.5'},f),'W')
        self.assertEqual(grade({'bet_type':'SPREAD|1|','pick':'Cal Poly +18.5'},f),'L')
        self.assertEqual(grade({'bet_type':'HOME_TT|1|','pick':'Grand Canyon Under 100.5'},f),'W')
    def test_all_cards_exact(self):
        keys,_,_=parse_card((BASE/'source/nov11_card_original.txt').read_text())
        self.assertEqual(len(keys['CARD']),65);self.assertEqual(len(keys['DOUBTED']),10)
    def test_point_in_time_failclosed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'oldboard.csv';p.write_text('game,pick,price,model_p\nA @ B,A ML,+130,0.5\n')
            z=check(p)
            self.assertEqual(z['status'],'FAIL_CLOSED');self.assertEqual(z['admitted'],0)
    def test_scoring_overround(self):
        from independent_audit import read_csv,discrepancies
        rows=read_csv(BASE/'source/nov11_board_96.csv');m=discrepancies(rows)
        self.assertEqual(len(m),96);self.assertTrue(all(0<=r['book_overround_pct']<=15 for r in m))
    def test_reproduce_live_research(self):
        with tempfile.TemporaryDirectory() as d:
            r=main(BASE/'source',Path(d))
            self.assertEqual(r['results']['original_65_card']['wins'],31)
            self.assertEqual(r['results']['original_65_card']['losses'],34)
            self.assertEqual(r['source_integrity']['calculation_or_grading_issues'],[])
            self.assertAlmostEqual(r['results']['original_65_card']['net_units'],-1.578965,places=5)
            self.assertEqual(r['results']['correlation_risk']['games'],10)
if __name__=='__main__':unittest.main()

