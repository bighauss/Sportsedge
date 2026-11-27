import unittest
from research.sportsleader.player_baseline import evaluate

class PlayerTests(unittest.TestCase):
    def row(self,day,game,value):
        return dict(date=day,game_id=game,player_id="p",stat="points",value=value)
    def test_same_day(self):
        rows=[self.row("2025-01-01","a",10),self.row("2025-01-02","b",20),self.row("2025-01-02","c",30)]
        result=evaluate(rows,min_games=1)["predictions"]
        self.assertEqual([r["prediction"] for r in result],[10,10])
    def test_duplicate(self):
        r=self.row("2025-01-01","a",10)
        with self.assertRaises(ValueError):
            evaluate([r,r])
    def test_no_history(self):
        self.assertEqual(evaluate([self.row("2025-01-01","a",10)])["predictions"],[])
