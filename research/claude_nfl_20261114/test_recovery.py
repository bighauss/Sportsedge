"""Research only: guards for recovered Claude Nov 14 runner, TD-share builder and v2.1 contrast."""
import csv,hashlib,io,os,tempfile,unittest
from pathlib import Path
import nfl_full_slate as slate
import se_repair_layer as r2
import build_nfl_td_shares_v1_1_20261114 as td
import reconcile_r2_v21 as v21
HERE=Path(__file__).resolve().parent
class RecoveryTests(unittest.TestCase):
    def test_sources_frozen_sha(self):
        for path,digest in {
          'nfl_full_slate.py':'282f9660636ce5d807e924b345b4ac8756007b8511af37b0231cba5bba54ad49',
          'se_repair_layer.py':'300c0938b1c17abfdae62d90dc5f4aa3d71c1c365310bb3809077746eb94d2e0',
          'build_nfl_td_shares_v1_1_20261114.py':'c0816ce737e6b53e8cf8e882ce4e3d6295a9e0b482d19ada95eb60f37b3f0cc5'}.items():
            self.assertEqual(hashlib.sha256((HERE/path).read_bytes()).hexdigest(),digest)
    def test_r2_no_rows_dropped(self):
        rows=[dict(sport='NFL',game='A @ B',mode='PROJECTION',model_p='.60',market_p='.55',price='-110',bet_type='ML|0|')]
        out=r2.repair(rows)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['pooled_p'],round(r2.pool(.6,.55,.30),6))
    def test_v21_linear_not_logit(self):
        s=[dict(sport='NFL',game='A @ B',pick='A ML',bet_type='ML|0|',model_p='.80',market_p='.20',price='+150',pooled_p='0.34',r2_keep='0')]
        o=v21.diagnostic(s);z=o['rows'][0]
        self.assertAlmostEqual(z['v21_linear_probability'],.38)
        self.assertIn('MODEL_MARKET_GAP_GT15PP_REVIEW',z['flags'])
        self.assertEqual(o['approved_stake_u'],0)
    def test_bad_odds_rejected(self):
        o=v21.diagnostic([dict(sport='NFL',game='A @ B',pick='A',bet_type='ML',model_p='.8',market_p='.2',price='0')]);self.assertEqual(o['invalid_rows'],1)
    def test_td_share_excludes_future_week_and_pass_td(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'week.csv'
            f.write_text('season,week,season_type,recent_team,player_display_name,player_id,rushing_tds,receiving_tds,passing_tds\n'
                         '2026,9,REG,BUF,Alice,A,1,0,9\n2026,9,REG,BUF,Bob,B,0,2,4\n2026,10,REG,BUF,Alice,A,100,0,0\n')
            shares,audit,sha=td.build(f,require_32=False)
            val={a['player']:float(a['share']) for a in shares}
            self.assertAlmostEqual(val['Alice'],1/3)
            self.assertAlmostEqual(val['Bob'],2/3)
    def test_missing_32_teams_not_promoted(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'week.csv'
            f.write_text('season,week,recent_team,player_display_name,player_id,rushing_tds,receiving_tds\n2026,9,BUF,Alice,A,1,0\n')
            with self.assertRaises(ValueError):td.build(f,require_32=True)
    def test_full_slate_missing_curve_refused(self):
        self.assertEqual(slate.prop_mean({}, {},'Fake Player','PASS_YDS'),(None,None,0))
if __name__=='__main__':unittest.main(verbosity=2)
