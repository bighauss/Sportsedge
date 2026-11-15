"""Synthetic prospective NFL player-forecast freeze/grade acceptance suite.

Time/source values are test fixtures; a passing test never establishes
historical publication, upstream signature, betting edge or authorization.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import io
import json
import unittest

from sportsedge.validation.forward_player_evidence import (
    RESEARCH_FREEZE, RESEARCH_GRADE, freeze_player_forecasts,
    grade_frozen_capture, _write_private_create_only,
)
from sportsedge.markets.player_forecast_intake import REQUIRED

NOW = datetime(2026,11,15,17,0,0,tzinfo=timezone.utc)
ASOF = NOW - timedelta(hours=1)
START = NOW + timedelta(hours=8)
END = START + timedelta(hours=3)
AFTER = END + timedelta(hours=1)
H = "sha256:"+"a"*64


def iso(t):
    return t.isoformat()


def csv_bytes(rows, columns):
    f=io.StringIO()
    w=csv.DictWriter(f,fieldnames=columns)
    w.writeheader()
    w.writerows(rows)
    return f.getvalue().encode("utf-8")


def write(root, filename, raw):
    p=Path(root)/filename
    p.write_bytes(raw)
    return {"path":str(p),"raw_sha256":"sha256:"+sha256(raw).hexdigest()}


def inputs(root, *, confirmed_active="1", lineup_state="ACTIVE",
           actual_rows=True, actual_value="0"):
    source=write(root,"source.csv",(
      b"season,week,season_type,player_id,team,rushing_tds,receiving_tds\n"
      b"2026,9,REG,P1,BUF,0,1\n"))
    source.update({
        "source_id":"NFLVERSE_WEEKLY",
        "data_through_utc":iso(NOW-timedelta(days=2)),
        "observed_at_utc":iso(NOW-timedelta(hours=5)),
        "captured_at_utc":iso(NOW-timedelta(hours=4)),
    })
    lineup=write(root,"lineup.csv",csv_bytes([{
        "event_id":"GAME1","player_id":"P1","team_id":"BUF",
        "status":lineup_state}],("event_id","player_id","team_id","status")))
    lineup.update({
        "source_name":"NFL_CLUB_INACTIVES_CLAIM",
        "observed_at_utc":iso(ASOF-timedelta(minutes=25)),
        "captured_at_utc":iso(ASOF-timedelta(minutes=20)),
    })
    projection={
        "sport":"NFL","event_id":"GAME1","player_id":"P1",
        "team_id":"BUF","stat":"REC_YDS","mean":"61.0","sd":"19.0",
        "asof_utc":iso(ASOF-timedelta(minutes=3)),
        "trained_until_utc":iso(NOW-timedelta(days=2)),
        "source_snapshot_sha256":source["raw_sha256"],
        "source_id":"NFLVERSE_WEEKLY","confirmed_active":confirmed_active,
        "projected_targets":"7","projected_rush_attempts":"",
        "projected_minutes":"","confirmed_pitcher":"0",
        "confirmed_batting_lineup":"0",
    }
    forecast=write(root,"forecast.csv",
                   csv_bytes([projection],sorted(REQUIRED)))
    manifest={
        "schema":RESEARCH_FREEZE,"event_id":"GAME1",
        "home_id":"BUF","away_id":"MIA","start_utc":iso(START),
        "forecast_asof_utc":iso(ASOF),
        "forecast_file":forecast,"lineup_file":lineup,
        "source_files":[source],"roster_player_ids":["P1"],
        "odds_observed_at_utc":None,
    }
    final=write(root,"actual.csv",csv_bytes([{
        "event_id":"GAME1","player_id":"P1","team_id":"BUF",
        "stat":"REC_YDS","actual":actual_value}] if actual_rows else [],
        ("event_id","player_id","team_id","stat","actual")))
    final.update({
        "source_id":"NFLVERSE_WEEKLY",
        "observed_at_utc":iso(END+timedelta(minutes=20)),
        "captured_at_utc":iso(END+timedelta(minutes=22)),
    })
    return manifest,final


def grade_request(root,captured_hash,result):
    return {
       "schema":RESEARCH_GRADE,
       "frozen_capture_path":str(Path(root)/"frozen.json"),
       "frozen_capture_sha256":captured_hash,
       "event_id":"GAME1","event_final_at_utc":iso(END),
       "result_file":result,
    }


class ForwardPlayerEvidence(unittest.TestCase):
    def test_pregame_freeze_and_final_grade_zero_stat_is_real(self):
        with TemporaryDirectory() as d:
            m,final=inputs(d)
            f=freeze_player_forecasts(m,now=NOW)
            self.assertEqual(f["state"],"PAPER_0U_FORWARD_CAPTURE_ONLY")
            self.assertEqual((f["frozen_rows"],f["blocked_rows"]),(1,0))
            self.assertFalse(f["lineup_authenticated_independently"])
            self.assertFalse(f["source_authenticated_independently"])
            self.assertEqual((f["approved_stake_u"],f["official_counted"]),(0,0))
            h=_write_private_create_only(Path(d)/"frozen.json",f)
            g=grade_frozen_capture(grade_request(d,h,final),now=AFTER)
            self.assertEqual(g["graded_rows"],1)
            self.assertEqual(g["unresolved_rows"],0)
            self.assertEqual(g["results"][0]["actual"],0)
            self.assertEqual(g["results"][0]["actual_minus_prediction"],-61.0)
            self.assertEqual((g["approved_stake_u"],g["official_counted"]),(0,0))

    def test_missing_final_stat_never_replaced_with_zero(self):
        with TemporaryDirectory() as d:
            m,final=inputs(d,actual_rows=False)
            f=freeze_player_forecasts(m,now=NOW)
            h=_write_private_create_only(Path(d)/"frozen.json",f)
            g=grade_frozen_capture(grade_request(d,h,final),now=AFTER)
            self.assertEqual(g["graded_rows"],0)
            self.assertEqual(g["unresolved_rows"],1)
            self.assertEqual(g["results"][0]["state"],"UNRESOLVED_MISSING_FINAL_STAT")
            self.assertIsNone(g["results"][0]["actual"])

    def test_player_missing_confirmed_active_is_blocked_but_preserved(self):
        with TemporaryDirectory() as d:
            m,final=inputs(d,confirmed_active="0",lineup_state="UNCONFIRMED")
            f=freeze_player_forecasts(m,now=NOW)
            self.assertEqual((f["frozen_rows"],f["blocked_rows"]),(0,1))
            self.assertIn("LINEUP_NOT_CONFIRMED_ACTIVE",f["forecast_rows"][0]["reasons"])
            h=_write_private_create_only(Path(d)/"frozen.json",f)
            g=grade_frozen_capture(grade_request(d,h,final),now=AFTER)
            self.assertEqual(g["blocked_rows"],1)
            self.assertEqual(g["graded_rows"],0)

    def test_future_or_postkickoff_freeze_refused(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            with self.assertRaisesRegex(ValueError,"FREEZE_IS_LATE_OR_IN_FUTURE"):
                freeze_player_forecasts(m,now=START)
            with self.assertRaisesRegex(ValueError,"FREEZE_IS_LATE_OR_IN_FUTURE"):
                freeze_player_forecasts(m,now=ASOF-timedelta(seconds=1))

    def test_forecast_file_changed_after_hash_is_rejected(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            Path(m["forecast_file"]["path"]).write_text("player,stat\nP2,PASS_YDS\n")
            with self.assertRaisesRegex(ValueError,"ORIGINAL_FILE_HASH_MISMATCH"):
                freeze_player_forecasts(m,now=NOW)

    def test_source_file_changed_after_hash_is_rejected(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            Path(m["source_files"][0]["path"]).write_text("fake")
            with self.assertRaisesRegex(ValueError,"ORIGINAL_FILE_HASH_MISMATCH"):
                freeze_player_forecasts(m,now=NOW)

    def test_lineup_receipt_after_forecast_blocks(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            m["lineup_file"]["captured_at_utc"]=iso(ASOF+timedelta(seconds=1))
            with self.assertRaisesRegex(ValueError,"LINEUP_CAPTURE_TOO_LATE"):
                freeze_player_forecasts(m,now=NOW)

    def test_source_after_observed_quote_blocks(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            m["odds_observed_at_utc"]=iso(ASOF-timedelta(hours=4,minutes=30))
            with self.assertRaisesRegex(ValueError,"SOURCE_AFTER_ODDS_QUOTE"):
                freeze_player_forecasts(m,now=NOW)

    def test_extra_api_key_or_auth_claim_is_forbidden(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            m["source_auth_verified"]=True
            with self.assertRaisesRegex(ValueError,"INVALID_FIELDS:forward_freeze"):
                freeze_player_forecasts(m,now=NOW)

    def test_no_duplicate_player_stat_in_same_event(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            raw=Path(m["forecast_file"]["path"]).read_bytes()
            cols,rows=csv.DictReader(io.StringIO(raw.decode())).fieldnames,None
            rr=list(csv.DictReader(io.StringIO(raw.decode())))
            new=csv_bytes(rr+rr,cols)
            m["forecast_file"]=write(d,"twice.csv",new)
            with self.assertRaisesRegex(ValueError,"DUPLICATE_PLAYER_STAT_ON_FROZEN_EVENT"):
                freeze_player_forecasts(m,now=NOW)

    def test_missing_source_bound_to_player_feature_blocks_individual(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            raw=Path(m["forecast_file"]["path"]).read_bytes()
            reader=csv.DictReader(io.StringIO(raw.decode()))
            rows=list(reader)
            rows[0]["source_snapshot_sha256"]=H
            m["forecast_file"]=write(d,"mismatched_forecast.csv",
                                      csv_bytes(rows,reader.fieldnames))
            out=freeze_player_forecasts(m,now=NOW)
            self.assertEqual(out["blocked_rows"],1)
            self.assertIn("MODEL_FEATURE_SOURCE_NOT_IN_PREGAME_ARCHIVE",
                          out["forecast_rows"][0]["reasons"])

    def test_external_input_no_bet_market_prices_can_taint_forecast(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            raw=Path(m["forecast_file"]["path"]).read_bytes()
            reader=csv.DictReader(io.StringIO(raw.decode()))
            rows=list(reader)
            for r in rows:r["odds"]="-110"
            m["forecast_file"]=write(d,"book_tainted.csv",
                            csv_bytes(rows,list(reader.fieldnames)+["odds"]))
            with self.assertRaisesRegex(ValueError,"BOOKMAKER_DERIVED_PROJECTION_FIELDS"):
                freeze_player_forecasts(m,now=NOW)

    def test_create_only_does_not_overwrite_original_archive(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            captured=freeze_player_forecasts(m,now=NOW)
            path=Path(d)/"frozen.json"
            first=_write_private_create_only(path,captured)
            with self.assertRaises(FileExistsError):
                _write_private_create_only(path,captured)
            self.assertEqual(first,"sha256:"+sha256(path.read_bytes()).hexdigest())

    def test_post_capture_tampering_is_caught_before_grade(self):
        with TemporaryDirectory() as d:
            m,final=inputs(d)
            obj=freeze_player_forecasts(m,now=NOW)
            h=_write_private_create_only(Path(d)/"frozen.json",obj)
            Path(d,"frozen.json").write_text('{"state":"OFFICIAL"}')
            with self.assertRaisesRegex(ValueError,"ORIGINAL_FILE_HASH_MISMATCH"):
                grade_frozen_capture(grade_request(d,h,final),now=AFTER)

    def test_result_never_graded_before_final(self):
        with TemporaryDirectory() as d:
            m,final=inputs(d)
            obj=freeze_player_forecasts(m,now=NOW)
            h=_write_private_create_only(Path(d)/"frozen.json",obj)
            with self.assertRaisesRegex(ValueError,"INVALID_FINAL_GAME_CHRONOLOGY"):
                grade_frozen_capture(grade_request(d,h,final),now=START)

    def test_duplicate_final_same_player_stat_fails(self):
        with TemporaryDirectory() as d:
            m,final=inputs(d)
            obj=freeze_player_forecasts(m,now=NOW)
            h=_write_private_create_only(Path(d)/"frozen.json",obj)
            r=dict(final)
            path=Path(r["path"])
            reader=csv.DictReader(io.StringIO(path.read_text()))
            rows=list(reader)
            twice=csv_bytes(rows+rows,reader.fieldnames)
            r.update(write(d,"actual_twice.csv",twice))
            with self.assertRaisesRegex(ValueError,"DUPLICATE_PLAYER_STAT_FINAL"):
                grade_frozen_capture(grade_request(d,h,r),now=AFTER)

    def test_duplicate_json_manifest_key_fails(self):
        from sportsedge.validation.forward_player_evidence import _strict_json
        with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
            _strict_json(b'{"schema":"x","schema":"y"}')


if __name__ == "__main__":
    unittest.main()
