"""Synthetic point-in-time manifest adversarial tests. Claimed times are fake."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sportsedge.markets.pit_source_manifest import (
    MANIFEST_VERSION, verify_model_feature_manifest, _inputs_to_check
)

D=datetime(2026,11,15,17,0,0,tzinfo=timezone.utc)


def fixture(paths, *, sport="CBB", event_id="C1"):
    files=[]
    for role,path in _inputs_to_check(paths).items():
        files.append({
            "role":role,
            "path":str(path),
            "raw_sha256":"sha256:"+sha256(path.read_bytes()).hexdigest(),
            "source_id":{"CBB":"CBB_HOOPR","NFL":"NFLVERSE_WEEKLY",
                         "CFB":"CFB_DATA","NBA":"NBA_STATS",
                         "MLB":"MLB_STATCAST"}[sport],
            "data_through_utc":(D-timedelta(days=4)).isoformat(),
            "observed_at_utc":(D-timedelta(hours=3)).isoformat(),
            "captured_at_utc":(D-timedelta(hours=2)).isoformat(),
        })
    return {"version":MANIFEST_VERSION,"sport":sport,"event_id":event_id,
            "forecast_asof_utc":D.isoformat(),
            "model_trained_until_utc":(D-timedelta(days=1)).isoformat(),
            "files":files}


class TestPITFileManifest(unittest.TestCase):
    def test_exact_feature_file_and_capture_time_accepted_as_research_only(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"teams.csv";p.write_text("team,rating\nA,1\n")
            files={"teams":str(p)}
            r=verify_model_feature_manifest(
                fixture(files),files,sport="CBB",event_id="C1",
                forecast_asof_utc=D)
            self.assertEqual(r.file_count,1)
            self.assertFalse(r.independently_authenticated)
            self.assertEqual((r.official_counted,r.approved_stake_u),(0,0))
            self.assertIn("RESEARCH_ONLY",r.status)

    def test_manifest_without_entire_source_list_fails(self):
        with TemporaryDirectory() as d:
            a=Path(d)/"teams.csv";a.write_text("team\nA\n")
            b=Path(d)/"players.csv";b.write_text("player\nP\n")
            files={"teams":str(a),"players":str(b)}
            m=fixture(files);m["files"].pop()
            with self.assertRaisesRegex(ValueError,"PIT_FEATURE_ROLE_COVERAGE_MISMATCH"):
                verify_model_feature_manifest(m,files,sport="CBB",event_id="C1",
                                              forecast_asof_utc=D)

    def test_tampered_source_bytes_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"teams.csv";p.write_text("team\nA\n")
            files={"teams":str(p)};m=fixture(files)
            p.write_text("team\nB\n")
            with self.assertRaisesRegex(ValueError,"PIT_FEATURE_RAW_HASH_MISMATCH"):
                verify_model_feature_manifest(m,files,sport="CBB",event_id="C1",
                                              forecast_asof_utc=D)

    def test_future_feature_capture_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"teams.csv";p.write_text("team\nA\n")
            files={"teams":str(p)};m=fixture(files)
            m["files"][0]["captured_at_utc"]=(D+timedelta(seconds=1)).isoformat()
            with self.assertRaisesRegex(ValueError,"PIT_FEATURE_LOOKAHEAD_OR_BAD_CAPTURE_ORDER"):
                verify_model_feature_manifest(m,files,sport="CBB",event_id="C1",
                                              forecast_asof_utc=D)

    def test_future_data_through_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"teams.csv";p.write_text("team\nA\n")
            files={"teams":str(p)};m=fixture(files)
            m["files"][0]["data_through_utc"]=(D+timedelta(days=2)).isoformat()
            with self.assertRaisesRegex(ValueError,"PIT_FEATURE_LOOKAHEAD_OR_BAD_CAPTURE_ORDER"):
                verify_model_feature_manifest(m,files,sport="CBB",event_id="C1",
                                              forecast_asof_utc=D)

    def test_model_fit_until_forecast_time_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"teams.csv";p.write_text("team\nA\n")
            files={"teams":str(p)};m=fixture(files)
            m["model_trained_until_utc"]=D.isoformat()
            with self.assertRaisesRegex(ValueError,"PIT_MODEL_TRAINED_ON_EVALUATION"):
                verify_model_feature_manifest(m,files,sport="CBB",event_id="C1",
                                              forecast_asof_utc=D)

    def test_forged_certification_flag_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"teams.csv";p.write_text("team\nA\n")
            files={"teams":str(p)};m=fixture(files)
            with self.assertRaisesRegex(ValueError,"CALLER_CANNOT_ATTEST_INDEPENDENT"):
                verify_model_feature_manifest(m,files,sport="CBB",event_id="C1",
                    forecast_asof_utc=D,independent_source_verified=True)

    def test_unapproved_model_odd_price_path_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"odds.csv";p.write_text("odds\n-110\n")
            with self.assertRaisesRegex(ValueError,"BOOKMAKER_FIELD_IN_MODEL_FEATURE_PATHS"):
                _inputs_to_check({"odds":str(p)})
            with self.assertRaisesRegex(ValueError,"BOOKMAKER_FILE_USED_AS_MODEL_FEATURE"):
                _inputs_to_check({"teams":str(p)})

    def test_unverified_cross_sport_registry_source_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"teams.csv";p.write_text("team\nA\n")
            files={"teams":str(p)};m=fixture(files)
            m["files"][0]["source_id"]="NBA_STATS"
            with self.assertRaisesRegex(ValueError,"PIT_SOURCE_DIFFERENT_SPORT"):
                verify_model_feature_manifest(m,files,sport="CBB",event_id="C1",
                                              forecast_asof_utc=D)

    def test_duplicate_feature_role_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"teams.csv";p.write_text("team\nA\n")
            files={"teams":str(p)};m=fixture(files)
            m["files"].append(deepcopy(m["files"][0]))
            with self.assertRaisesRegex(ValueError,"PIT_FEATURE_ROLE_REUSED"):
                verify_model_feature_manifest(m,files,sport="CBB",event_id="C1",
                                              forecast_asof_utc=D)

    def test_offline_mlb_directory_excludes_bookmaker_rows(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            (root/"teams.csv").write_text("team,runs\nA,4\n")
            (root/"odds.csv").write_text("line,price\n4.5,-110\n")
            files={"folder":str(root)}
            m=fixture(files,sport="MLB",event_id="G1")
            r=verify_model_feature_manifest(m,files,sport="MLB",event_id="G1",
                                             forecast_asof_utc=D)
            self.assertEqual(r.file_count,1)
            self.assertEqual(r.verified_roles,("folder/teams.csv",))

    def test_local_symlink_feature_is_refused(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"source.csv";p.write_text("team\nA\n")
            link=Path(d)/"link.csv";link.symlink_to(p)
            with self.assertRaisesRegex(ValueError,"PIT_SYMLINK_FEATURE_REFUSED"):
                _inputs_to_check({"teams":str(link)})


if __name__=="__main__":
    unittest.main()
