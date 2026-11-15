#!/usr/bin/env python3
"""Offline standard-library regression tests for the READ-ONLY NBA append guard."""
import contextlib
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from sportsedge_nba_append_guard_r3 import HEADER, run


def make_csv(rows, *, newline='\r\n', header=HEADER):
    f = io.StringIO(newline='')
    w = csv.writer(f, lineterminator=newline)
    w.writerow(header)
    w.writerows(rows)
    return f.getvalue().encode('utf-8')

A = ('NBA','2026-11-10','NY Knicks','CLE Cavaliers','108','100','0','')
B = ('NBA','2026-11-11','DET Pistons','LA Lakers','121','110','0','')
C = ('NBA','2026-11-12','CHI Bulls','SA Spurs','123','112','0','')

class GuardTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def put(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def check(self, args, passed):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = run([str(a) for a in args])
        parsed = json.loads(output.getvalue())
        self.assertEqual((rc,parsed['status']), (0,'PASS') if passed else (4,'FAIL'))
        return parsed

    def audit(self, rows, passed=True, **kwargs):
        data = make_csv(rows, **kwargs)
        return self.check(['audit',self.put('board.csv',data),'--as-of','2026-11-13'],passed)

    def test_accept_blank_poss(self): self.audit([A,B])
    def test_accept_numeric_poss(self): self.audit([(*A[:-1], '97.1')])
    def test_reject_zero_poss(self): self.audit([(*A[:-1], '0')],False)
    def test_reject_nan_poss(self): self.audit([(*A[:-1], 'nan')],False)
    def test_reject_negative_poss(self): self.audit([(*A[:-1], '-1')],False)
    def test_reject_duplicate(self): self.audit([A,A],False)
    def test_reject_case_variant_duplicate(self): self.audit([A,(*A[:2],'ny knicks',*A[3:])],False)
    def test_reject_missing_home(self): self.audit([(*A[:2],'',*A[3:])],False)
    def test_reject_same_team(self): self.audit([(*A[:3],A[2],*A[4:])],False)
    def test_reject_invalid_date(self): self.audit([('NBA','2026-02-31',*A[2:])],False)
    def test_reject_future_date(self): self.audit([('NBA','2026-11-14',*A[2:])],False)
    def test_reject_bad_score(self): self.audit([(*A[:4],'-1',*A[5:])],False)
    def test_reject_empty_score(self): self.audit([(*A[:4],'',*A[5:])],False)
    def test_reject_bad_neutral(self): self.audit([(*A[:6],'2',*A[7:])],False)
    def test_reject_ragged(self): self.audit([A[:7]],False)
    def test_reject_duplicate_header(self): self.audit([A],False,header=[*HEADER[:-1],'neutral'])
    def test_reject_empty(self): self.check(['audit',self.put('empty.csv',b'')],False)
    def test_reject_non_utf8(self): self.check(['audit',self.put('bad.csv',b'\xff')],False)
    def test_reject_no_final_newline(self):
        self.check(['audit',self.put('bad.csv',make_csv([A]).rstrip(b'\r\n'))],False)
    def test_valid_byte_replay(self):
        base = make_csv([A]);delta = make_csv([B,C]);merged = base + delta[delta.index(b'\n')+1:]
        self.check(['replay',self.put('base.csv',base),self.put('delta.csv',delta),self.put('merged.csv',merged)],True)
    def test_byte_replay_lf_normalization_fails(self):
        base = make_csv([A]);delta = make_csv([B]);merged = (base + delta[delta.index(b'\n')+1:]).replace(b'\r\n',b'\n')
        self.check(['replay',self.put('base.csv',base),self.put('delta.csv',delta),self.put('merged.csv',merged)],False)
    def test_byte_replay_wrong_row_fails(self):
        base = make_csv([A]);delta = make_csv([B]);merged=make_csv([A,C])
        self.check(['replay',self.put('base.csv',base),self.put('delta.csv',delta),self.put('merged.csv',merged)],False)
    def test_replay_reject_base_delta_overlap(self):
        base = make_csv([A]);delta = make_csv([A]);merged=base + delta[delta.index(b'\n')+1:]
        self.check(['replay',self.put('base.csv',base),self.put('delta.csv',delta),self.put('merged.csv',merged)],False)
    def test_stdout_json_parseable(self):
        r=self.audit([A]);self.assertEqual(r['checks']['inputs'][0]['rows'],1)

if __name__=='__main__': unittest.main(verbosity=2)
