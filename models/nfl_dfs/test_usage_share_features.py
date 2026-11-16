import csv,gzip,hashlib,io,unittest
from usage_share_features import Blocked,derive

def fixture(future=False,unmapped=False):
    f=io.StringIO();fields=["season","week","season_type","player_id","recent_team","targets","carries"]
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for week in (1,2,3):
        for tm,tag in (("PIT","P"),("CIN","C")):
            for pid in ("A","B"):
                w.writerow(dict(season=2026,week=week,season_type="REG",player_id=tag+pid,recent_team=tm,targets=10,carries=12))
    if future: w.writerow(dict(season=2026,week=4,season_type="REG",player_id="PA",recent_team="PIT",targets=10,carries=12))
    if unmapped: w.writerow(dict(season=2026,week=2,season_type="REG",player_id="X",recent_team="PIT",targets=100,carries=100))
    raw=f.getvalue().encode()
    m=dict(source_sha256=hashlib.sha256(raw).hexdigest(),captured_at_utc="2026-11-15T20:00:00Z",
           kickoff_utc="2026-11-16T01:20:00Z",season=2026,target_week=4,
           roster=[dict(player_id=k,team=t) for t,k in (("PIT","PA"),("PIT","PB"),("CIN","CA"),("CIN","CB"))])
    return raw,m

class Tests(unittest.TestCase):
    def test_exact_ids_and_shrink(self):
        raw,m=fixture();r=derive(raw,m)
        self.assertEqual(len(r["players"]),4)
        self.assertAlmostEqual(r["players"][0]["target_share_raw"],.5)
        self.assertLess(r["players"][0]["target_share_shrunk"],.5)
        self.assertIsNone(r["players"][0]["snap_share"])
    def test_future_block(self):
        raw,m=fixture(True)
        with self.assertRaisesRegex(Blocked,"future"): derive(raw,m)
    def test_unmapped_block(self):
        raw,m=fixture(unmapped=True)
        with self.assertRaisesRegex(Blocked,"coverage"): derive(raw,m)
    def test_capture_time_block(self):
        raw,m=fixture();m["captured_at_utc"]=m["kickoff_utc"]
        with self.assertRaisesRegex(Blocked,"before kickoff"): derive(raw,m)
    def test_hash_block(self):
        raw,m=fixture();m["source_sha256"]="a"*64
        with self.assertRaisesRegex(Blocked,"SHA256"): derive(raw,m)
    def test_gzip_source_hash(self):
        raw,m=fixture();z=gzip.compress(raw);m.update(compressed=True,source_sha256=hashlib.sha256(z).hexdigest())
        self.assertEqual(len(derive(z,m)["players"]),4)
if __name__=="__main__": unittest.main()
