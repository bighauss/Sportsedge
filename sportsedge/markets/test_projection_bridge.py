"""Synthetic end-to-end bridge to existing recovered Claude and NFL ridge forecasts.

Prepares documented fake sample datasets, never pulls live bookmaker data.
"""
from __future__ import annotations
import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path

from sportsedge.markets.projection_bridge import from_claude_sport,from_nfl_ridge,sha_inputs

ROOT=Path(__file__).resolve().parents[2]
ASOF=datetime(2026,11,15,12,0,tzinfo=timezone.utc)


class ProjectionBridgeAcceptance(unittest.TestCase):
    def test_cbb_existing_projection_not_old_card(self):
        from models.cbb import test_cbb
        paths=test_cbb.make_samples()
        # Synthetic venue evidence for the matching event; not provider proof.
        with tempfile.TemporaryDirectory() as d:
            venue=Path(d)/"venue_registry.csv"
            venue.write_text(
                "game_id,neutral,source,source_sha256,published_utc,captured_utc,tipoff_utc\\n"
                "C1,0,ESPN," + "a"*64 +
                ",2026-11-15T10:00:00Z,2026-11-15T11:00:00Z,2026-11-15T19:00:00Z\n")
            paths["venue_registry"]=str(venue)
            p=from_claude_sport("CBB",paths,"C1",asof_utc=ASOF)
        self.assertEqual((p.home_id,p.away_id),("Alpha","Beta"))
        self.assertGreater(p.expected_home,0)
        self.assertGreater(p.expected_away,0)
        self.assertIn("NOT_CHRONOLOGICALLY_CALIBRATED",p.warnings)

    def test_cfb_existing_projection_not_old_card(self):
        from models.cfb import make_samples
        make_samples.main()
        directory=ROOT/"models/cfb/samples"
        d=json.loads((directory/"inputs.json").read_text())
        paths={k:str(directory/v) for k,v in d.items()}
        p=from_claude_sport("CFB",paths,"1001",asof_utc=ASOF)
        self.assertEqual((p.home_id,p.away_id),("Alpha State","Beta Tech"))
        self.assertGreater(p.expected_home,0)
        self.assertNotEqual(p.expected_home,p.expected_away)

    def test_nba_existing_projection_not_old_card(self):
        from models.nba import make_samples
        make_samples.main()
        root=ROOT/"models/nba/sample"
        names=("teams","games","injuries","players","positional_defense","odds","props")
        paths={k:str(root/(k+".csv")) for k in names}
        p=from_claude_sport("NBA",paths,"G1",asof_utc=ASOF)
        self.assertGreater(p.expected_home+p.expected_away,200)

    def test_mlb_existing_projection_not_old_card(self):
        from models.mlb import make_samples
        make_samples.main()
        root=ROOT/"models/mlb/sample_inputs"
        p=from_claude_sport("MLB",{"folder":str(root)},"G1",asof_utc=ASOF)
        self.assertGreater(p.expected_home,0)
        self.assertGreater(p.expected_away,0)

    def test_nfl_frozen_ridge_recomputation_gate(self):
        source=(
          "team,off,def,gp,lg,hfa,asof,half_life,ridge\n"
          "Alpha,2,1,5,21,1.6,2026-11-15,45,5\n"
          "Beta,-1,0,5,21,1.6,2026-11-15,45,5\n")
        forecast={"home":"Alpha","away":"Beta","home_proj":"23.800",
                  "away_proj":"18.200","model_version":"SPORTSEDGE_NFL_RIDGE_R1",
                  "asof_ct":"2026-11-15T12:00:00+00:00"}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ratings.csv";path.write_text(source)
            p=from_nfl_ridge(str(path),forecast,event_id="NFL-TEST",frozen_asof_utc=ASOF)
            self.assertAlmostEqual(p.expected_home,23.8)
            self.assertIn("NFL_RIDGE_FORMULA_REPRODUCED",p.warnings)
            forecast["away_proj"]="30.000"
            with self.assertRaisesRegex(ValueError,"RECOMPUTATION_GATE"):
                from_nfl_ridge(str(path),forecast,event_id="NFL-TEST",frozen_asof_utc=ASOF)

    def test_market_quote_data_does_not_enter_feature_hash(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            (folder/"teams.csv").write_text("team,off\nA,2\n")
            (folder/"odds.csv").write_text("book,price\nDK,-110\n")
            a=sha_inputs({"folder":str(folder)})
            (folder/"odds.csv").write_text("book,price\nDK,+350\n")
            b=sha_inputs({"folder":str(folder)})
            self.assertEqual(a,b)
            (folder/"teams.csv").write_text("team,off\nA,3\n")
            c=sha_inputs({"folder":str(folder)})
            self.assertNotEqual(a,c)


if __name__=="__main__":
    unittest.main()
