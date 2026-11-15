"""Adversarial synthetic walk-forward tests. Team/player identities are fake."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import unittest
from sportsedge.markets.nfl_player_walkforward_research import (
    STATS, ResearchForecast, historical_player_walkforward,
    _observations_weekly, parse_source_archive,
)
from sportsedge.markets.ngs_public_research_smoke import NFL_TEAMS
from hashlib import sha256

def make_data():
    weekly=[]
    ngs={k:[] for k in ("NFL_NGS_PASS","NFL_NGS_RUSH","NFL_NGS_RECEIVE")}
    for ix,team in enumerate(sorted(NFL_TEAMS)):
        label="LA" if team=="LAR" else team
        pid="GSIS_"+str(ix)
        for week in range(1,11):
            yy=200+week*3+ix
            ry=60+week
            cy=45+week*2
            weekly.append({
                "season":"2026","week":str(week),"season_type":"REG",
                "player_id":pid,"team":label,"attempts":"25",
                "passing_yards":str(yy),"carries":"12",
                "rushing_yards":str(ry),"targets":"6",
                "receptions":"4","receiving_yards":str(cy),
                "rushing_tds":"0","receiving_tds":"0",
            })
            ngs["NFL_NGS_PASS"].append({
                "season":"2026","week":str(week),"season_type":"REG",
                "team_abbr":label,"player_gsis_id":pid,
                "attempts":"25","completions":"20",
                "pass_yards":str(yy+4),"pass_touchdowns":"2",
            })
            ngs["NFL_NGS_RUSH"].append({
                "season":"2026","week":str(week),"season_type":"REG",
                "team_abbr":label,"player_gsis_id":pid,
                "rush_attempts":"12","rush_yards":str(ry+2),
                "rush_touchdowns":"0",
            })
            ngs["NFL_NGS_RECEIVE"].append({
                "season":"2026","week":str(week),"season_type":"REG",
                "team_abbr":label,"player_gsis_id":pid,
                "targets":"6","receptions":"4",
                "yards":str(cy+2),"rec_touchdowns":"0",
            })
    return tuple(weekly),{k:tuple(v) for k,v in ngs.items()}

def study(weekly=None, ngs=None):
    w,n=make_data()
    return historical_player_walkforward(
        w if weekly is None else weekly,
        n if ngs is None else ngs,
        season=2026,first_test_week=5,through_week=9)


class NFLPlayerHistoricalStudy(unittest.TestCase):
    def test_chronological_holdouts_and_one_event_every_team(self):
        r=study()
        self.assertEqual([x["holdout_week"] for x in r["folds"]],[5,6,7,8,9])
        self.assertEqual(r["totals"]["PASS_YDS"]["baseline"]["n"],32*5)
        self.assertEqual(r["totals"]["PASS_YDS"]["paired_ngs"]["n"],32*5)
        self.assertEqual(r["counts"]["not_observed_in_holdout"],0)
        self.assertEqual((r["official_counted"],r["approved_stake_u"]),(0,0))
        self.assertIsNone(r["card"])
        self.assertFalse(r["historical_publisher_snapshots_at_original_decision"])
        self.assertFalse(r["confirmed_lineups_or_rosters_available"])

    def test_ewma_compared_with_two_naive_forecasts_on_same_rows(self):
        r=study()
        for stat,values in r["totals"].items():
            n=values["baseline"]["n"]
            self.assertEqual(values["naive_last_observed"]["n"],n)
            self.assertEqual(values["naive_trailing_three_equal"]["n"],n)
            self.assertGreaterEqual(values["naive_last_observed"]["mae"],0)
        self.assertIn("LAST_OBSERVED",
                      r["baselines_compared_on_identical_graded_rows"])

    def test_future_week10_and_week11_cannot_change_prior_holdouts(self):
        weekly,ngs=make_data()
        prior=study(weekly,ngs)
        mutated=[]
        for r in weekly:
            v=dict(r)
            if int(v["week"])>=10:
                v["passing_yards"]="999999"
                v["targets"]="999"
            mutated.append(v)
        changed=study(tuple(mutated),ngs)
        self.assertEqual(prior["folds"],changed["folds"])
        self.assertEqual(prior["totals"],changed["totals"])

    def test_week9_result_not_in_week8_fit(self):
        weekly,ngs=make_data()
        before=study(weekly,ngs)
        altered=[]
        for r in weekly:
            v=dict(r)
            if v["week"]=="9":
                v["passing_yards"]="1000"
            altered.append(v)
        after=study(tuple(altered),ngs)
        self.assertEqual(before["folds"][:4],after["folds"][:4])
        self.assertNotEqual(before["folds"][4],after["folds"][4])

    def test_extra_ngs_current_week_cannot_leak_into_baseline(self):
        weekly,ngs=make_data()
        base=study(weekly,ngs)
        copied={k:list(v) for k,v in ngs.items()}
        for r in copied["NFL_NGS_PASS"]:
            if r["week"]=="9":
                r["pass_yards"]="9999"
        alt=study(weekly,{k:tuple(v) for k,v in copied.items()})
        self.assertEqual(base["folds"][:4],alt["folds"][:4])
        self.assertEqual(base["totals"]["PASS_YDS"]["baseline"],
                         alt["totals"]["PASS_YDS"]["baseline"])

    def test_future_row_retrospective_is_ungraded_not_zero(self):
        weekly,ngs=make_data()
        keep=tuple(r for r in weekly if not (r["week"]=="8" and r["team"]=="SEA"))
        output=study(keep,ngs)
        self.assertGreater(output["counts"]["not_observed_in_holdout"],0)
        self.assertLess(output["totals"]["RUSH_YDS"]["baseline"]["n"],160)
        self.assertTrue(output["missing_player_actuals_not_assumed_zero"])

    def test_cross_team_duplicate_same_player_isnt_silently_reassigned(self):
        weekly,ngs=make_data()
        same=dict(weekly[0])
        with self.assertRaisesRegex(ValueError,"WEEKLY_DUPLICATE_PLAYER_TEAM_WEEK"):
            study(weekly+(same,),ngs)

    def test_invalid_duplicate_nextgen_keys_block(self):
        weekly,ngs=make_data()
        dup={k:list(v) for k,v in ngs.items()}
        dup["NFL_NGS_RUSH"].append(dict(dup["NFL_NGS_RUSH"][0]))
        with self.assertRaisesRegex(ValueError,"NGS_DUPLICATED_WEEKLY_PLAYER_TEAM_ROW"):
            study(weekly,{k:tuple(v) for k,v in dup.items()})

    def test_aggregate_week_zero_not_in_ngs_fit(self):
        weekly,ngs=make_data()
        base=study(weekly,ngs)
        changed={k:list(v) for k,v in ngs.items()}
        for asset in changed:
            for row in list(changed[asset])[::10]:
                row=dict(row);row["week"]="0"
                for field in ("pass_yards","rush_yards","yards"):
                    if field in row:row[field]="100000"
                changed[asset].append(row)
        alt=study(weekly,{k:tuple(v) for k,v in changed.items()})
        self.assertEqual(base["folds"],alt["folds"])
        self.assertEqual(base["totals"],alt["totals"])

    def test_missing_ngs_cannot_be_backfilled_as_naive_quote(self):
        weekly,ngs=make_data()
        missing={k:v for k,v in ngs.items() if k!="NFL_NGS_PASS"}
        with self.assertRaisesRegex(ValueError,"THREE_NGS_SOURCE_ASSETS_REQUIRED"):
            study(weekly,missing)

    def test_player_moment_cannot_claim_verified_active_from_history(self):
        with self.assertRaisesRegex(ValueError,
                    "STARTER_STATUS_CANNOT_BE_INFERRED_FROM_GAME_LOGS"):
            ResearchForecast("P","SEA",8,"PASS_YDS",7,200,201,210,20,
                             candidate_has_verified_active_status=True)

    def test_raw_github_asset_digest_mismatch_refused(self):
        raw=(b"season,week,season_type,player_id,team,rushing_tds,"
             b"receiving_tds\n2026,1,REG,P,SEA,0,0\n")
        now=datetime(2026,11,15,20,tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError,"SOURCE_ORIGINAL_SHA256_MISMATCH"):
            parse_source_archive(raw,source_id="NFLVERSE_WEEKLY",
                expected_sha256="sha256:"+"a"*64,
                observed_at_utc=now,captured_at_utc=now)

    def test_no_betting_lines_or_player_props_emitted(self):
        r=study()
        self.assertNotIn("p_anytime_td",r)
        self.assertNotIn("stakes",r)
        self.assertNotIn("p_over",r)
        self.assertTrue(r["no_automatic_model_adoption"])


if __name__=="__main__":
    unittest.main()
