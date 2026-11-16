# Private closing-price archive (PAPER only)

Never commit actual DraftKings screenshots, transcriptions, CSV, quote IDs,
hash manifests, or the output ledger to this public repository.

For each event/phase, create a PRIVATE quoted CSV with columns:
book,event_id,market_key,selection,line,price_american,
provider_event_id,provider_market_id,provider_quote_id

Provider IDs may be entered as NOT_CAPTURED where unavailable; this does NOT
authenticate the quote or allow an OFFICIAL EV claim. Preserve the EXACT line
and side (including alternate lines) and keep original screenshots separately.

Example manifest placed next to that CSV (values below are illustrative ONLY):
{
  "source_path": "capture.csv",
  "source_sha256": "<64 lowercase SHA256 of capture.csv bytes>",
  "event_id": "EXAMPLE-EVENT",
  "snapshot_kind": "CLOSE",
  "captured_at_utc": "2026-11-16T01:15:00Z",
  "kickoff_utc": "2026-11-16T01:20:00Z"
}

Run:
  python ledger/close_snapshot_archive.py /private/capture_manifest.json --private-ledger /private/snapshots.ndjson
  cd ledger && python test_close_snapshot_archive.py

Source manifests and private ledger destinations are refused if they resolve
inside the SportsEdge public Git checkout, regardless of the process working
directory or symlink paths. Original CSV rows and formatting are never edited.
The intake now fails on duplicate CSV headers, overlong rows, non-finite
numeric lines, duplicate selections whose numeric lines differ only in
formatting (e.g. `49.5` vs `+049.500`), and a purported provider observation
timestamp later than local capture. Distinct alternate lines remain distinct.
Optional provider-observation metadata and the local hash chain still
**do not** independently authenticate a provider or prove historical time.

CLOSE requires time before kickoff and no farther than 10 minutes from start;
TAKE permits earlier capture. Original CSV byte hashes are verified. The
output is a local chained JSONL append, NOT a trusted clock, digitally signed
third-party receipt, tamper-proof storage or verified provider quote. Use
external access controls and independent backups; avoid simultaneous writers.
This is the intake predecessor to PR #68's private CLV/settlement pipeline.
As-of source archives and closing snapshots for every market must actually
be collected by Muse/owner or an authorized feed before CLV can be calculated.
