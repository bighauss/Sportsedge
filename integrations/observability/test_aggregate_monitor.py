"""Synthetic baseline/current quality alerts; no genuine model-performance claim."""
import copy
import unittest
import aggregate_monitor as mon


def report(n=100, blocked=1, matched=70, brier=.18):
    valid=n-blocked
    return {"schema":"SPORTSEDGE_OBSERVABILITY_V1",
            "official":False,"stake_u":0,"source_authenticated":False,
            "input_rows":n,"blocked_rows":blocked,"clock_consistent_rows":valid,
            "metrics":{"n_decided":min(80,valid),"n_clv_matched":matched,
                       "n_clv_unmatched":valid-matched,
                       "brier_descriptive_not_forward_certified":brier}}


class MonitorTests(unittest.TestCase):
    def test_alert_block_growth(self):
        result=mon.compare_reports(report(), report(blocked=20))
        self.assertEqual(result["status"],"REVIEW_ALERTS")
        self.assertIn("BLOCKED_ROW_RATE_INCREASE",result["alerts"])
        self.assertFalse(result["official"])

    def test_alert_closing_coverage_drop(self):
        before=report(matched=90)
        after=report(matched=30)
        self.assertIn("MATCHED_CLOSE_COVERAGE_DROP",
                      mon.compare_reports(before,after)["alerts"])

    def test_alert_descriptive_brier(self):
        before=report(brier=.18)
        after=report(brier=.30)
        self.assertIn("DESCRIPTIVE_BRIER_WORSENING_UNCONFIRMED",
                      mon.compare_reports(before,after)["alerts"])

    def test_no_alert_is_not_betting_certification(self):
        item=mon.compare_reports(report(),report())
        self.assertEqual(item["status"],"NO_THRESHOLD_ALERT")
        self.assertFalse(item["source_authenticated"])
        self.assertFalse(item["forward_validated"])
        self.assertEqual(item["stake_u"],0)

    def test_low_samples_no_drift_claim(self):
        item=mon.compare_reports(report(n=10,blocked=1,matched=3),
                                 report(n=10,blocked=8,matched=1))
        self.assertEqual(item["status"],"INSUFFICIENT_SAMPLE_NO_DRIFT_CLAIM")
        self.assertFalse(item["alerts"])

    def test_bad_schema_and_threshold_rejected(self):
        with self.assertRaises(mon.ExportBlocked):
            mon.compare_reports({},report())
        with self.assertRaisesRegex(mon.ExportBlocked,"MIN_ROWS"):
            mon.compare_reports(report(),report(),min_rows=1)
        with self.assertRaisesRegex(mon.ExportBlocked,"INVALID_THRESHOLD"):
            mon.compare_reports(report(),report(),max_block_increase=True)


if __name__=="__main__":
    unittest.main()
