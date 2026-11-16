"""Synthetic prospective NFL player-forecast freeze/grade acceptance suite.

Time/source values are test fixtures; a passing test never establishes
historical publication, upstream signature, betting edge or authorization.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory
import csv
import io
import json
import os
import subprocess
import sys
import unittest

from sportsedge.validation.forward_player_evidence import (
    RESEARCH_FREEZE, RESEARCH_GRADE, freeze_player_forecasts,
    grade_frozen_capture, _write_private_create_only, main,
    _trusted_registry_root, _freeze_registry_path, _grade_registry_path,
)
from sportsedge.markets.player_forecast_intake import REQUIRED

NOW = datetime(2026,11,15,17,0,0,tzinfo=timezone.utc)
ASOF = NOW - timedelta(minutes=30)
START = NOW + timedelta(hours=1)
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
    model_artifact=write(root,"model_revision.py",(
        b"MODEL_VERSION='PLAYER_LAG3_RESEARCH_CANDIDATE'\n"))
    manifest={
        "schema":RESEARCH_FREEZE,"event_id":"GAME1",
        "home_id":"BUF","away_id":"MIA","season":2026,"week":11,
        "start_utc":iso(START),
        "forecast_asof_utc":iso(ASOF),
        "forecast_file":forecast,"model_artifact":model_artifact,
        "lineup_file":lineup,
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

    def test_registered_weekly_source_must_have_real_csv_schema(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            bad=write(d,"bad_source.csv",b"garbage\nnot,a,valid,source\n")
            m["source_files"][0].update(bad)
            with self.assertRaisesRegex(ValueError,"SOURCE_REQUIRED_COLUMN_MISSING"):
                freeze_player_forecasts(m,now=NOW)

    def test_ngs_missing_gsis_id_header_rejected(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            bad=write(d,"ngs_missing_gsis.csv",b"season,week,season_type,team_abbr\n2026,9,REG,BUF\n")
            m["source_files"][0].update(bad)
            m["source_files"][0]["source_id"]="NFLVERSE_NGS"
            with self.assertRaisesRegex(ValueError,"NFL_NGS_SOURCE_ID_OR_WEEK_COLUMNS_MISSING"):
                freeze_player_forecasts(m,now=NOW)

    def test_pbp_source_disallowed_for_player_curve(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            m["source_files"][0]["source_id"]="NFLVERSE_PBP"
            with self.assertRaisesRegex(ValueError,"NFL_PLAYER_SOURCE_NOT_ALLOWLISTED"):
                freeze_player_forecasts(m,now=NOW)

    def test_same_game_week_row_blocks_even_if_manifest_claims_prior_cutoff(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            raw=(
                b"season,week,season_type,player_id,team,rushing_tds,receiving_tds\n"
                b"2026,11,REG,P1,BUF,0,1\n")
            m["source_files"][0].update(
                write(d,"same_week_source.csv",raw))
            with self.assertRaisesRegex(ValueError,
                              "SOURCE_ROW_SAME_OR_FUTURE_GAME_WEEK"):
                freeze_player_forecasts(m,now=NOW)

    def test_ngs_week_zero_season_aggregate_blocks(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            raw=(
                b"season,week,season_type,player_gsis_id,team_abbr\n"
                b"2026,0,REG,P1,BUF\n")
            m["source_files"][0].update(
                write(d,"ngs_aggregate.csv",raw))
            m["source_files"][0]["source_id"]="NFLVERSE_NGS"
            with self.assertRaisesRegex(ValueError,
                              "SOURCE_ROW_SAME_OR_FUTURE_GAME_WEEK"):
                freeze_player_forecasts(m,now=NOW)

    def test_model_source_artifact_tampering_refused(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            Path(m["model_artifact"]["path"]).write_text("CHANGED=True\n")
            with self.assertRaisesRegex(ValueError,
                              "ORIGINAL_FILE_HASH_MISMATCH"):
                freeze_player_forecasts(m,now=NOW)

    def test_season_and_week_and_model_sha_preserved_in_private_freeze(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            f=freeze_player_forecasts(m,now=NOW)
            self.assertEqual((f["season"],f["week"]),(2026,11))
            self.assertEqual(
                f["model_artifact_sha256"],m["model_artifact"]["raw_sha256"])

    def test_lineup_receipt_after_forecast_blocks(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            m["lineup_file"]["captured_at_utc"]=iso(ASOF+timedelta(seconds=1))
            with self.assertRaisesRegex(ValueError,"LINEUP_CAPTURE_TOO_LATE"):
                freeze_player_forecasts(m,now=NOW)

    def test_quote_before_feature_freeze_blocks(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            m["odds_observed_at_utc"]=iso(ASOF-timedelta(hours=4,minutes=30))
            with self.assertRaisesRegex(ValueError,"INVALID_ODDS_OBSERVATION_ORDER"):
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

    def test_stale_lineup_evidence_blocks_freeze(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            m["lineup_file"]["observed_at_utc"]=iso(START-timedelta(hours=3))
            with self.assertRaisesRegex(ValueError,"STALE_LINEUP_OBSERVATION"):
                freeze_player_forecasts(m,now=NOW)

    def test_unregistered_lineup_source_blocks_freeze(self):
        with TemporaryDirectory() as d:
            m,_=inputs(d)
            m["lineup_file"]["source_name"]="UNREGISTERED"
            with self.assertRaisesRegex(ValueError,"UNREGISTERED_LINEUP_SOURCE"):
                freeze_player_forecasts(m,now=NOW)

    def test_subfolder_cwd_cannot_write_private_archive_inside_repository(self):
        with TemporaryDirectory() as d:
            repo_root=Path(__file__).resolve().parents[2]
            with patch.object(Path,"cwd",return_value=repo_root/"docs"):
                with self.assertRaisesRegex(ValueError,"PRIVATE_EVIDENCE_MUST_BE_OUTSIDE_REPOSITORY"):
                    _write_private_create_only(repo_root/"research"/"leak.json",{"state":"PAPER"})

    def test_forged_archive_denominator_rejected_even_with_matching_hash(self):
        with TemporaryDirectory() as d:
            m,final=inputs(d)
            obj=freeze_player_forecasts(m,now=NOW)
            obj["frozen_rows"]=0
            raw=(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
            p=Path(d)/"frozen.json"
            p.write_bytes(raw)
            h="sha256:"+sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError,"FROZEN_ARCHIVE_DENOMINATOR_INVALID"):
                grade_frozen_capture(grade_request(d,h,final),now=AFTER)

    def test_result_stat_case_and_whitespace_normalized(self):
        with TemporaryDirectory() as d:
            m,final=inputs(d,actual_value="8")
            obj=freeze_player_forecasts(m,now=NOW)
            h=_write_private_create_only(Path(d)/"frozen.json",obj)
            raw=csv_bytes([{"event_id":"GAME1","player_id":"P1",
                           "team_id":"BUF","stat":" rec_yds ","actual":"8"}],
                           ("event_id","player_id","team_id","stat","actual"))
            final.update(write(d,"actual_normalized.csv",raw))
            out=grade_frozen_capture(grade_request(d,h,final),now=AFTER)
            self.assertEqual(out["graded_rows"],1)
            self.assertEqual(out["results"][0]["actual"],8)

    def test_duplicate_json_manifest_key_fails(self):
        from sportsedge.validation.forward_player_evidence import _strict_json
        with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
            _strict_json(b'{"schema":"x","schema":"y"}')

    def test_cli_one_canonical_event_freeze_across_different_output_names(self):
        with TemporaryDirectory() as d:
            root=Path(d)/"shared-registry"
            root.mkdir(mode=0o700)
            m,_=inputs(d)
            req=Path(d)/"freeze-request.json"
            req.write_text(json.dumps(m))
            canonical=root/"freeze-2026-w11-GAME1.json"
            other=Path(d)/"alternate-folder"
            other.mkdir(mode=0o700)
            with patch("sportsedge.validation.forward_player_evidence._clock",
                       return_value=NOW):
                with self.assertRaisesRegex(ValueError,"NONCANONICAL_FREEZE_OR_GRADE_OUTPUT_REFUSED"):
                    main(["freeze",str(req),str(other/"also-frozen.json"),
                          "--registry-root",str(root)])
                self.assertFalse((other/"also-frozen.json").exists())
                self.assertEqual(main(["freeze",str(req),str(canonical),
                                       "--registry-root",str(root)]),0)
                original=canonical.read_bytes()
                self.assertEqual(canonical.stat().st_mode & 0o777,0o600)
                with self.assertRaises(FileExistsError):
                    main(["freeze",str(req),str(canonical),
                          "--registry-root",str(root)])
                with self.assertRaisesRegex(ValueError,"NONCANONICAL_FREEZE_OR_GRADE_OUTPUT_REFUSED"):
                    main(["freeze",str(req),str(other/"second.json"),
                          "--registry-root",str(root)])
            self.assertEqual(canonical.read_bytes(),original)

    def test_cli_grade_only_original_canonical_freeze_once(self):
        with TemporaryDirectory() as d:
            root=Path(d)/"shared-registry"
            root.mkdir(mode=0o700)
            m,final=inputs(d)
            freeze_path=root/"freeze-2026-w11-GAME1.json"
            freeze_request=Path(d)/"freeze-request.json"
            freeze_request.write_text(json.dumps(m))
            with patch("sportsedge.validation.forward_player_evidence._clock",
                       return_value=NOW):
                main(["freeze",str(freeze_request),str(freeze_path),
                      "--registry-root",str(root)])
            capture_sha="sha256:"+sha256(freeze_path.read_bytes()).hexdigest()
            g=grade_request(d,capture_sha,final)
            g["frozen_capture_path"]=str(freeze_path)
            grade_path=root/f"grade-2026-w11-GAME1-{capture_sha[7:]}.json"
            grade_request_path=Path(d)/"grade-request.json"
            grade_request_path.write_text(json.dumps(g))
            with patch("sportsedge.validation.forward_player_evidence._clock",
                       return_value=AFTER):
                self.assertEqual(main(["grade",str(grade_request_path),str(grade_path),
                                       "--registry-root",str(root)]),0)
                original=grade_path.read_bytes()
                self.assertEqual(json.loads(original)["graded_rows"],1)
                self.assertEqual(grade_path.stat().st_mode & 0o777,0o600)
                with self.assertRaises(FileExistsError):
                    main(["grade",str(grade_request_path),str(grade_path),
                          "--registry-root",str(root)])
                with self.assertRaisesRegex(ValueError,"NONCANONICAL_FREEZE_OR_GRADE_OUTPUT_REFUSED"):
                    main(["grade",str(grade_request_path),str(Path(d)/"cherrypicked.json"),
                          "--registry-root",str(root)])
            self.assertEqual(grade_path.read_bytes(),original)

    def test_grade_duplicate_source_different_name_does_not_bypass_unique_freeze(self):
        with TemporaryDirectory() as d:
            root=Path(d)/"shared-registry"
            root.mkdir(mode=0o700)
            m,final=inputs(d)
            frozen=freeze_player_forecasts(m,now=NOW)
            original=root/"freeze-2026-w11-GAME1.json"
            sha=_write_private_create_only(original,frozen)
            alternate=root/"freeze-2026-w11-GAME1-cherrypicked.json"
            alternate.write_bytes(original.read_bytes())
            alternate.chmod(0o600)
            g=grade_request(d,sha,final)
            g["frozen_capture_path"]=str(alternate)
            rq=Path(d)/"grade-request.json"
            rq.write_text(json.dumps(g))
            with patch("sportsedge.validation.forward_player_evidence._clock",
                       return_value=AFTER):
                with self.assertRaisesRegex(ValueError,"GRADE_FROZEN_SOURCE_NOT_IN_CANONICAL_REGISTRY"):
                    main(["grade",str(rq),str(root/"any.json"),
                          "--registry-root",str(root)])
            self.assertFalse((root/"any.json").exists())

    def test_registry_missing_world_readable_and_symlink_roots_refused(self):
        with TemporaryDirectory() as d:
            root=Path(d)/"trusted"
            with self.assertRaisesRegex(ValueError,"TRUSTED_REGISTRY_DIRECTORY_MISSING"):
                _trusted_registry_root(str(root))
            root.mkdir(mode=0o700)
            self.assertEqual(_trusted_registry_root(str(root)),root)
            root.chmod(0o755)
            with self.assertRaisesRegex(ValueError,"TRUSTED_REGISTRY_REQUIRES_OWNER_DIRECTORY_0700"):
                _trusted_registry_root(str(root))
            root.chmod(0o700)
            alias=Path(d)/"symlink-root"
            alias.symlink_to(root,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"TRUSTED_REGISTRY_OUTSIDE_PUBLIC_REPO_NO_SYMLINKS"):
                _trusted_registry_root(str(alias))

    def test_two_independent_processes_exclusive_create_one_physical_freeze(self):
        # Both workers contend for EXACTLY the same canonical event path,
        # rather than choosing alternate filenames/directories.
        with TemporaryDirectory() as d:
            root=Path(d)/"trusted"
            root.mkdir(mode=0o700)
            target=root/"freeze-2026-w11-GAME1.json"
            script=(
                "import sys; "
                "from sportsedge.validation.forward_player_evidence import _write_private_create_only; "
                "_write_private_create_only(sys.argv[1],"
                "{'schema':'sportsedge-nfl-player-forward-freeze-v2','state':'PAPER_0U','approved_stake_u':0})"
            )
            repo_root=Path(__file__).resolve().parents[2]
            workers=[subprocess.Popen(
                        [sys.executable,"-c",script,str(target)],
                        cwd=str(repo_root),stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
                     for _ in range(2)]
            ended=[w.communicate(timeout=15) for w in workers]
            codes=[w.returncode for w in workers]
            self.assertEqual(sorted(codes),[0,1],ended)
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            self.assertEqual(json.loads(target.read_bytes())["approved_stake_u"],0)
            self.assertTrue(any(b"FileExistsError" in err for _,err in ended))

    def test_registry_path_identity_stays_stable_on_same_event(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            frozen={"event_id":"GAME1","season":2026,"week":11}
            self.assertEqual(_freeze_registry_path(root,frozen).name,
                             "freeze-2026-w11-GAME1.json")
            self.assertEqual(_grade_registry_path(root,frozen,H).name,
                             f"grade-2026-w11-GAME1-{H[7:]}.json")
            with self.assertRaisesRegex(ValueError,"INVALID_STABLE_ID"):
                _freeze_registry_path(root,dict(frozen,event_id="../fake"))


if __name__ == "__main__":
    unittest.main()
