"""Offline private media preflight CLI. No network, upload, publication or asset copying."""
import argparse
import json
import math
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from tools.media.asset_intake_contract import MediaHold, preflight

REPO_ROOT = Path(__file__).resolve().parents[2]


def _unique_pairs(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise MediaHold("RECEIPT_JSON_DUPLICATE_KEY")
        data[key] = value
    return data


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise MediaHold("RECEIPT_JSON_NONFINITE")
    if isinstance(value, dict):
        for part in value.values():
            _finite(part)
    elif isinstance(value, list):
        for part in value:
            _finite(part)


def private_file(path):
    p = Path(path)
    if not p.is_absolute():
        raise MediaHold("PRIVATE_ABSOLUTE_PATH_REQUIRED")
    if p.is_symlink() or any(component.is_symlink() for component in p.parents):
        raise MediaHold("SYMLINK_REJECTED")
    if p.is_dir():
        raise MediaHold("REGULAR_FILE_REQUIRED")
    lexical = Path(os.path.abspath(p))
    resolved = p.resolve()
    if any(candidate == REPO_ROOT or REPO_ROOT in candidate.parents
           for candidate in (lexical, resolved)):
        raise MediaHold("PUBLIC_REPOSITORY_INPUT_REFUSED")
    parent = p.parent
    st = parent.stat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or (
            stat.S_IMODE(st.st_mode) != 0o700):
        raise MediaHold("OWNER_PRIVATE_DIRECTORY_0700_REQUIRED")
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise MediaHold("REGULAR_FILE_REQUIRED")
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
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
        r = json.loads(
            receipt_bytes.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                MediaHold("RECEIPT_JSON_NONFINITE")))
        _finite(r)
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise MediaHold("RECEIPT_JSON_INVALID") from exc
    if not isinstance(r, dict):
        raise MediaHold("RECEIPT_JSON_OBJECT_REQUIRED")
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
