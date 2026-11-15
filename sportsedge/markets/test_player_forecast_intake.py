"""All-five-sport synthetic independent prop forecast CSV input contracts."""
import csv
import io
from hashlib import sha256
import unittest
from datetime import datetime, timezone, timedelta

from sportsedge.markets.player_forecast_intake import ingest_player_forecast_csv

D=datetime(2026,11,15,17,0,0,tzinfo=timezone.utc)
H="sha256:"+"a"*64
COLUMNS=[
    "sport","event_id","player_id","team_id","stat","mean","sd",
    "asof_utc","trained_until_utc","source_snapshot_sha256","source_id",
    "confirmed_active","projected_targets","projected_rush_attempts",
    "projected_minutes","confirmed_pitcher","confirmed_batting_lineup",
]


def fixture(sport,stat,source,**kw):
    row={
        "sport":sport,"event_id":"GAME-1","player_id":"PLAYER-1","team_id":"HOME",
        "stat":stat,"mean":"12","sd":"4",
        "asof_utc":(D-timedelta(hours=2)).isoformat(),
        "trained_until_utc":(D-timedelta(days=2)).isoformat(),
        "source_snapshot_sha256":H,"source_id":source,
        "confirmed_active":"1","projected_targets":"",
        "projected_rush_attempts":"","projected_minutes":"",
        "confirmed_pitcher":"0","confirmed_batting_lineup":"0",
    }
    row.update(kw)
    return row


def asbytes(rows,columns=COLUMNS):
    stream=io.StringIO()
    w=csv.DictWriter(stream,fieldnames=columns)
    w.writeheader();w.writerows(rows)
    return stream.getvalue().encode("utf-8")


def call(rows,sport,raw=None):
    raw=raw or asbytes(rows)
    return ingest_player_forecast_csv(
        raw,sport=sport,event_id="GAME-1",game_roster_ids=frozenset({"PLAYER-1"}),
        event_team_ids=frozenset({"HOME","AWAY"}),
        forecast_freeze_utc=D-timedelta(minutes=25),
        odds_observed_at_utc=D-timedelta(minutes=1),
        expected_file_sha256="sha256:"+sha256(raw).hexdigest())


class AllFiveSportProps(unittest.TestCase):
    def test_nfl_receiving_yards(self):
        p=call([fixture("NFL","REC_YDS","NFLVERSE_NGS",projected_targets="5")],"NFL")
        self.assertEqual(p.moments[0].projected_targets,5)
        self.assertEqual((p.official_counted,p.approved_stake_u),(0,0))

    def test_cfb_rushing_yards(self):
        p=call([fixture("CFB","RUSH_YDS","CFB_DATA",projected_rush_attempts="12")],"CFB")
        self.assertEqual(p.sport,"CFB")

    def test_cbb_points(self):
        p=call([fixture("CBB","POINTS","CBB_HOOPR")],"CBB")
        self.assertEqual(p.moments[0].stat,"POINTS")

    def test_nba_threes_with_20_minutes(self):
        p=call([fixture("NBA","3PM","NBA_STATS",projected_minutes="24")],"NBA")
        self.assertEqual(p.moments[0].projected_minutes,24)

    def test_mlb_pitcher_strikeouts_with_confirmed_starter(self):
        p=call([fixture("MLB","PITCHER_K","MLB_STATCAST",confirmed_pitcher="1")],"MLB")
        self.assertTrue(p.moments[0].confirmed_pitcher)

    def test_mlb_batter_hr_requires_confirmed_lineup(self):
        with self.assertRaisesRegex(ValueError,"BATTING_LINEUP_NOT_CONFIRMED"):
            call([fixture("MLB","HOME_RUNS","MLB_STATCAST")],"MLB")

    def test_unknown_name_without_stable_id_refused(self):
        r=fixture("NBA","POINTS","NBA_STATS",projected_minutes="24")
        r["player_id"]="J. SMITH"
        with self.assertRaisesRegex(ValueError,"UNBOUND_ROSTER_OR_TEAM_ID"):
            call([r],"NBA")

    def test_book_derived_columns_refused(self):
        r=fixture("CBB","POINTS","CBB_HOOPR")
        r["market_implied_mean"]="17.5"
        raw=asbytes([r],COLUMNS+["market_implied_mean"])
        with self.assertRaisesRegex(ValueError,"BOOKMAKER_DERIVED_INPUT"):
            call([r],"CBB",raw=raw)

    def test_wrong_source_for_sport(self):
        with self.assertRaisesRegex(ValueError,"UNAPPROVED_PLAYER_FEATURE_SOURCE"):
            call([fixture("NFL","PASS_YDS","NBA_STATS")],"NFL")

    def test_missing_confirmed_active_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"PLAYER_NOT_CONFIRMED_ACTIVE"):
            call([fixture("NBA","POINTS","NBA_STATS",projected_minutes="24",
                          confirmed_active="0")],"NBA")

    def test_lookahead_after_price_blocked(self):
        r=fixture("CBB","POINTS","CBB_HOOPR",
                  asof_utc=D.isoformat())
        with self.assertRaisesRegex(ValueError,"PLAYER_FORECAST_CHRONOLOGY_OR_LOOKAHEAD"):
            call([r],"CBB")

    def test_replaced_original_source_file_rejected(self):
        r=fixture("CBB","POINTS","CBB_HOOPR")
        raw=asbytes([r])
        with self.assertRaisesRegex(ValueError,"PLAYER_FORECAST_FILE_HASH_MISMATCH"):
            ingest_player_forecast_csv(
                raw,sport="CBB",event_id="GAME-1",
                game_roster_ids=frozenset({"PLAYER-1"}),
                event_team_ids=frozenset({"HOME","AWAY"}),
                forecast_freeze_utc=D-timedelta(minutes=25),
                odds_observed_at_utc=D-timedelta(minutes=1),
                expected_file_sha256=H)

    def test_rush_attempt_volume_refused(self):
        with self.assertRaisesRegex(ValueError,"RUSHING_PROP_ATTEMPT_VOLUME_BELOW_FLOOR"):
            call([fixture("NFL","RUSH_YDS","NFLVERSE_WEEKLY",
                          projected_rush_attempts="9")],"NFL")

    def test_duplicate_player_stat_rows(self):
        r=fixture("CBB","POINTS","CBB_HOOPR")
        with self.assertRaisesRegex(ValueError,"DUPLICATED_PLAYER_STAT_PROJECTION"):
            call([r,r],"CBB")

    def test_nan_variance_rejected(self):
        with self.assertRaisesRegex(ValueError,"PLAYER_FORECAST_NONFINITE_OR_NEGATIVE:sd"):
            call([fixture("NBA","POINTS","NBA_STATS",projected_minutes="24",sd="NaN")],"NBA")


if __name__=="__main__":
    unittest.main()
