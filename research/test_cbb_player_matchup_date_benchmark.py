import unittest
from datetime import date, timedelta
from cbb_player_matchup_date_benchmark import evaluate


def fixture(n=13):
    records, pace = [], []
    for i in range(n):
        day = date(2025,1,1)+timedelta(days=2*i)
        gid = str(i+1)
        for tid,pid,points in (("h","p",70),("a","q",65)):
            records.append({"game_id":gid,"day":day,"team_id":tid,"player_id":pid,
                            "stats":{"POINTS":points,"REBOUNDS":30,"ASSISTS":12,"THREES":5}})
        pace.append({"event_id":gid,"day":day.isoformat(),"home":"h","away":"a",
                     "home_points":"70","away_points":"65","possessions":"70"})
    return records,pace


class DateBenchmark(unittest.TestCase):
    def test_common_rows_and_baselines(self):
        r,p=fixture()
        result=evaluate(r,p)
        self.assertEqual(result["paired_appearances"],10)
        self.assertEqual(result["paired_games"],5)
        self.assertEqual(result["metrics"]["POINTS"]["last5"]["mae"],0)
        self.assertEqual(result["metrics"]["PRA"]["last8"]["mae"],0)
        self.assertGreater(result["metrics"]["POINTS"]["matchup10"]["mae"],0)
        self.assertEqual(len(result["metrics"]),8)
        self.assertEqual(result["window_counts"], {8:2,9:2,10:6})
        self.assertEqual(set(result["metrics"]["POINTS"]),
                         {"last5","last8","plain10","pace_only10","defense_only10","matchup10"})
        self.assertEqual(result["metrics"]["POINTS"]["plain10"]["mae"],0)
        self.assertEqual(result["metrics"]["POINTS"]["pace_only10"]["mae"],0)
        self.assertAlmostEqual(result["paired_ablation_deltas"]["POINTS"]["defense_only10"]["delta_mae_vs_plain10"],
                               result["metrics"]["POINTS"]["matchup10"]["mae"])

    def test_no_target_or_same_day_training(self):
        r,p=fixture(9)
        p[-1]["day"]=p[-2]["day"]
        for row in r[-2:]:row["day"]=r[-3]["day"]
        self.assertEqual(evaluate(r,p)["paired_appearances"],0)

    def test_probability_diagnostics_require_twenty_prior_residuals(self):
        r,p=fixture(28)
        self.assertEqual(evaluate(r,p)["probability_diagnostics"],{})
        r,p=fixture(29)
        report=evaluate(r,p)
        self.assertEqual(len(report["probability_diagnostics"]),8)
        for family, results in report["probability_diagnostics"].items():
            for name in ("empirical_recent","matchup_residual"):
                self.assertEqual(results[name]["n"],2)
                self.assertGreaterEqual(results[name]["brier"],0)
                self.assertLessEqual(results[name]["brier"],1)
                self.assertGreaterEqual(results[name]["log_loss"],0)

    def test_reconcile_and_reject_missing_pace(self):
        r,p=fixture()
        p[0]["home_points"]="71"
        report=evaluate(r,p[:-1])
        self.assertEqual(report["rejections"]["PLAYER_POINTS_NOT_RECONCILED"],1)
        self.assertEqual(report["rejections"]["PACE_GAME_MISSING"],1)
        with self.assertRaisesRegex(ValueError,"DUPLICATE_PACE"):
            evaluate(r,p+[p[0]])


if __name__=="__main__":
    unittest.main()
