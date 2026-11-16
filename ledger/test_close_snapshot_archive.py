import csv,hashlib,io,json,tempfile,unittest
from pathlib import Path
from close_snapshot_archive import Blocked,make_records,append,verify_chain

def fixture(kind="CLOSE"):
    f=io.StringIO();cols=["book","event_id","market_key","selection","line","price_american",
                          "provider_event_id","provider_market_id","provider_quote_id"]
    w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
    w.writerow(dict(book="DK",event_id="E1",market_key="FG_TOTAL",selection="OVER",
                    line="49.5",price_american="-110",provider_event_id="DK-E1",
                    provider_market_id="M1",provider_quote_id="NOT_CAPTURED"))
    raw=f.getvalue().encode()
    m=dict(source_sha256=hashlib.sha256(raw).hexdigest(),snapshot_kind=kind,
           event_id="E1",captured_at_utc="2026-11-16T01:15:00Z",
           kickoff_utc="2026-11-16T01:20:00Z")
    return raw,m

class Tests(unittest.TestCase):
    def test_valid_close_paper_and_no_claim(self):
        raw,m=fixture();r=make_records(raw,m)
        self.assertEqual(r[0]["close_window_seconds"],300)
        self.assertEqual(r[0]["evidence_state"],"PAPER_SOURCE_CLAIM_ONLY")
    def test_outside_window_block(self):
        raw,m=fixture();m["captured_at_utc"]="2026-11-15T23:00:00Z"
        with self.assertRaisesRegex(Blocked,"WINDOW"):make_records(raw,m)
    def test_after_kickoff_block(self):
        raw,m=fixture();m["captured_at_utc"]=m["kickoff_utc"]
        with self.assertRaisesRegex(Blocked,"AFTER"):make_records(raw,m)
    def test_source_hash_block(self):
        raw,m=fixture();m["source_sha256"]="0"*64
        with self.assertRaisesRegex(Blocked,"HASH"):make_records(raw,m)
    def test_append_chain_and_duplicates(self):
        raw,m=fixture();r=make_records(raw,m)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"snapshots.ndjson"
            self.assertEqual(append(path,r)["added"],1)
            self.assertEqual(len(verify_chain(path)),1)
            with self.assertRaisesRegex(Blocked,"DUPLICATE"):append(path,r)
            path.write_text(path.read_text().replace("49.5","48.5"))
            with self.assertRaisesRegex(Blocked,"HASH"):verify_chain(path)
    def test_take_can_be_earlier(self):
        raw,m=fixture("TAKE");m["captured_at_utc"]="2026-11-15T15:00:00Z"
        self.assertIsNone(make_records(raw,m)[0]["close_window_seconds"])
if __name__=="__main__":unittest.main()
