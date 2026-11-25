"""Fail-closed prospective challenger collector. Never mutates the card or ledger."""
import argparse, json
from pathlib import Path
from .evidence_io import atomic_publish

def discover_and_record(card_path, capture_dir, out_dir):
    capture_dir, out_dir = Path(capture_dir), Path(out_dir)
    names = sorted(p.name for p in capture_dir.iterdir()) if capture_dir.is_dir() else []
    status = dict(state="BLOCK_CAPTURE_FILES_NOT_CONTRACTED", filenames=names, forecasts_written=0, approved_stake_u=0, reason="Ratings and prior-game files are not identified by an exact contract; no forecast inferred")
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_publish(out_dir / "status.json", (json.dumps(status, sort_keys=True) + "\n").encode())
    return status

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--card", required=True)
    p.add_argument("--capture-dir", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    try:
        status = discover_and_record(a.card, a.capture_dir, a.out)
    except Exception as exc:
        status = dict(state="BLOCK_" + type(exc).__name__, forecasts_written=0, approved_stake_u=0)
    print(json.dumps(status, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
