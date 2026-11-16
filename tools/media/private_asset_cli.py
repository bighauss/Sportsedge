"""Offline private media preflight CLI. No network, upload, publication or asset copying."""
import argparse
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from tools.media.asset_intake_contract import MediaHold, preflight

def private_file(path):
    p = Path(path)
    if p.is_symlink():
        raise MediaHold("SYMLINK_REJECTED")
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise MediaHold("REGULAR_FILE_REQUIRED")
        if info.st_mode & 0o077:
            raise MediaHold("PRIVATE_FILE_MODE_REQUIRED")
        if info.st_size > 25_000_000:
            raise MediaHold("FILE_TOO_LARGE")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(25_000_001)
        if len(raw) > 25_000_000:
            raise MediaHold("FILE_TOO_LARGE")
        return raw
    finally:
        os.close(fd)

def evaluate(asset, receipt, now_utc):
    raw = private_file(asset)
    receipt_bytes = private_file(receipt)
    if len(receipt_bytes) > 100_000:
        raise MediaHold("RECEIPT_TOO_LARGE")
    try:
        r = json.loads(receipt_bytes)
    except (ValueError, UnicodeError) as exc:
        raise MediaHold("RECEIPT_JSON_INVALID") from exc
    return preflight(raw, r, now_utc=now_utc)

def main(argv=None):
    parser = argparse.ArgumentParser(description="Private local asset preflight; no upload or publishing")
    parser.add_argument("--asset", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.asset, args.receipt, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    except (MediaHold, OSError, TypeError) as exc:
        # Do not expose private paths, filenames, exception details or receipt contents.
        print(json.dumps({"status": "HOLD", "reason": exc.args[0] if isinstance(exc, MediaHold) else "PRIVATE_INPUT_ERROR"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == "__main__":
    sys.exit(main())
