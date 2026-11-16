"""Synthetic contract tests, not evidence of predictive skill."""
import unittest
from tournament_sim import simulate, validate_field

def golfer(pid, sg=0):
    return dict(player_id=pid, source_status="PREGAME_VERIFIED", sg_ott=sg,
                sg_app=0.0, sg_arg=0.0, sg_putt=0.0, round_sd=1.0)

class TournamentTests(unittest.TestCase):
    def test_repeatable(self):
        a=[golfer("a",2),golfer("b",-1),golfer("c")]
        self.assertEqual(simulate(a,n=200,seed=42),simulate(a,n=200,seed=42))
    def test_probabilities_bounded(self):
        r=simulate([golfer("a",2),golfer("b",-2)],n=100,cut_size=1)
        for p in r["players"].values():
            self.assertTrue(all(0 <= v <= 1 for v in p.values()))
            self.assertGreaterEqual(p["top5"],p["win_tie_fraction"])
        self.assertEqual(r["status"],"UNCALIBRATED_PAPER_0U")
    def test_stronger_player_more_likely(self):
        r=simulate([golfer("a",4),golfer("b",-4)],n=300,seed=2,cut_size=2)
        self.assertGreater(r["players"]["a"]["win_tie_fraction"],r["players"]["b"]["win_tie_fraction"])
    def test_duplicate_player_rejected(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_PLAYER"):
            validate_field([golfer("a"),golfer("a")])
    def test_unverified_data_rejected(self):
        x=golfer("a");x["source_status"]="UNKNOWN"
        with self.assertRaisesRegex(ValueError,"SOURCE_NOT_VERIFIED"):
            simulate([x,golfer("b")])
    def test_missing_sg_rejected(self):
        x=golfer("a");del x["sg_app"]
        with self.assertRaisesRegex(ValueError,"MISSING_OR_INVALID_SG_APP"):
            simulate([x,golfer("b")])
    def test_invalid_round_sd_rejected(self):
        x=golfer("a");x["round_sd"]=0
        with self.assertRaisesRegex(ValueError,"INVALID_VARIANCE"):
            simulate([x,golfer("b")])
    def test_invalid_settings_rejected(self):
        a=[golfer("a"),golfer("b")]
        for kwargs in ({"n":0},{"common_sd":-1},{"cut_after":4},{"seed":True}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                simulate(a,**kwargs)

if __name__=="__main__":
    unittest.main()
