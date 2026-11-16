"""Offline synthetic Torvik-to-CBBD identity and pre-tip research bridge tests."""
import copy
import csv
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cbbd_prospective_capture import capture_games, Hold
from torvik_cbbd_pregame_bridge import archive_csv, project_scheduled

SCHEDULE_TIME = datetime(2026,11,15,17,0,tzinfo=timezone.utc)
DATA_TIME = datetime(2026,11,15,17,30,tzinfo=timezone.utc)
MAP_TIME = datetime(2026,11,15,17,40,tzinfo=timezone.utc)
FREEZE = datetime(2026,11,15,18,0,tzinfo=timezone.utc)


def schedule(game_id=10, **kwargs):
    r={"id":game_id,"season":2027,"startDate":"2026-11-15T20:00:00Z",
       "startTimeTbd":False,"status":"scheduled",
       "homeTeamId":101,"awayTeamId":202,
       "neutralSite":False,"homePoints":None,"awayPoints":None}
    r.update(kwargs)
    return r


def raw_ratings(n=300):
    rows=[]
    for i in range(n):
        rows.append({"team":f"Team{i}", "adj_o":str(102+i/100),
                     "adj_d":str(98+i/100), "adj_tempo":str(67+i/300),
                     "date":"20261115"})
    return rows


def write_csv(path, rows):
    with Path(path).open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fake_fetch(rows):
    raw=json.dumps(rows).encode()
    return lambda req, cap: (raw, "application/json", req.full_url)


def fixtures(tmp, *, games=None, ratings=None, mapping=None, home_court=None):
    private=Path(tmp)
    captured=capture_games(
        season=2027,start_utc="2026-11-15T00:00:00Z",
        end_utc="2026-11-15T23:59:59Z",private_dir=private/"provider",
        key="fake-fixture-key",transport=fake_fetch(games or [schedule()]),
        clock=lambda:SCHEDULE_TIME)
    samples={
        "ratings":("TORVIK_RATINGS", ratings or raw_ratings(),DATA_TIME),
        "map":("CBBD_ID_CROSSWALK",mapping or [
            {"cbbd_id":"101","torvik_team":"Team1"},
            {"cbbd_id":"202","torvik_team":"Team2"}],MAP_TIME),
        "hca":("HCA_RESEARCH", home_court or [
            {"cbbd_id":"101","home_court_points":"3.36"}],MAP_TIME),
    }
    vals={"schedule_raw":captured["raw_path"],
          "schedule_manifest":captured["manifest_path"]}
    for label,(kind,rows,when) in samples.items():
        original=private/(label+"_input.csv")
        write_csv(original,rows)
        evidence=archive_csv(source_path=original,private_dir=private/"snapshots",
                             kind=kind,season=2027,clock=lambda t=when:t)
        key = ("ratings" if label=="ratings" else label)
        vals[key+"_raw"]=evidence["raw_path"]
        vals[key+"_manifest"]=evidence["manifest_path"]
    vals["output_path"]=private/"new_board.json"
    vals["now"]=FREEZE
    return vals


