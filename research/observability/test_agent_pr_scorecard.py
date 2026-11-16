"""Deterministic unit tests; never query GitHub or an external service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from research.observability.agent_pr_scorecard import (
    POLICY_MERGED_UTC, WINDOW, describe, live_prs, markdown,
    scorecard, select_windows, when,
)

CUT=when(POLICY_MERGED_UTC)


def row(n, created, merged=None, *, lines=30, files=2,
        commits=2, completed=3, green=True, failures=0, reruns=0):
    return {
        "number":n,
        "created_at":created.isoformat(),
        "merged_at":(merged or created+timedelta(minutes=4)).isoformat(),
        "additions":lines,
        "deletions":0,
        "changed_files":files,
        "commits":commits,
        "reviews_changes_requested":0,
        "ci":{
            "completed_workflows":completed,
            "all_green":green,
            "failed_workflows":failures,
            "workflow_rerun_attempts":reruns,
        },
    }


def cohort(before=20, after=0):
    result=[]
    for i in range(before):
        d=CUT-timedelta(hours=before+2-i)
        result.append(row(i+1,d))
    for i in range(after):
        d=CUT+timedelta(hours=i+1)
        result.append(row(100+i,d))
    return result


class ScorecardTests(unittest.TestCase):
    def test_policy_cutoff_utc(self):
        self.assertEqual(CUT.isoformat(),"2026-11-16T04:52:14+00:00")
        with self.assertRaisesRegex(ValueError,"NON_UTC"):
            when("2026-11-16T04:52:14")

    def test_prospective_sample_is_incomplete_until_twenty(self):
        report=scorecard(cohort(after=6),as_of=(CUT+timedelta(days=30)).isoformat())
        self.assertEqual(report["state"],"POST_SAMPLE_INCOMPLETE")
        self.assertEqual(report["baseline"]["merged_prs"],20)
        self.assertEqual(report["post"]["merged_prs"],6)
        self.assertFalse(report["causal_effect_established"])
        self.assertEqual(report["official_counted"],0)

    def test_maturity_requires_fourteen_days_after_last_merged_pr(self):
        data=cohort(after=20)
        now=CUT+timedelta(hours=21)
        report=scorecard(data,as_of=now.isoformat())
        self.assertEqual(report["state"],"POST_MATURITY_WINDOW_PENDING")
        result=scorecard(data,as_of=(CUT+timedelta(days=30)).isoformat())
        self.assertEqual(result["state"],"DESCRIPTIVE_WINDOWS_READY_NOT_CAUSAL")
        self.assertFalse(result["causal_effect_established"])

    def test_baseline_incomplete_never_claims_quality(self):
        result=scorecard(cohort(before=8,after=20),
                         as_of=(CUT+timedelta(days=30)).isoformat())
        self.assertEqual(result["state"],"BASELINE_INCOMPLETE")

    def test_created_before_policy_but_merged_after_is_excluded(self):
        records=cohort()
        records.append(row(700,CUT-timedelta(minutes=1),CUT+timedelta(minutes=1)))
        before,after=select_windows(records)
        self.assertNotIn(700,[x["number"] for x in before+after])

    def test_agent_contract_pr_220_excluded(self):
        items=cohort(before=20,after=20)
        items.append(row(220,CUT,CUT+timedelta(minutes=1)))
        before,after=select_windows(items)
        self.assertNotIn(220,[x["number"] for x in before+after])
        self.assertEqual(len(after),20)

    def test_baseline_last_twenty_post_first_twenty_deterministic(self):
        items=cohort(before=40,after=35)
        a,b=select_windows(list(reversed(items)))
        self.assertEqual([p["number"] for p in a],
                         list(reversed(range(21,41))))
        self.assertEqual([p["number"] for p in b],list(range(100,120)))

    def test_no_ci_is_unknown_not_success(self):
        items=cohort(before=20)
        items[0]["ci"]={"completed_workflows":0,"all_green":True,
                        "failed_workflows":0,"workflow_rerun_attempts":0}
        a=describe(items)
        self.assertEqual(a["prs_with_completed_pr_head_workflows"],19)
        self.assertEqual(a["prs_with_only_successful_completed_workflows"],19)
        self.assertEqual(a["all_green_rate_among_ci_observed"],1.0)

    def test_failed_ci_and_reruns_visible_not_as_causal_impact(self):
        items=cohort(before=20)
        items[0]["ci"].update(all_green=False,failed_workflows=2,
                              workflow_rerun_attempts=1)
        a=describe(items)
        self.assertEqual(a["prs_with_only_successful_completed_workflows"],19)
        self.assertEqual(a["failed_workflows_observed"],2)
        self.assertEqual(a["workflow_rerun_attempts_observed"],1)
        self.assertEqual(a["all_green_rate_among_ci_observed"],0.95)

    def test_large_diff_alert_not_quality_score(self):
        items=cohort(before=20)
        items[0].update(additions=850,changed_files=12,commits=12)
        a=describe(items)
        self.assertEqual(a["prs_over_500_changed_lines"],1)
        self.assertEqual(a["prs_over_10_changed_files"],1)
        self.assertEqual(a["median_commits"],2)

    def test_invalid_pr_metadata_fails_not_imputed(self):
        items=cohort(before=20)
        items[0]["changed_files"]=-1
        with self.assertRaisesRegex(ValueError,"INVALID_CHANGED_FILES"):
            describe(items)

    def test_report_explicitly_disclaims_accuracy_and_causality(self):
        report=scorecard(cohort(after=4),as_of=(CUT+timedelta(days=30)).isoformat())
        text=markdown(report)
        self.assertIn("Do not claim improvement yet",text)
        self.assertIn("not proof the agent rules caused",text)
        self.assertIn("CHANGES_REQUESTED",text)
        self.assertTrue(report["metrics_are_github_metadata_not_agent_accuracy"])
        self.assertFalse(report["betting_source_validation"])

    def test_live_client_collects_only_public_pr_metadata(self):
        before=row(17,CUT-timedelta(minutes=20))
        after=row(221,CUT+timedelta(minutes=20))
        replies={
            "/pulls?state=closed&sort=created&direction=desc&per_page=100&page=1":
                [{**before,"head":{"sha":"sha_before"}},
                 {**after,"head":{"sha":"sha_after"}}],
            "/pulls/17":{**before,"head":{"sha":"sha_before"}},
            "/pulls/221":{**after,"head":{"sha":"sha_after"}},
            "/actions/runs?head_sha=sha_before&event=pull_request&per_page=100":
                {"workflow_runs":[{"head_sha":"sha_before","event":"pull_request",
                                    "status":"completed","conclusion":"success","run_attempt":1}]},
            "/actions/runs?head_sha=sha_after&event=pull_request&per_page=100":
                {"workflow_runs":[{"head_sha":"sha_after","event":"pull_request",
                                    "status":"completed","conclusion":"failure","run_attempt":2}]},
            "/pulls/17/reviews?per_page=100":[],
            "/pulls/221/reviews?per_page=100":[{"state":"CHANGES_REQUESTED"}],
        }
        with patch("research.observability.agent_pr_scorecard.github_get",
                   side_effect=lambda path:replies[path]) as fake:
            found=live_prs()
        self.assertEqual(len(found),2)
        self.assertEqual(fake.call_count,7)
        after_pr=next(x for x in found if x["number"]==221)
        self.assertFalse(after_pr["ci"]["all_green"])
        self.assertEqual(after_pr["ci"]["failed_workflows"],1)
        self.assertEqual(after_pr["ci"]["workflow_rerun_attempts"],1)
        self.assertEqual(after_pr["reviews_changes_requested"],1)


if __name__=="__main__":
    unittest.main()
