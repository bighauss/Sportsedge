"""Fail-closed synthetic fixtures for dfs item #4; stdlib unittest only."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import build_game_inputs as builder
import backtest_showdown as backtest
import showdown_mc as mc


def put(path, data):
    raw=data.encode("utf-8") if isinstance(data,str) else data
    path.write_bytes(raw)
    return {"path":path.name,"sha256":hashlib.sha256(raw).hexdigest(),
            "captured_at_utc":"2026-11-14T10:00:00Z"}


def fake_game():
    names=[("PIT","P_QB","P_RB","P_WR"),("CIN","C_QB","C_RB","C_WR")]
    cfg={"tag":"PIT_CIN_fixture","salary_file":"salaries.csv","pool_min_mean":0.0,
         "players":{},"teams":{},"market":{"spread_home":3.5,"total":48.0}}
    for team,qb,rb,wr in names:
        cfg["teams"][team]={"qb":qb,"pass_att":14,"rush_att":9,"pass_td":1.0,
            "rush_td":.4,"int_rate":.01,"fum_lost":.1,"fga":0.0,"fg50":.8,"fg40":.85,
            "fg_short":.9,"targets":{wr:3,rb:1},"recv":{"_default":[.6,10],wr:[.6,10],rb:[.8,6]},
            "pass_td_w":{wr:2,rb:1},"rush":{rb:9,qb:1},
            "ypc":{rb:4,qb:3},"rush_td_w":{rb:4,qb:.1},
            "dst":{"sacks":1,"frec":0.1,"td":0.0}}
        for n,pos in ((qb,"QB"),(rb,"RB"),(wr,"WR")):
            cfg["players"][n]={"team":team,"pos":pos,"p_active":1.0}
    return cfg


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.cfg=fake_game()
        self.template=put(self.root/"game.json",json.dumps(self.cfg))
        roster=[
            {"player_name":n,"team":meta["team"],
             "gsis_id":str(i+1),"position":meta["pos"]}
            for i,(n,meta) in enumerate(self.cfg["players"].items())]
        self.ids={r["player_name"]:r["gsis_id"] for r in roster}
        roster_path=self.root/"roster.csv"
        with roster_path.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=builder.ROSTER_COLUMNS)
            w.writeheader();w.writerows(roster)
        self.roster=put(roster_path,roster_path.read_bytes())
        plays=[]
        for tm,opp,dates in (("PIT","CIN",["2026-11-01","2026-11-08"]),
                             ("CIN","PIT",["2026-11-01","2026-11-08"])):
            qb,rb,wr=(f"{tm[0]}_QB",f"{tm[0]}_RB",f"{tm[0]}_WR")
            for j,day in enumerate(dates):
                game=f"{day}-{tm}-{opp}"
                for i in range(14):
                    plays.append(dict(game_id=game,game_date=day,posteam=tm,
                        season_type="REG",pass_attempt=1,rush_attempt=0,
                        complete_pass=int(i%2==0),pass_touchdown=int(i==0),
                        rush_touchdown=0,interception=0,fumble_lost=0,
                        passing_yards=12 if i%2==0 else 0,
                        receiving_yards=12 if i%2==0 else 0,rushing_yards=0,
                        passer_player_id=self.ids[qb],
                        receiver_player_id=self.ids[wr if i%3 else rb],
                        rusher_player_id="",yardline_100=10 if i<2 else 50))
                for i in range(9):
                    plays.append(dict(game_id=game,game_date=day,posteam=tm,
                        season_type="REG",pass_attempt=0,rush_attempt=1,
                        complete_pass=0,pass_touchdown=0,rush_touchdown=int(i==0),
                        interception=0,fumble_lost=0,passing_yards=0,
                        receiving_yards=0,rushing_yards=4,
                        passer_player_id="",receiver_player_id="",
                        rusher_player_id=self.ids[rb],
                        yardline_100=4 if i<2 else 60))
        pbp=self.root/"pbp.csv"
        with pbp.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=builder.PBP_COLUMNS)
            w.writeheader();w.writerows(plays)
        self.pbp=put(pbp,pbp.read_bytes())
        self.manifest={"kickoff_utc":"2026-11-16T01:20:00Z",
                       "game_date_local":"2026-11-15",
                       "template":self.template,"roster":self.roster,"pbp":self.pbp}
        self.manifest_path=self.root/"inputs.json"
        self.save_manifest()
    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def test_pbp_builder_uses_only_raw_prior_plays(self):
        cfg=builder.build(self.manifest_path,lookback=2,min_games=2)
        self.assertEqual(cfg["teams"]["PIT"]["pass_att"],14)
        self.assertEqual(cfg["teams"]["CIN"]["rush_att"],9)
        self.assertEqual(cfg["teams"]["PIT"]["pass_td"],1.0)
        self.assertEqual(cfg["_auto_build"]["status"],"PAPER_RESEARCH_ONLY")
        self.assertFalse(cfg["_auto_build"]["provider_fantasy_points_used"])
        self.assertEqual(cfg["teams"]["PIT"]["fga"],0.0)
        self.assertNotIn("AvgPointsPerGame",str(cfg))

    def test_local_date_required_for_us_evening_kickoff(self):
        self.manifest.pop("game_date_local")
        self.save_manifest()
        with self.assertRaises(builder.Blocked):
            builder.build(self.manifest_path,lookback=2,min_games=2)

    def test_special_scoring_from_raw_boxscore(self):
        row={field:"0" for field in backtest.RESULT_HEADER}
        row.update(player_name="Tester",team="PIT",pos="WR",
                   two_point_conversions="1",return_tds="1",offensive_fumble_td="1")
        self.assertEqual(backtest.observed_score(row),14)
        row.update(pos="DST",points_allowed="17",
                   blocked_kicks="1",two_point_returns="1")
        self.assertEqual(backtest.observed_score(row),5)

    def test_bad_hash_blocked(self):
        self.manifest["pbp"]["sha256"]="00"*32
        self.save_manifest()
        with self.assertRaises(builder.Blocked):
            builder.build(self.manifest_path,lookback=2,min_games=2)

    def test_post_kickoff_capture_blocked(self):
        self.manifest["pbp"]["captured_at_utc"]="2026-11-16T02:00:00Z"
        self.save_manifest()
        with self.assertRaises(builder.Blocked):
            builder.build(self.manifest_path,lookback=2,min_games=2)

    def test_future_game_data_blocked_even_with_good_hash(self):
        with (self.root/"pbp.csv").open("a") as f:
            f.write("future,2026-11-15,PIT,REG,1,0,1,0,0,0,0,10,10,0,1,3,,50\n")
        self.manifest["pbp"]=put(self.root/"pbp.csv",(self.root/"pbp.csv").read_bytes())
        self.save_manifest()
        with self.assertRaises(builder.Blocked):
            builder.build(self.manifest_path,lookback=2,min_games=2)

    def archive(self,model_ok=True):
        sal=self.root/"salaries.csv"
        with sal.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=("Name","TeamAbbrev","Position","Roster Position","Salary","Status"))
            w.writeheader()
            for name,info in self.cfg["players"].items():
                for role,cost in (("FLEX",7500),("CPT",11250)):
                    w.writerow({"Name":name,"TeamAbbrev":info["team"],
                        "Position":info["pos"],"Roster Position":role,
                        "Salary":cost,"Status":""})
        salary=put(sal,sal.read_bytes())
        result=self.root/"results.csv"
        with result.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=backtest.RESULT_HEADER)
            w.writeheader()
            for name,info in self.cfg["players"].items():
                row={k:0 for k in backtest.RESULT_HEADER}
                row.update(player_name=name,team=info["team"],pos=info["pos"])
                row.update(pass_yd=200 if info["pos"]=="QB" else 0,
                           receptions=5 if info["pos"]=="WR" else 0,
                           rush_yd=75 if info["pos"]=="RB" else 0)
                w.writerow(row)
        result_spec=put(result,result.read_bytes())
        result_spec["captured_at_utc"]="2026-11-16T08:00:00Z"
        model_hash=hashlib.sha256(Path(mc.__file__).read_bytes()).hexdigest()
        entry={"tag":self.cfg["tag"],"kickoff_utc":self.manifest["kickoff_utc"],
            "config":self.template,"salaries":salary,"results":result_spec,
            "engine":{"sha256":model_hash if model_ok else "bad",
                      "captured_at_utc":"2026-11-14T10:00:00Z"}}
        ar=self.root/"archive.json"
        ar.write_text(json.dumps({"slates":[entry]}))
        return ar

    def test_backtest_asof_replay_and_no_roi(self):
        a=self.archive()
        data=backtest.replay(a,n_sims=60,seed=7)
        self.assertTrue(data["all_verified_asof"])
        self.assertGreaterEqual(data["slates"][0]["gpp_actual_points"],0)
        self.assertEqual(data["slates"][0]["ownership"],"NOT_AVAILABLE")
        self.assertIn("NO_FIELD",data["slates"][0]["contest_ev"])

    def test_backtest_rejects_changed_model_or_labels_reconstruction(self):
        a=self.archive(model_ok=False)
        with self.assertRaises(builder.Blocked):
            backtest.replay(a,n_sims=50)
        reconstructed=backtest.replay(a,n_sims=50,allow_reconstruction=True)
        self.assertFalse(reconstructed["all_verified_asof"])
        self.assertEqual(reconstructed["slates"][0]["status"],"RECONSTRUCTED_NOT_FORWARD_TEST")

    def test_backtest_prelock_result_leak_blocked(self):
        a=self.archive()
        x=json.loads(a.read_text())
        x["slates"][0]["results"]["captured_at_utc"]="2026-11-15T19:00:00Z"
        a.write_text(json.dumps(x))
        with self.assertRaises(builder.Blocked):
            backtest.replay(a,n_sims=50)


if __name__=="__main__":
    unittest.main()