class TorvikCbddBridgeTests(unittest.TestCase):
    def test_full_prospective_projection_is_score_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp)
            r=project_scheduled(**kw)
            self.assertEqual(r["input_rows"],1)
            self.assertEqual(r["projected_rows"],1)
            x=r["results"][0]
            self.assertEqual(x["game_id"],"10")
            self.assertEqual(x["home_team_id"],"101")
            self.assertEqual(x["away_team_id"],"202")
            self.assertEqual(x["status"],"PAPER_NON_COUNTED_UNCALIBRATED")
            self.assertAlmostEqual(x["total"],x["home_points"]+x["away_points"])
            self.assertEqual(x["stake_u"],0)
            self.assertIsNone(x["ml_probability"])
            self.assertIsNone(x["expected_value"])
            self.assertEqual(r["status"],"CBB_POINT_IN_TIME_RESEARCH_ONLY_UNAUTHENTICATED_PAPER_0U")

    def test_explicit_missing_home_court_is_blocked_not_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp,home_court=[{"cbbd_id":"999","home_court_points":"2.5"}])
            r=project_scheduled(**kw)
            self.assertEqual(r["projected_rows"],0)
            self.assertIn("HCA_INPUT_MISSING",r["results"][0]["reason"])

    def test_neutral_requires_no_home_court(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp,games=[schedule(neutralSite=True)],
                        home_court=[{"cbbd_id":"999","home_court_points":"2.5"}])
            r=project_scheduled(**kw)
            self.assertEqual(r["projected_rows"],1)
            self.assertNotIn("hca",r["results"][0]["source_clock_consistent_not_authenticated"])

    def test_fuzzy_miami_alias_never_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp,mapping=[
                {"cbbd_id":"101","torvik_team":"Team1"},
                {"cbbd_id":"999","torvik_team":"Team2"}])
            r=project_scheduled(**kw)
            self.assertIn("EXACT_CBBD_TO_TORVIK_MAPPING_MISSING",r["results"][0]["reason"])

    def test_crosswalk_collision_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp,mapping=[
                {"cbbd_id":"101","torvik_team":"Team1"},
                {"cbbd_id":"202","torvik_team":"Team1"}])
            with self.assertRaisesRegex(Hold,"CROSSWALK_NOT_BIJECTIVE"):
                project_scheduled(**kw)

    def test_too_small_torvik_universe_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_file=Path(tmp)/"ratings.csv"
            write_csv(input_file,raw_ratings(15))
            with self.assertRaisesRegex(Hold,"INCOMPLETE_TORVIK_D1_TEAM_UNIVERSE"):
                archive_csv(source_path=input_file,private_dir=Path(tmp)/"archived",
                            kind="TORVIK_RATINGS",season=2027,clock=lambda:DATA_TIME)

    def test_duplicate_games_quarantine_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp,games=[schedule(10),schedule(10),schedule(11)])
            r=project_scheduled(**kw)
            self.assertEqual(r["input_rows"],3)
            self.assertEqual([x["status"] for x in r["results"]],
                             ["BLOCKED","BLOCKED","PAPER_NON_COUNTED_UNCALIBRATED"])
            self.assertIn("DUPLICATE_CBBD_EVENT",r["results"][0]["reason"])

    def test_in_progress_or_late_frozen_game_kept_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp,games=[
                schedule(10,status="in_progress"),
                schedule(11,startDate="2026-11-15T16:00:00Z"),
                schedule(12)])
            r=project_scheduled(**kw)
            self.assertEqual(r["input_rows"],3)
            self.assertEqual(r["projected_rows"],1)
            self.assertIn("NOT_PREGAME_SCHEDULED",r["results"][0]["reason"])
            self.assertIn("PREGAME_FREEZE_TOO_LATE",r["results"][1]["reason"])

    def test_source_captured_after_model_freeze_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp)
            kw["now"]=datetime(2026,11,15,17,15,tzinfo=timezone.utc)
            with self.assertRaisesRegex(Hold,"SOURCE_CAPTURE_IS_AFTER_MODEL_FREEZE"):
                project_scheduled(**kw)
            self.assertFalse(Path(kw["output_path"]).exists())

    def test_stale_rating_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp)
            kw["now"]=datetime(2026,11,16,18,0,tzinfo=timezone.utc)
            with self.assertRaisesRegex(Hold,"TOO_STALE"):
                project_scheduled(**kw)
            self.assertFalse(Path(kw["output_path"]).exists())

    def test_original_csv_hash_mismatch_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp)
            p=Path(kw["ratings_raw"])
            p.write_bytes(p.read_bytes()+b" ")
            with self.assertRaisesRegex(Hold,"CSV_ORIGINAL_BYTE_HASH_MISMATCH"):
                project_scheduled(**kw)

    def test_create_only_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp)
            project_scheduled(**kw)
            with self.assertRaisesRegex(FileExistsError,"CREATE_ONLY"):
                project_scheduled(**kw)

    def test_date_label_cannot_be_in_future(self):
        with tempfile.TemporaryDirectory() as tmp:
            ratings=raw_ratings()
            ratings[4]["date"]="20261116"
            path=Path(tmp)/"input.csv"
            write_csv(path,ratings)
            with self.assertRaisesRegex(Hold,"TORVIK_DATE_AFTER_CAPTURE"):
                archive_csv(source_path=path,private_dir=Path(tmp)/"archived",
                            kind="TORVIK_RATINGS",season=2027,clock=lambda:DATA_TIME)

    def test_archive_rejects_duplicate_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"dup.csv"
            p.write_text("team,adj_o,adj_o,adj_d,adj_tempo\nTeam1,110,111,100,67\n")
            with self.assertRaisesRegex(Hold,"DUPLICATE_OR_INVALID_CSV_HEADERS"):
                archive_csv(source_path=p,private_dir=Path(tmp)/"stored",
                            kind="TORVIK_RATINGS",season=2027,clock=lambda:DATA_TIME)

    def test_crosswalk_refuses_unmatched_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp,mapping=[
                {"cbbd_id":"101","torvik_team":"Team1"},
                {"cbbd_id":"202","torvik_team":"Miami (OH)"}])
            with self.assertRaisesRegex(Hold,"CROSSWALK_TARGET_NOT_IN_FROZEN_RATINGS"):
                project_scheduled(**kw)

    def test_archives_creates_exact_sha_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw=fixtures(tmp)
            for label in ("ratings","map","hca"):
                raw=Path(kw[label+"_raw"]).read_bytes()
                manifest=json.loads(Path(kw[label+"_manifest"]).read_text())
                self.assertEqual(manifest["source_sha256"],hashlib.sha256(raw).hexdigest())
                self.assertEqual(manifest["status"],"RESEARCH_ONLY_PAPER_0U")
                self.assertIn("NOT_PUBLISHER_ATTESTATION",manifest["publication_basis"])


if __name__=="__main__":
    unittest.main()
