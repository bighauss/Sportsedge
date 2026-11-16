"""Private close-price preflight with auditable local hash chain (research only).

NO sportsbook scraping, no quote authentication, no wagering. Never commit
quote CSV, capture manifest or output NDJSON to a public GitHub repository.
Local SHA chain is NOT a third-party timestamp or immutable proof.
"""
from __future__ import annotations
import argparse,csv,datetime as dt,hashlib,io,json,math
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS=("book","event_id","market_key","selection","line","price_american",
        "provider_event_id","provider_market_id","provider_quote_id")

class Blocked(ValueError): pass

REPO_ROOT = Path(__file__).resolve().parents[1]


def private_path(path, reason="PRIVATE_EVIDENCE_MUST_BE_OUTSIDE_PUBLIC_REPO"):
    """Reject repository paths regardless of CWD, including resolved symlinks."""
    target = Path(path).resolve()
    if target == REPO_ROOT or REPO_ROOT in target.parents:
        raise Blocked(reason)
    return target


def line_identity(value):
    """Collapse purely numeric formatting, never alter original source rows."""
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        parsed = Decimal(raw)
    except InvalidOperation:
        # For qualitative markets the line field may be nonnumeric.
        return raw.casefold()
    if not parsed.is_finite():
        raise Blocked("INVALID_NUMERIC_MARKET_LINE")
    return "0" if parsed == 0 else str(parsed.normalize())


def utc(s):
    try: x=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    except (ValueError,AttributeError) as e:raise Blocked("INVALID_UTC") from e
    if x.utcoffset()!=dt.timedelta(0):raise Blocked("NON_UTC_CLOCK")
    return x

def payload_hash(obj):
    data=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def make_records(source_bytes,meta):
    if not source_bytes or len(source_bytes)>10_000_000:raise Blocked("INVALID_SOURCE_BYTES")
    digest=hashlib.sha256(source_bytes).hexdigest()
    if digest!=meta.get("source_sha256"):raise Blocked("SOURCE_HASH_MISMATCH")
    kind=meta.get("snapshot_kind")
    if kind not in ("TAKE","CLOSE"):raise Blocked("INVALID_CAPTURE_KIND")
    cap=utc(meta["captured_at_utc"]);kick=utc(meta["kickoff_utc"])
    if not cap<kick:raise Blocked("AFTER_KICKOFF")
    lag=(kick-cap).total_seconds()
    if kind=="CLOSE" and not 0<lag<=600:
        raise Blocked("NOT_WITHIN_10_MIN_CLOSE_WINDOW")
    if "observed_at_utc" in meta:
        observed = utc(meta["observed_at_utc"])
        if observed >= kick:
            raise Blocked("PROVIDER_CLOCK_NOT_PREGAME")
        if observed > cap:
            raise Blocked("PROVIDER_CLOCK_AFTER_LOCAL_CAPTURE")
    try:reader=csv.DictReader(io.StringIO(source_bytes.decode("utf-8-sig")))
    except UnicodeDecodeError as e:raise Blocked("NON_UTF8_SOURCE") from e
    fields = reader.fieldnames or ()
    if len(fields) != len(set(fields)):
        raise Blocked("DUPLICATE_CSV_HEADER")
    if not set(FIELDS).issubset(fields):
        raise Blocked("MISSING_QUOTE_FIELDS")
    rows=[];seen=set()
    for i,r in enumerate(reader,2):
        if None in r or any(k not in FIELDS for k in r):
            raise Blocked(f"MALFORMED_CSV_ROW_{i}")
        if any(r.get(f) is None or not r.get(f).strip() for f in FIELDS[:-1]):
            raise Blocked(f"MISSING_QUOTE_FIELD_ROW_{i}")
        if r["event_id"]!=meta.get("event_id"):raise Blocked("EVENT_MISMATCH")
        try:american=int(r["price_american"])
        except ValueError as e:raise Blocked("INVALID_AMERICAN_ODDS") from e
        if abs(american)<100 or abs(american)>100000:raise Blocked("INVALID_AMERICAN_ODDS")
        key=(r["book"].strip().casefold(),r["event_id"].strip(),
             r["market_key"].strip().casefold(),r["selection"].strip().casefold(),
             line_identity(r["line"]))
        if key in seen:raise Blocked("DUPLICATE_SAME_MARKET_LINE")
        seen.add(key)
        # Row's provider ID is a claim, not provider-authenticated metadata.
        row={f:(r.get(f) or "").strip() for f in FIELDS}
        row["provider_quote_id"]=row["provider_quote_id"] or "NOT_CAPTURED"
        row["price_american"]=american
        row["source_sha256"]=digest
        row["captured_at_utc"]=meta["captured_at_utc"]
        row["observed_at_utc"]=meta.get("observed_at_utc")
        row["kickoff_utc"]=meta["kickoff_utc"]
        row["snapshot_kind"]=kind
        row["evidence_state"]="PAPER_SOURCE_CLAIM_ONLY"
        row["close_window_seconds"]=round(lag) if kind=="CLOSE" else None
        row["id"]=payload_hash({k:row[k] for k in sorted(row) if k!="id"})
        rows.append(row)
    if not rows:raise Blocked("EMPTY_QUOTE_SOURCE")
    return rows

