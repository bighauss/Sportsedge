import csv,hashlib,io,json,tempfile,unittest
from pathlib import Path
from close_snapshot_archive import Blocked,make_records,append,verify_chain,from_manifest,REPO_ROOT

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
    def test_missing_provider_id_remains_paper(self):
        raw,m=fixture()
        raw=raw.replace(b"NOT_CAPTURED",b"")
        m["source_sha256"]=hashlib.sha256(raw).hexdigest()
        r=make_records(raw,m)
        self.assertEqual(r[0]["provider_quote_id"],"NOT_CAPTURED")
        self.assertEqual(r[0]["evidence_state"],"PAPER_SOURCE_CLAIM_ONLY")
    def test_duplicate_csv_headers_rejected_before_grading(self):
        raw,m=fixture()
        altered=raw.replace(b"line,price_american",b"line,line,price_american")
        m["source_sha256"]=hashlib.sha256(altered).hexdigest()
        with self.assertRaisesRegex(Blocked,"DUPLICATE_CSV_HEADER"):
            make_records(altered,m)

    def test_overlong_csv_row_rejected_not_truncated(self):
        raw,m=fixture()
        altered=raw.rstrip(b"\n")+b",INJECTED\n"
        m["source_sha256"]=hashlib.sha256(altered).hexdigest()
        with self.assertRaisesRegex(Blocked,"MALFORMED_CSV_ROW"):
            make_records(altered,m)

    def test_equivalent_alt_line_spellings_are_one_selection(self):
        raw,m=fixture()
        lines=raw.decode().splitlines()
        changed=lines[1].replace(",49.5,",",+049.500,")
        self.assertNotEqual(changed,lines[1])
        altered=("\n".join([lines[0],lines[1],changed])+"\n").encode()
        m["source_sha256"]=hashlib.sha256(altered).hexdigest()
        with self.assertRaisesRegex(Blocked,"DUPLICATE_SAME_MARKET_LINE"):
            make_records(altered,m)

    def test_distinct_alt_lines_remain_distinct(self):
        raw,m=fixture()
        lines=raw.decode().splitlines()
        extra=lines[1].replace(",49.5,",",50.5,")
        altered=("\n".join([lines[0],lines[1],extra])+"\n").encode()
        m["source_sha256"]=hashlib.sha256(altered).hexdigest()
        rows=make_records(altered,m)
        self.assertEqual(len(rows),2)
        self.assertEqual([r["line"] for r in rows],["49.5","50.5"])

    def test_observed_after_local_capture_is_impossible(self):
        raw,m=fixture()
        m["observed_at_utc"]="2026-11-16T01:18:00Z"
        with self.assertRaisesRegex(Blocked,"PROVIDER_CLOCK_AFTER_LOCAL_CAPTURE"):
            make_records(raw,m)

    def test_nan_line_refused_even_with_original_hash(self):
        raw,m=fixture()
        corrupted=raw.replace(b",49.5,",b",NaN,")
        m["source_sha256"]=hashlib.sha256(corrupted).hexdigest()
        with self.assertRaisesRegex(Blocked,"INVALID_NUMERIC_MARKET_LINE"):
            make_records(corrupted,m)

    def test_public_repo_manifest_and_ledger_paths_refused(self):
        raw,m=fixture()
        records=make_records(raw,m)
        with tempfile.TemporaryDirectory() as d:
            safe=Path(d)/"ledger.ndjson"
            self.assertEqual(append(safe,records)["added"],1)
        with self.assertRaisesRegex(Blocked,"PRIVATE_LEDGER_MUST_BE_OUTSIDE_PUBLIC_REPO"):
            append(REPO_ROOT/"ledger"/"do_not_write_private.ndjson",records)
        with self.assertRaisesRegex(Blocked,"PRIVATE_MANIFEST_MUST_BE_OUTSIDE_PUBLIC_REPO"):
            from_manifest(REPO_ROOT/"ledger"/"do_not_read_private.json")

    def test_take_can_be_earlier(self):
        raw,m=fixture("TAKE");m["captured_at_utc"]="2026-11-15T15:00:00Z"
        self.assertIsNone(make_records(raw,m)[0]["close_window_seconds"])
if __name__=="__main__":unittest.main()
