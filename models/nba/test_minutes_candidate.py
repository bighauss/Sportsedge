import csv,hashlib,io,unittest
from minutes_candidate import Blocked,candidate
def data(bad_future=False,missing=False):
    f=io.StringIO();w=csv.DictWriter(f,fieldnames=["game_id","game_utc","player_id","team","minutes","is_regulation"])
    w.writeheader()
    players=[]
    for tm in ("A","B"):
        for i in range(8):
            pid=tm+str(i);players.append(dict(player_id=pid,team=tm,status="ACTIVE"))
            for k,date in enumerate(("2026-10-01","2026-10-04","2026-10-07")):
                if missing and i==7 and k==2:continue
                w.writerow(dict(game_id=tm+date,game_utc=date+"T23:00:00Z",player_id=pid,team=tm,minutes=30,is_regulation="1"))
    if bad_future:
        w.writerow(dict(game_id="future",game_utc="2026-11-17T23:00:00Z",player_id="A0",team="A",minutes=30,is_regulation="1"))
    b=f.getvalue().encode()
    return b,dict(logs_sha256=hashlib.sha256(b).hexdigest(),captured_at_utc="2026-11-15T12:00:00Z",
                  tipoff_utc="2026-11-16T01:20:00Z",players=players)
class Tests(unittest.TestCase):
    def test_minutes_conserved(self):
        raw,m=data();r=candidate(raw,m)
        self.assertEqual(len(r["players"]),16)
        self.assertEqual(r["team_regulation_minutes"]["A"]["allocated_minutes"],240)
        self.assertTrue(all(p["minutes"]==30 for p in r["players"]))
    def test_future_block(self):
        raw,m=data(bad_future=True)
        with self.assertRaisesRegex(Blocked,"future"):candidate(raw,m)
    def test_missing_history_block(self):
        raw,m=data(missing=True)
        with self.assertRaisesRegex(Blocked,"fewer"):candidate(raw,m)
    def test_unknown_availability_block(self):
        raw,m=data();m["players"][0]["status"]="QUESTIONABLE"
        with self.assertRaisesRegex(Blocked,"status"):candidate(raw,m)
    def test_sha_block(self):
        raw,m=data();m["logs_sha256"]="0"*64
        with self.assertRaisesRegex(Blocked,"hash"):candidate(raw,m)
    def test_capture_block(self):
        raw,m=data();m["captured_at_utc"]=m["tipoff_utc"]
        with self.assertRaisesRegex(Blocked,"lookahead"):candidate(raw,m)
if __name__=="__main__":unittest.main()
