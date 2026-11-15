"""Synthetic NGS weekly feature integrity tests, no network or player identities."""
from __future__ import annotations

from copy import deepcopy
from itertools import count
import unittest

from sportsedge.markets.ngs_public_research_smoke import (
    NFL_TEAMS, CORE_STATS, audit_ngs_weekly_rows,
)


def make_rows(kind="NFL_NGS_RECEIVE", *, include_week_zero=False,
              include_week_ten=False):
    rows=[]
    for i,team in enumerate(sorted(NFL_TEAMS)):
        metric={
            "NFL_NGS_PASS":{"attempts":"30","completions":"20",
                            "pass_yards":"250","pass_touchdowns":"2"},
            "NFL_NGS_RUSH":{"rush_attempts":"15","rush_yards":"68",
                            "rush_touchdowns":"1"},
            "NFL_NGS_RECEIVE":{"targets":"8","receptions":"5",
                               "yards":"74","rec_touchdowns":"1"},
        }[kind]
        if team=="LAR":
            team="LA"  # actual NGS Rams abbreviation
        row={"season":"2026","season_type":"REG","week":"1",
             "player_gsis_id":f"id{i}","team_abbr":team,**metric}
        rows.append(row)
        if include_week_zero:
            rows.append({**row,"week":"0"})
        if include_week_ten:
            rows.append({**row,"week":"10"})
    return rows


def columns(rows):
    return tuple(rows[0].keys())


class NGSDataGate(unittest.TestCase):
    def test_pass_weekly_team_and_gsis_coverage(self):
        rows=make_rows("NFL_NGS_PASS",include_week_zero=True,
                       include_week_ten=True)
        r=audit_ngs_weekly_rows("NFL_NGS_PASS",columns(rows),rows)
        self.assertEqual(r["accepted_team_count"],32)
        self.assertEqual(r["accepted_regular_season_player_week_rows"],32)
        self.assertEqual(r["excluded_week_zero_aggregate_rows"],32)
        self.assertEqual(r["excluded_post_cutoff_rows"],32)

    def test_rush_weekly_data_acceptance(self):
        rows=make_rows("NFL_NGS_RUSH")
        r=audit_ngs_weekly_rows("NFL_NGS_RUSH",columns(rows),rows)
        self.assertEqual(r["accepted_regular_season_player_week_rows"],32)

    def test_receive_weekly_data_acceptance(self):
        rows=make_rows("NFL_NGS_RECEIVE")
        r=audit_ngs_weekly_rows("NFL_NGS_RECEIVE",columns(rows),rows)
        self.assertTrue(r["requires_fitted_player_variance_before_prop_pricing"])

    def test_missing_gsis_identity_blocks_source(self):
        rows=make_rows()
        rows[0]["player_gsis_id"]=""
        with self.assertRaisesRegex(ValueError,"NGS_PLAYER_GSIS_ID_MISSING"):
            audit_ngs_weekly_rows("NFL_NGS_RECEIVE",columns(rows),rows)

    def test_duplicate_player_week_team_refused(self):
        rows=make_rows()
        rows.append(deepcopy(rows[0]))
        with self.assertRaisesRegex(ValueError,"NGS_DUPLICATED_WEEKLY_PLAYER_TEAM_ROW"):
            audit_ngs_weekly_rows("NFL_NGS_RECEIVE",columns(rows),rows)

    def test_receptions_cannot_exceed_targets(self):
        rows=make_rows()
        rows[0]["receptions"]="10"
        with self.assertRaisesRegex(ValueError,"NGS_RECEIVING_CATCHES_EXCEED_TARGETS"):
            audit_ngs_weekly_rows("NFL_NGS_RECEIVE",columns(rows),rows)

    def test_completions_cannot_exceed_attempts(self):
        rows=make_rows("NFL_NGS_PASS")
        rows[0]["completions"]="40"
        with self.assertRaisesRegex(ValueError,"NGS_PASS_COMPLETIONS_EXCEED_ATTEMPTS"):
            audit_ngs_weekly_rows("NFL_NGS_PASS",columns(rows),rows)

    def test_missing_required_stat_column_refused(self):
        rows=make_rows()
        cols=columns(rows)[:-1]
        with self.assertRaisesRegex(ValueError,"NGS_REQUIRED_SCHEMA_MISSING"):
            audit_ngs_weekly_rows("NFL_NGS_RECEIVE",cols,rows)

    def test_nonfinite_metric_refused(self):
        rows=make_rows()
        rows[0]["targets"]="NaN"
        with self.assertRaisesRegex(ValueError,"NGS_REQUIRED_STAT_MISSING_OR_INVALID"):
            audit_ngs_weekly_rows("NFL_NGS_RECEIVE",columns(rows),rows)

    def test_most_teams_missing_is_not_complete_coverage(self):
        rows=make_rows()[:10]
        with self.assertRaisesRegex(ValueError,"NGS_32_TEAM_COVERAGE_INCOMPLETE"):
            audit_ngs_weekly_rows("NFL_NGS_RECEIVE",columns(rows),rows)

    def test_week_zero_only_fails_as_no_weekly_data(self):
        rows=make_rows()
        for r in rows:r["week"]="0"
        with self.assertRaisesRegex(ValueError,"NGS_NO_VALID_WEEKLY_2026_ROWS"):
            audit_ngs_weekly_rows("NFL_NGS_RECEIVE",columns(rows),rows)


if __name__=="__main__":
    unittest.main()
