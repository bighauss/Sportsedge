"""Offline synthetic ESPN final-source evidence regressions: all five sports."""
import copy
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from sportsedge.validation import espn_final_evidence as f

KICK="2026-11-21T18:00:00Z"
CAP="2026-11-21T22:00:00Z"
EV="401234567"
H="101"
A="202"


def summary(sport="NFL", home_score=None, away_score=None, extras=0,
            with_players=True):
    n=9 if sport=="MLB" else (2 if sport=="CBB" else 4)
    hs=[2]*n
    aw=[1]*n
    if extras:
        hs.extend([1]*extras)
        aw.extend([0]*extras)
    if home_score is not None: hs[0]=home_score
    if away_score is not None: aw[0]=away_score
    def side(tid,where,seq):
        return {"homeAway":where,"team":{"id":tid},
                "score":str(sum(seq)),
                "linescores":[{"value":x,"period":i} for i,x in enumerate(seq,1)]}
    data={"header":{"id":EV,"competitions":[{
        "id":EV, "date":KICK,
        "status":{"type":{"completed":True,"name":"STATUS_FINAL"}},
        "competitors":[side(H,"home",hs),side(A,"away",aw)]
    }]}}
    if with_players:
        if sport in ("NFL","CFB"):
            stats=[{
                "name":"passing", "labels":["C/ATT","YDS","TD","INT"],
                "athletes":[{"athlete":{"id":"301"},"stats":["21/32","248","2","1"]}]},
                {"name":"receiving","labels":["REC","YDS"],
                "athletes":[{"athlete":{"id":"302"},"stats":["5","91"]}]}]
        elif sport in ("NBA","CBB"):
            stats=[{"name":"starters","labels":["PTS","REB","AST","3PT"],
                    "athletes":[{"athlete":{"id":"301"},"stats":["23","7","4","3-7"]}]}]
        else:
            stats=[{"name":"batting","labels":["H","RBI"],
                    "athletes":[{"athlete":{"id":"301"},"stats":["2","1"]}]}]
        data["boxscore"]={"players":[{"team":{"id":H},"statistics":stats}]}
    return data


def run(data,**kw):
    settings=dict(event_id=EV,sport="NFL",home_espn_id=H,
                  away_espn_id=A,captured_utc=CAP,kickoff_utc=KICK)
    settings.update(kw)
    return f.inspect(json.dumps(data).encode(),**settings)


