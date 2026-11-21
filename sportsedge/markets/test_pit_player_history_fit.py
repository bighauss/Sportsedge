"""Offline synthetic tests: prior-game player rates, source chronology, 0u."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import io
import json
import unittest

from sportsedge.markets.pit_player_history_fit import (
    SCHEMA, CSV_COLUMNS, fit_player_history, main,
)
from sportsedge.markets.player_projection_builder import build_player_forecast_csv

F = datetime(2026,11,21,17,tzinfo=timezone.utc)
H = "sha256:"+"a"*64


def row(sport, i, stat, unit, opportunity, value, *, player="P-1",team="HOME"):
    return {
        "sport":sport, "game_id":"HISTORY-"+str(i),
        "game_end_utc":(F-timedelta(days=i*7)).isoformat(),
        "player_id":player,"team_id":team,"stat":stat,
        "opportunity_unit":unit,
        "opportunities":str(opportunity), "actual_stat":str(value),
    }


def source(rows):
    stream=io.StringIO(newline="")
    w=csv.DictWriter(stream, fieldnames=CSV_COLUMNS,lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return stream.getvalue().encode()


def ctx(sport, raw):
    return {
        "schema":SCHEMA, "sport":sport, "event_id":"NEXT-1",
        "home_id":"HOME","away_id":"AWAY",
        "event_start_utc":(F+timedelta(hours=2)).isoformat(),
        "forecast_asof_utc":F.isoformat(),
        "source_published_utc":(F-timedelta(hours=4)).isoformat(),
        "source_captured_utc":(F-timedelta(hours=3)).isoformat(),
        "normalized_history_sha256":"sha256:"+sha256(raw).hexdigest(),
        "original_provider_sha256":H,
        "source_id":{"NFL":"NFLVERSE_WEEKLY","CFB":"CFB_DATA",
                     "CBB":"CBB_HOOPR"}[sport],
        "frozen_roster":{"P-1":"HOME"},
        "confirmed_activity":{"P-1":True},
    }


def four(sport="NFL",stat="PASS_YDS",unit="PASS_ATT",values=None):
    values=values or [(30,180),(32,224),(34,204),(36,252)]
    return [row(sport,i,stat,unit,n,val) for i,(n,val) in
            enumerate(values,1)]


class PriorGamePlayerFit(unittest.TestCase):
    def test_nfl_qb_pass_yards_prior_only_to_existing_builder(self):
        raw=source(four())
        features,report=fit_player_history(raw,ctx("NFL",raw))
        self.assertEqual(report["forecast_rows"],1)
        self.assertEqual(report["status"],"PAPER_0U_UNCALIBRATED_PRIOR_GAMES_BASELINE")
        self.assertFalse(report["source_authenticated"])
        self.assertEqual((report["approved_stake_u"],report["official_counted"]),(0,0))
        self.assertEqual(features["players"][0]["stat"],"PASS_YDS")
        self.assertAlmostEqual(features["players"][0]["opportunities"],33)
        self.assertAlmostEqual(features["players"][0]["rate_per_opportunity"],860/132)
        self.assertGreater(features["players"][0]["standard_deviation"],0)
        csv_raw,census=build_player_forecast_csv(features)
        self.assertEqual(census["produced"],1)
        rows=list(csv.DictReader(io.StringIO(csv_raw.decode())))
        self.assertEqual(rows[0]["mean"],"215")
        self.assertTrue(report["history_blocked"])

    def test_cbb_point_rate_from_actual_minutes_and_empirical_sd(self):
        raw=source(four("CBB","POINTS","MINUTES",[(30,18),(32,21),(28,12),(34,23)]))
        feat,rep=fit_player_history(raw,ctx("CBB",raw))
        self.assertEqual(rep["forecast_rows"],1)
        p=feat["players"][0]
        self.assertAlmostEqual(p["opportunities"],31)
        self.assertAlmostEqual(p["rate_per_opportunity"],74/124)
        out,census=build_player_forecast_csv(feat)
        self.assertEqual(census["produced"],1)
        self.assertEqual(list(csv.DictReader(io.StringIO(out.decode())))[0]["mean"],"18.5")

    def test_cfb_rushing_research_usage_from_prior_only(self):
        raw=source(four("CFB","RUSH_YDS","RUSH_ATT",
                        [(12,60),(15,80),(14,70),(19,110)]))
        feat,rep=fit_player_history(raw,ctx("CFB",raw))
        self.assertEqual(rep["forecast_rows"],1)
        p=feat["players"][0]
        self.assertAlmostEqual(p["opportunities"],15)
        self.assertAlmostEqual(p["rate_per_opportunity"],320/60)
        out,census=build_player_forecast_csv(feat)
        self.assertEqual(census["produced"],1)
        self.assertEqual(list(csv.DictReader(io.StringIO(out.decode())))[0]["mean"],"80")

    def test_one_or_three_games_never_get_guess_variance(self):
        for n in (1,2,3):
            with self.subTest(n=n):
                raw=source(four()[:n])
                with self.assertRaisesRegex(ValueError,"HISTORY_NO_VALID_TRAINED_STATS"):
                    fit_player_history(raw,ctx("NFL",raw))

    def test_duplicate_player_game_stat_is_fatal(self):
        history=four()
        history.append(dict(history[0]))
        raw=source(history)
        with self.assertRaisesRegex(ValueError,"HISTORY_DUPLICATE_PLAYER_GAME_STAT"):
            fit_player_history(raw,ctx("NFL",raw))

    def test_future_game_in_original_ledger_is_rejected(self):
        history=four()
        history[0]["game_end_utc"]=(F+timedelta(hours=3)).isoformat()
        raw=source(history)
        with self.assertRaisesRegex(ValueError,"HISTORY_FUTURE_GAME"):
            fit_player_history(raw,ctx("NFL",raw))

    def test_target_event_cannot_be_a_prior_game(self):
        history=four()
        history[0]["game_id"]="NEXT-1"
        raw=source(history)
        with self.assertRaisesRegex(ValueError,"HISTORY_TARGET_EVENT_IN_ARCHIVE"):
            fit_player_history(raw,ctx("NFL",raw))

    def test_game_finish_time_must_agree_across_player_stat_rows(self):
        history=four()
        other=row("NFL",1,"COMPLETIONS","PASS_ATT",30,20)
        other["game_end_utc"]=(F-timedelta(days=2)).isoformat()
        raw=source(history+[other])
        with self.assertRaisesRegex(ValueError,"HISTORY_INCONSISTENT_GAME_END"):
            fit_player_history(raw,ctx("NFL",raw))

    def test_matching_game_finish_times_accept_equivalent_utc_offsets(self):
        other=row("NFL",1,"COMPLETIONS","PASS_ATT",30,20)
        other["game_end_utc"]=other["game_end_utc"].replace("+00:00","Z")
        raw=source(four()+[other])
        _,report=fit_player_history(raw,ctx("NFL",raw))
        self.assertEqual(report["forecast_rows"],1)

    def test_malformed_csv_quotes_are_rejected(self):
        raw=source(four()).rstrip(b"\n")
        raw=raw[:raw.rfind(b",")]+b',"252'
        with self.assertRaisesRegex(ValueError,"HISTORY_INVALID_CSV"):
            fit_player_history(raw,ctx("NFL",raw))

    def test_source_snapshot_published_or_captured_late(self):
        raw=source(four())
        q=ctx("NFL",raw)
        q["source_captured_utc"]=(F+timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"HISTORY_SOURCE_PUBLICATION_OR_FREEZE_LOOKAHEAD"):
            fit_player_history(raw,q)

    def test_archive_digest_change_and_fake_bookmaker_feature_refused(self):
        raw=source(four())
        q=ctx("NFL",raw)
        q["normalized_history_sha256"]="sha256:"+"0"*64
        with self.assertRaisesRegex(ValueError,"HISTORY_NORMALIZED_ORIGINAL_BYTES_HASH_MISMATCH"):
            fit_player_history(raw,q)
        q=ctx("NFL",raw)
        q["dk_moneyline"]=-110
        with self.assertRaisesRegex(ValueError,"HISTORY_CONTEXT_KEYS_REQUIRED_NO_BOOKMARKET_INPUT"):
            fit_player_history(raw,q)

    def test_wrong_stat_unit_or_extra_csv_columns_refused(self):
        history=four()
        history[0]["opportunity_unit"]="TEAM_RUSH_PLAYS"
        raw=source(history)
        with self.assertRaisesRegex(ValueError,"HISTORY_UNSUPPORTED_STAT_OR_UNIT"):
            fit_player_history(raw,ctx("NFL",raw))
        history=four()
        stream=io.StringIO()
        writer=csv.DictWriter(stream,fieldnames=list(CSV_COLUMNS)+["odds"])
        writer.writeheader()
        writer.writerows([dict(z,odds=-110) for z in history])
        raw=stream.getvalue().encode()
        with self.assertRaisesRegex(ValueError,"HISTORY_INVALID_CSV"):
            fit_player_history(raw,ctx("NFL",raw))

    def test_player_team_transfer_without_stable_rebind_refused(self):
        history=four()
        history[0]["team_id"]="AWAY"
        raw=source(history)
        with self.assertRaisesRegex(ValueError,"HISTORY_PLAYER_CHANGED_TEAM"):
            fit_player_history(raw,ctx("NFL",raw))

    def test_zero_variance_refused_instead_of_inventing_sd(self):
        raw=source(four(values=[(30,180)]*4))
        with self.assertRaisesRegex(ValueError,"HISTORY_NO_VALID_TRAINED_STATS"):
            fit_player_history(raw,ctx("NFL",raw))

    def test_roster_without_confirmed_activity_refused(self):
        raw=source(four())
        q=ctx("NFL",raw)
        q["confirmed_activity"]={}
        with self.assertRaisesRegex(ValueError,"HISTORY_FROZEN_ROSTER_ACTIVITY_CENSUS_REQUIRED"):
            fit_player_history(raw,q)

    def test_inactive_roster_yields_no_stat_not_certified(self):
        raw=source(four())
        q=ctx("NFL",raw)
        q["confirmed_activity"]["P-1"]=False
        with self.assertRaisesRegex(ValueError,"HISTORY_NO_VALID_TRAINED_STATS"):
            fit_player_history(raw,q)

    def test_no_selection_by_book_line_variations(self):
        raw=source(four())
        q=ctx("NFL",raw)
        p,r=fit_player_history(raw,q)
        self.assertEqual(len(p["players"]),1)
        self.assertEqual(p["players"][0]["stat"],"PASS_YDS")
        self.assertEqual(r["opportunity_model"],
                         "PRIOR_5_GAME_MEAN_NOT_OPPONENT_ADJUSTED")

    def test_private_create_only_cli_and_no_rewrite(self):
        raw=source(four())
        q=ctx("NFL",raw)
        with TemporaryDirectory() as d:
            src=Path(d)/"history.csv"
            context=Path(d)/"context.json"
            features=Path(d)/"features.json"
            census=Path(d)/"census.json"
            src.write_bytes(raw)
            context.write_text(json.dumps(q))
            self.assertEqual(main([str(src),str(context),str(features),str(census)]),0)
            self.assertEqual(json.loads(census.read_text())["forecast_rows"],1)
            with self.assertRaisesRegex(ValueError,"HISTORY_OUTPUT_CREATE_ONLY"):
                main([str(src),str(context),str(features),str(census)])


if __name__=="__main__":
    unittest.main()
