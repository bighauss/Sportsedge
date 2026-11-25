"""Whole native module tests. Synthetic inputs are not predictive validation."""
import copy
import datetime as dt
import json
import tempfile
from pathlib import Path
import unittest
import cbbd_native_score_model as native
from research.cbb_hca.cbb_score_factorial import compare,freeze


def context():
    ratings=[dict(season=2027,teamId=i,offensiveRating=o,defensiveRating=d,netRating=o-d)
             for i,o,d in ((1,112.,100.),(2,108.,104.),(3,104.,108.))]
    rows=[]
    for i in range(60):
        tip=dt.datetime(2026,11,1,tzinfo=dt.timezone.utc)+dt.timedelta(hours=i*6)
        rows.append(dict(game_id=str(i+1),season=2027,tipoff_utc=native.stamp(tip),
            final_captured_utc=native.stamp(tip+dt.timedelta(hours=3)),home_team_id=str(i%3+1),
            away_team_id=str((i+1)%3+1),neutral=False,home_points=80+i%7,away_points=70+i%5,possessions=65+i%11))
    return native.fit_context(json.dumps(ratings).encode(),rows,season=2027,freeze_utc="2026-11-24T23:00:00Z")

class NativeIntegration(unittest.TestCase):
    def test_baseline_parity(self):
        ctx=context();p=native.project(ctx,"1","2",neutral=False,_need_sd=False)
        rows=compare(ctx,"1","2",neutral=False);self.assertEqual(len(rows),4)
        for k in ("home_points","away_points","margin","total","possessions"):
            self.assertEqual(rows["additive_product"][k],p[k])
    def test_context_unchanged(self):
        ctx=context();old=copy.deepcopy(ctx);compare(ctx,"1","2",neutral=False);self.assertEqual(ctx,old)
    def test_venue_gate(self):
        with self.assertRaises(native.Pass):compare(context(),"1","2",neutral=None)
    def test_native_pace_gate(self):
        ctx=context();ctx["team_pace"]["1"]=(70.,0)
        with self.assertRaisesRegex(native.Pass,"MISSING_PACE_HISTORY"):compare(ctx,"1","2",neutral=False)
    def test_create_only_and_pretip(self):
        g=dict(game_id="1000",season=2027,home_team_id="1",away_team_id="2",neutral=False,tipoff_utc="2026-11-25T01:00:00Z")
        clock=lambda:dt.datetime(2026,11,24,23,1,tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"forecast.json";r=freeze(context(),g,p,clock=clock)
            self.assertEqual(len(r["forecasts"]),4)
            with self.assertRaises(FileExistsError):freeze(context(),g,p,clock=clock)
            g["tipoff_utc"]="2026-11-24T22:00:00Z"
            with self.assertRaises(native.Pass):freeze(context(),g,Path(td)/"late.json",clock=clock)

if __name__=="__main__":unittest.main()