class ESPNIntakeTests(unittest.TestCase):
    def test_nfl_four_quarters_and_partial_player_stats(self):
        r=run(summary())
        c=r["candidate"]
        self.assertEqual(c["periods"]["Q1"],[2,1])
        self.assertEqual(c["periods"]["Q4"],[2,1])
        self.assertEqual(c["player_stats"]["301"]["PASS_YDS"],248)
        self.assertEqual(c["player_stats"]["301"]["COMPLETIONS"],21)
        self.assertEqual(c["player_stats"]["301"]["PASS_ATT"],32)
        self.assertEqual(c["player_stats"]["302"]["RECEPTIONS"],5)
        self.assertFalse(c["events_complete"])
        self.assertEqual(c["player_period_stats"],{})
        self.assertFalse(r["provider_publication_authenticated"])
        self.assertEqual(r["official_counted"],0)
        self.assertEqual(r["price_evidence_status"],"NOT_CHECKED")

    def test_cfb_has_quarters_not_fake_1h_player_props(self):
        r=run(summary("CFB"),sport="CFB")
        self.assertEqual(set(r["candidate"]["periods"]),{"Q1","Q2","Q3","Q4"})
        self.assertEqual(r["candidate"]["player_stats"]["301"]["PASS_TDS"],2)
        self.assertFalse(r["candidate"]["events_complete"])

    def test_cbb_halves_and_only_explicit_players(self):
        r=run(summary("CBB"),sport="CBB")
        c=r["candidate"]
        self.assertEqual(set(c["periods"]),{"H1","H2"})
        self.assertEqual(c["player_stats"]["301"]["POINTS"],23)
        self.assertEqual(c["player_stats"]["301"]["3PM"],3)
        self.assertEqual(c["player_stats"]["301"]["ASSISTS"],4)
        self.assertNotIn("9999",c["player_stats"])
        self.assertNotIn("PRA",c["player_stats"]["301"])

    def test_nba_overtime_accumulates_only_known_splits(self):
        r=run(summary("NBA",extras=2),sport="NBA")
        self.assertEqual(r["candidate"]["periods"]["OT"],[2,0])
        self.assertEqual(r["candidate"]["player_stats"]["301"]["REBOUNDS"],7)

    def test_mlb_innings_and_extras_no_pitching_props_fabricated(self):
        r=run(summary("MLB",extras=2),sport="MLB")
        self.assertEqual(r["candidate"]["periods"]["I1"],[2,1])
        self.assertEqual(r["candidate"]["periods"]["I9"],[2,1])
        self.assertEqual(r["candidate"]["periods"]["EXTRA"],[2,0])
        self.assertEqual(r["candidate"]["roster_ids"],[])
        self.assertEqual(r["candidate"]["player_stats"],{})
        self.assertIn("MLB_PLAYER_SCHEMA_NOT_ADMITTED",r["player_stat_warnings"])

    def test_no_stats_means_missing_not_healthy_or_zero(self):
        r=run(summary(with_players=False))
        self.assertEqual(r["candidate"]["player_stats"],{})
        self.assertIn("PLAYER_BOX_SCORE_MISSING",r["player_stat_warnings"])

    def test_nonfinal_or_incomplete_status_blocks(self):
        x=summary()
        x["header"]["competitions"][0]["status"]["type"]["completed"]=False
        with self.assertRaisesRegex(f.Reject,"FINAL_STATUS_NOT_CONFIRMED"):run(x)

    def test_espn_competition_identity_and_order(self):
        x=summary()
        with self.assertRaisesRegex(f.Reject,"EVENT_ID_MISMATCH"):
            run(x,event_id="4444")
        x["header"]["competitions"][0]["competitors"][0]["homeAway"]="away"
        with self.assertRaisesRegex(f.Reject,"DUPLICATE_HOME_AWAY"):run(x)
        x=summary()
        with self.assertRaisesRegex(f.Reject,"TEAM_ID_OR_SIDE_MISMATCH"):
            run(x,home_espn_id="333")

    def test_bad_score_total_or_missing_period_refused(self):
        x=summary()
        x["header"]["competitions"][0]["competitors"][0]["score"]="99"
        with self.assertRaisesRegex(f.Reject,"HOME_PERIOD_SUM_NOT_FINAL"):run(x)
        x=summary()
        x["header"]["competitions"][0]["competitors"][0]["linescores"].pop()
        with self.assertRaisesRegex(f.Reject,"PERIOD_LINESCORES_MISSING_OR_MISMATCH"):run(x)

    def test_bad_period_index_refused(self):
        x=summary()
        x["header"]["competitions"][0]["competitors"][0]["linescores"][0]["period"]=2
        with self.assertRaisesRegex(f.Reject,"PERIOD_ORDER_MISMATCH"):run(x)

    def test_invalid_cbb_quarter_count_refused(self):
        x=summary("CBB")
        x["header"]["competitions"][0]["competitors"][0]["linescores"].pop()
        x["header"]["competitions"][0]["competitors"][0]["score"]="2"
        x["header"]["competitions"][0]["competitors"][1]["linescores"].pop()
        x["header"]["competitions"][0]["competitors"][1]["score"]="1"
        with self.assertRaisesRegex(f.Reject,"PERIOD_COUNT_INCOMPLETE"):run(x,sport="CBB")

    def test_capture_before_kickoff_refused(self):
        with self.assertRaisesRegex(f.Reject,"CAPTURE_NOT_POSTGAME"):
            run(summary(),captured_utc="2026-11-21T17:59:59Z")

    def test_missing_or_invalid_source_kickoff(self):
        for fields in ({}, {"date": None}, {"date": ""}, {"date": 123}, {"date": "2026-11-21T18:00:00"}):
            with self.subTest(fields=fields):
                doc = summary()
                comp = doc["header"]["competitions"][0]
                del comp["date"]
                comp.update(fields)
                with self.assertRaisesRegex(f.Reject, "ESPN_KICKOFF_INVALID"):
                    run(doc)

    def test_kickoff_identity_mismatch(self):
        x=summary()
        x["header"]["competitions"][0]["date"]="2026-11-21T19:00:00Z"
        with self.assertRaisesRegex(f.Reject,"KICKOFF_IDENTITY_MISMATCH"):run(x)

    def test_original_duplicate_json_keys_refused(self):
        raw=b'{"header":{},"header":{}}'
        with self.assertRaisesRegex(f.Reject,"INVALID_OR_DUPLICATE_SOURCE_JSON"):
            f.inspect(raw,event_id=EV,sport="NFL",home_espn_id=H,away_espn_id=A,
                      captured_utc=CAP,kickoff_utc=KICK)

    def test_wrong_roster_player_id_never_creates_stat(self):
        x=summary()
        player=x["boxscore"]["players"][0]["statistics"][0]["athletes"][0]
        player["athlete"]["id"]="ABCD"
        r=run(x)
        self.assertNotIn("ABCD",r["candidate"]["player_stats"])
        self.assertIn("PLAYER_ID_INVALID",r["player_stat_warnings"])

    def test_missing_player_stat_is_not_zero(self):
        x=summary()
        x["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"][1]="--"
        r=run(x)
        self.assertNotIn("PASS_YDS",r["candidate"]["player_stats"]["301"])
        self.assertIn("MISSING_OR_AMBIGUOUS_STAT:PASS_YDS",r["player_stat_warnings"])

    def test_malformed_ratio_not_fake_3pt(self):
        x=summary("NBA")
        x["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"][3]="abc"
        r=run(x,sport="NBA")
        self.assertNotIn("3PM",r["candidate"]["player_stats"]["301"])
        self.assertIn("UNPARSEABLE_3PT_RATIO",r["player_stat_warnings"])

    def test_data_bytes_hash_and_private_staged_bundle(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            root.chmod(0o700)
            raw=json.dumps(summary()).encode()
            r=f.inspect(raw,event_id=EV,sport="NFL",home_espn_id=H,away_espn_id=A,
                        captured_utc=CAP,kickoff_utc=KICK)
            receipt=f.save(raw,r,root/"new",source_url="synthetic://local",import_kind="import")
            self.assertEqual((root/"new"/"original_espn_summary.json").read_bytes(),raw)
            self.assertEqual(receipt["source_original_sha256"],hashlib.sha256(raw).hexdigest())
            self.assertEqual((root/"new"/"original_espn_summary.json").stat().st_mode&0o777,0o600)
            self.assertFalse(receipt["provider_publication_authenticated"])
            with self.assertRaises(FileExistsError):
                f.save(raw,f.inspect(raw,event_id=EV,sport="NFL",home_espn_id=H,
                       away_espn_id=A,captured_utc=CAP,kickoff_utc=KICK),
                       root/"new",source_url="synthetic://local",import_kind="import")

    def test_no_redirect_transport(self):
        with self.assertRaisesRegex(f.Reject,"EVENT_NOT_EXACT_ESPN_ID"):
            f._fetch("NFL","x/../../../etc")
        self.assertIsNone(f.NoRedirect().redirect_request(None,None,302,"Found",{}, "https://bad.test"))

    def test_missing_player_roster_does_not_auto_zero(self):
        x=summary()
        x["boxscore"]["players"]=[]
        r=run(x)
        self.assertEqual(r["candidate"]["player_stats"],{})
        self.assertNotIn("301",r["candidate"]["roster_ids"])


    def test_public_or_group_readable_output_is_blocked(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            root.chmod(0o755)
            raw=json.dumps(summary()).encode()
            r=run(summary())
            with self.assertRaisesRegex(f.Reject,"OUTPUT_PARENT_NOT_OWNER_PRIVATE"):
                f.save(raw,r,root/"unsafe",source_url="synthetic",import_kind="import")
            self.assertFalse((root/"unsafe").exists())

    def test_cross_team_athlete_id_is_quarantined(self):
        x=summary()
        copied=copy.deepcopy(x["boxscore"]["players"][0])
        copied["team"]["id"]=A
        x["boxscore"]["players"].append(copied)
        r=run(x)
        self.assertNotIn("301",r["candidate"]["player_stats"])
        self.assertNotIn("301",r["candidate"]["roster_ids"])
        self.assertIn("PLAYER_ID_BELONGS_TO_MULTIPLE_TEAMS",r["player_stat_warnings"])

    def test_conflicting_player_stat_is_quarantined(self):
        x=summary()
        first=x["boxscore"]["players"][0]["statistics"][0]
        duplicated=copy.deepcopy(first)
        duplicated["athletes"][0]["stats"][1]="300"
        x["boxscore"]["players"][0]["statistics"].append(duplicated)
        r=run(x)
        self.assertNotIn("PASS_YDS",r["candidate"]["player_stats"]["301"])
        self.assertIn("CONFLICTING_PLAYER_STAT_VALUES",r["player_stat_warnings"])



    def test_original_response_modified_after_inspection_refused(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            root.chmod(0o700)
            raw=json.dumps(summary()).encode()
            report=run(summary())
            # Different byte layout still the same JSON object: must be blocked.
            changed=json.dumps(summary(),indent=4).encode()
            with self.assertRaisesRegex(f.Reject,"SOURCE_RECEIPT_RAW_BYTES_MISMATCH"):
                f.save(changed,report,root/"no",source_url="synthetic",import_kind="import")
            self.assertFalse((root/"no").exists())


if __name__=="__main__":
    unittest.main(verbosity=2)
