"""R2 safety regression: malformed inputs must yield BLOCK reports, no crash.

Requires the frozen v5 package's dependencies alongside this script.
"""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from sportsedge_nfl_daily_lane_r2 import preflight, run

HEADER = 'sport,home,away,home_proj,away_proj,market,price_a,price_b\n'
MODEL_HEADER = 'sport,home,away,home_proj,away_proj,asof_ct,start_ct,model_version,source_file_sha256\n'

class FailClosedInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.board=self.dir/'board.csv'
        self.board.write_text(HEADER+'NFL,NY Giants,WAS Commanders,,,ML,-110,-110\n')
        self.source=self.dir/'source.txt';self.source.write_text('SYNTHETIC; not evidence\n')
        self.proj=self.dir/'projections.csv'
        h=hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.proj.write_text(MODEL_HEADER+f'NFL,NY Giants,WAS Commanders,21,20,2026-11-12T12:00:00-06:00,2026-11-12T19:15:00-06:00,SPORTSEDGE_NFL_SYNTHETIC,{h}\n')
        self.capture='2026-11-12T18:08:00-06:00'
        self.engine=self.dir/'sportsedge_v5.py';self.engine.write_text('not V5\n')
        self.slate=self.dir/'slate.csv';self.slate.write_text('sport,away,home,dk_event_id\nNFL,WAS Commanders,NY Giants,synth\n')

    def call_run(self):
        z=run(self.board,self.proj,self.source,self.capture,self.engine,self.slate,self.dir/'out',True)
        self.assertEqual(z['verdict'],'BLOCK')
        self.assertFalse(z['pricing_invoked'])
        disk=json.loads((self.dir/'out'/'nfl_daily_lane_report.json').read_text())
        self.assertEqual(disk['verdict'],'BLOCK')
        return disk

    def test_truncated_board_row_fails_closed(self):
        self.board.write_text(HEADER+'NFL,NY Giants,WAS Commanders\n')
        self.assertIn('CSV_UNDERFLOW',str(self.call_run()['refusals']))

    def test_truncated_projection_row_fails_closed(self):
        self.proj.write_text(MODEL_HEADER+'NFL,NY Giants,WAS Commanders\n')
        self.assertIn('CSV_UNDERFLOW',str(self.call_run()['refusals']))

    def test_overflow_board_row_fails_closed(self):
        self.board.write_text(HEADER+'NFL,NY Giants,WAS Commanders,,,ML,-110,-110,EXTRA\n')
        self.assertIn('CSV_OVERFLOW',str(self.call_run()['refusals']))

    def test_blank_board_market_fails_closed(self):
        self.board.write_text(HEADER+'NFL,NY Giants,WAS Commanders,,,,-110,-110\n')
        z=preflight(self.board,self.proj,self.source,self.capture)
        self.assertIn('MISSING_BOARD_IDENTITY_OR_MARKET',z['refusals'])

    def test_same_team_fails_closed(self):
        self.board.write_text(HEADER+'NFL,NY Giants,NY Giants,,,ML,-110,-110\n')
        self.assertIn('BOARD_HOME_EQUALS_AWAY',preflight(self.board,self.proj,self.source,self.capture)['refusals'])

    def test_blank_model_version_fails_closed(self):
        self.proj.write_text(self.proj.read_text().replace('SPORTSEDGE_NFL_SYNTHETIC',''))
        self.assertIn('MISSING_MODEL_IDENTITY_OR_PROVENANCE',preflight(self.board,self.proj,self.source,self.capture)['refusals'])

    def test_missing_engine_fails_closed(self):
        self.engine.unlink()
        self.assertIn('GUARDED_V5_INPUT_OR_RUNTIME',str(self.call_run()['refusals']))

    def test_no_sources_fails_closed(self):
        self.assertIn('MISSING_OWN_MODEL_PROJECTIONS_OR_SOURCE',preflight(self.board)['refusals'])

    def test_valid_synthetic_preflight_does_not_price(self):
        self.assertEqual(preflight(self.board,self.proj,self.source,self.capture)['verdict'],'PIT_READY_FOR_GUARDED_V5')
        self.assertIn('ENGINE_SHA_NOT_V5_OF_RECORD',self.call_run()['refusals'])

if __name__=='__main__':unittest.main(verbosity=2)