def verify_chain(path):
    previous="0"*64
    items=[]
    if not path.exists():return items
    with path.open(encoding="utf-8") as f:
        for line_number,line in enumerate(f,1):
            try:entry=json.loads(line)
            except json.JSONDecodeError as e:raise Blocked("BROKEN_LEDGER_JSON") from e
            if entry.get("previous_hash")!=previous:raise Blocked("BROKEN_LEDGER_CHAIN")
            expected=payload_hash({"previous_hash":previous,"quote":entry["quote"]})
            if entry.get("entry_hash")!=expected:raise Blocked("BROKEN_LEDGER_HASH")
            previous=expected
            items.append(entry)
    return items

def append(path,records):
    # Single-writer private local use only; use external locking for concurrency.
    path=private_path(path, "PRIVATE_LEDGER_MUST_BE_OUTSIDE_PUBLIC_REPO")
    prior=verify_chain(path)
    existing={e["quote"]["id"] for e in prior}
    if len({r["id"] for r in records})!=len(records) or any(r["id"] in existing for r in records):
        raise Blocked("DUPLICATE_SNAPSHOT_IMPORT")
    prev=prior[-1]["entry_hash"] if prior else "0"*64
    lines=[]
    for r in records:
        entry={"previous_hash":prev,"quote":r}
        entry["entry_hash"]=payload_hash(entry)
        lines.append(json.dumps(entry,sort_keys=True,ensure_ascii=False))
        prev=entry["entry_hash"]
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as f:
        f.write("\n".join(lines)+"\n")
        f.flush()
    return {"status":"PAPER_SOURCE_CLAIM_ONLY","added":len(records),"total":len(prior)+len(records),
            "last_local_hash":prev,"warning":"Local hash chain is not third-party signed or immutable."}

def from_manifest(path):
    path=private_path(path, "PRIVATE_MANIFEST_MUST_BE_OUTSIDE_PUBLIC_REPO")
    meta=json.loads(path.read_text(encoding="utf-8"))
    rel=Path(meta["source_path"]);p=(path.parent/rel).resolve()
    if rel.is_absolute() or not p.is_relative_to(path.parent) or not p.is_file():
        raise Blocked("SOURCE_PATH_ESCAPE")
    return make_records(p.read_bytes(),meta)

def main():
    a=argparse.ArgumentParser();a.add_argument("manifest",type=Path)
    a.add_argument("--private-ledger",required=True,type=Path);args=a.parse_args()
    print(json.dumps(append(args.private_ledger,from_manifest(args.manifest)),indent=2))
if __name__=="__main__":main()
