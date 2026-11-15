"""Synthetic tests for actual nflverse 2026 weekly player-stat adapter."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import build_weekly_game_inputs as weekly
from build_game_inputs import Blocked


class WeeklyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.players={}
        self.teams={}
        self.pids={}
        for tm in ("PIT","CIN"):
            qb,rb,wr=(tm+"_QB",tm+"_RB",tm+"_WR")
            self.teams[tm]={"qb":qb,"fum_lost":.3,"fga":1.4,
                            "fg50":.8,"fg40":.9,"fg_short":.95,
                            "dst":{"sacks":2,"frec":.2,"td":.05}}
            for name,pos in ((qb,"QB"),(rb,"RB"),(wr,"WR")):
                self.players[name]={"team":tm,"pos":pos,"p_active":1}
                self.pids[name]=tm+"-"+pos
        self.cfg={"tag":"TEST_PIT_CIN","teams":self.teams,"players":self.players,
                  "salary_file":"owner.csv","market":{"total":48.0}}
        self.template=self.store("template.json",json.dumps(self.cfg))
        roster_path=self.root/"roster.csv"
        with roster_path.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=("player_name","team","gsis_id","position"))
            w.writeheader()
            for name,meta in self.players.items():
                w.writerow(dict(player_name=name,team=meta["team"],
                                gsis_id=self.pids[name],position=meta["pos"]))
        self.roster=self.store("roster.csv",roster_path.read_bytes())
        columns=(*weekly.CORE,"team","FD Pts","AvgPointsPerGame")
        rows=[]
        for tm in ("PIT","CIN"):
            for wk in (8,9):
                stats=[
                    (tm+"_QB",dict(attempts=20,completions=14,passing_tds=2,
                                  passing_interceptions=1,carries=2,rushing_yards=6)),
                    (tm+"_RB",dict(carries=12,rushing_yards=55,rushing_tds=1,
                                  targets=4,receptions=3,receiving_yards=24)),
                    (tm+"_WR",dict(targets=8,receptions=5,
                                  receiving_yards=75,receiving_tds=1))
                ]
                for name,metric in stats:
                    row=dict.fromkeys(columns,"0")
                    row.update(season="2026",week=str(wk),season_type="REG",
                               player_id=self.pids[name],team=tm,
                               **{k:str(v) for k,v in metric.items()})
                    row["FD Pts"]="9000"
                    row["AvgPointsPerGame"]="777"
                    rows.append(row)
        self.rows=rows
        self.columns=columns
        self.manifest={"kickoff_utc":"2026-11-16T01:20:00Z",
                       "game_date_local":"2026-11-15",
                       "target_season":2026,"target_week":10,
                       "roster":self.roster,"template":self.template}
        self.save_weekly(rows)

    def store(self,name,data,capture="2026-11-15T20:00:00Z"):
        raw=data.encode() if isinstance(data,str) else data
        (self.root/name).write_bytes(raw)
        return {"path":name,"sha256":hashlib.sha256(raw).hexdigest(),
                "captured_at_utc":capture}

    def save_weekly(self,rows):
        import io
        buf=io.StringIO()
        writer=csv.DictWriter(buf,fieldnames=self.columns,extrasaction="ignore")
        writer.writeheader();writer.writerows(rows)
        self.manifest["weekly"]=self.store("weekly.csv.gz",
                                            gzip.compress(buf.getvalue().encode(),mtime=0))
        self.manifest_path=self.root/"manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest))

    def test_pregame_weekly_stats_and_no_provider_fp(self):
        out=weekly.build(self.manifest_path,lookback=2,min_games=2)
        self.assertEqual(out["teams"]["CIN"]["pass_att"],20)
        self.assertEqual(out["teams"]["PIT"]["rush_att"],14)
        self.assertEqual(out["teams"]["PIT"]["pass_td"],2)
        self.assertEqual(out["teams"]["CIN"]["fum_lost"],.3)
        self.assertEqual(out["_auto_build"]["team_coverage"]["PIT"]["prior_weeks"],[9,8])
        self.assertFalse(out["_auto_build"]["provider_fantasy_points_used"])
        self.assertNotIn("9000",json.dumps(out))
        self.assertNotIn("777",json.dumps(out))

    def test_current_week_excluded(self):
        rows=[dict(self.rows[0],week="10",receiving_tds="1000")]+self.rows
        self.save_weekly(rows)
        out=weekly.build(self.manifest_path,lookback=2,min_games=2)
        self.assertGreater(out["_auto_build"]["excluded_current_or_future_rows"],0)
        self.assertEqual(out["teams"]["PIT"]["pass_td"],2)

    def test_real_2026_passing_interception_column(self):
        self.assertIn("passing_interceptions",weekly.CORE)
        self.assertNotIn("interceptions",weekly.CORE)
        out=weekly.build(self.manifest_path,lookback=2,min_games=2)
        self.assertEqual(out["teams"]["PIT"]["int_rate"],.05)

    def test_legacy_interception_only_file_is_blocked(self):
        # Real 2026 release uses passing_interceptions. A synthetic
        # legacy-only alias must fail instead of filling 0 INTs.
        self.columns=tuple("interceptions" if k=="passing_interceptions"
                           else k for k in self.columns)
        self.save_weekly(self.rows)
        with self.assertRaises(Blocked):
            weekly.build(self.manifest_path,lookback=2,min_games=2)

    def test_wrong_hash_fails(self):
        self.manifest["weekly"]["sha256"]="0"*64
        self.manifest_path.write_text(json.dumps(self.manifest))
        with self.assertRaises(Blocked):
            weekly.build(self.manifest_path,lookback=2,min_games=2)

    def test_no_team_field_fails(self):
        # The adapter must reject a source with no canonical or documented
        # alternate team identifier, rather than quietly using zero rows.
        self.columns=tuple(x for x in self.columns if x!="team")
        self.save_weekly(self.rows)
        with self.assertRaises(Blocked):
            weekly.build(self.manifest_path,lookback=2,min_games=2)

    def test_ngs_week_zero_is_not_a_weekly_observation(self):
        columns=weekly.NGS
        src=self.root/"ngs.csv"
        with src.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=columns)
            w.writeheader()
            for wk in (0,8,9,10):
                w.writerow({"season":"2026","week":wk,"season_type":"REG",
                    "player_gsis_id":self.pids["PIT_WR"],"team_abbr":"PIT",
                    "targets":"8","receptions":"5","yards":"75","rec_touchdowns":"1"})
        self.manifest["ngs_receiving"]=self.store("ngs.csv",src.read_bytes())
        self.manifest_path.write_text(json.dumps(self.manifest))
        out=weekly.build(self.manifest_path,lookback=2,min_games=2)
        self.assertEqual(out["_auto_build"]["ngs"]["excluded_week_zero_aggregates"],1)
        self.assertEqual(out["_auto_build"]["ngs"]["matched_prior_player_weeks"],2)


if __name__=="__main__":
    unittest.main()
