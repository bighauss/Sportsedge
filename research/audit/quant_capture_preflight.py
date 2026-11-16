"""SportsEdge fail-closed local snapshot preflight; NO network or model mutation.

Reads an existing provider capture file, validates timestamps and offer
inventory, then saves a create-only manifest. It does NOT authenticate the
source or collect any sportsbook quote. A scheduler/dashboard should call
this only in an admin/private job, never for public traffic.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from quant_foundation import when
from quant_evidence import digest_ok, market_census


def quota_decision(now_utc: str, observed_calls: list[str], *, max_hour: int,
                   max_day: int, cache_age_seconds: float | None,
                   min_cache_seconds: int = 300) -> dict:
    """Decision ONLY; durable request counters must come from external storage.

    Never makes a network call. Rejects future/naive counter times.
    """
    now = when(now_utc)
    if max_hour < 1 or max_day < 1 or min_cache_seconds < 0:
        raise ValueError('INVALID_QUOTA_POLICY')
    if cache_age_seconds is not None and cache_age_seconds < 0:
        raise ValueError('INVALID_CACHE_AGE')
    if cache_age_seconds is not None and cache_age_seconds <= min_cache_seconds:
        return {'allowed': False, 'code': 'USE_CACHE'}
    within_hour = within_day = 0
    for value in observed_calls:
        tick = when(value)
        if tick > now:
            raise ValueError('FUTURE_REQUEST_LOG')
        diff = (now-tick).total_seconds()
        within_hour += diff < 3600
        within_day += diff < 86400
    if within_day >= max_day:
        return {'allowed': False, 'code': 'DAY_QUOTA_EXHAUSTED'}
    if within_hour >= max_hour:
        return {'allowed': False, 'code': 'HOUR_QUOTA_EXHAUSTED'}
    return {'allowed': True, 'code': 'CAN_REQUEST_ADMIN_ONLY'}


def manifest_for_capture(source: bytes, *, asof_utc: str,
                         provider: str, claim_source_authenticated: bool = False) -> dict:
    """Hash existing bytes and keep all rows; authenticity is always unproven."""
    if claim_source_authenticated:
        raise ValueError('CANNOT_ASSERT_PROVIDER_AUTHENTICITY_FROM_FILE')
    stamp = when(asof_utc)
    if not provider or not provider.strip():
        raise ValueError('SOURCE_PROVIDER_MISSING')
    rows = list(csv.DictReader(source.decode('utf-8-sig').splitlines()))
    if not rows:
        raise ValueError('EMPTY_CAPTURE')
    flagged = []
    for rownum, row in enumerate(rows, 2):
        try:
            freeze = when(row['captured_utc'])
            kickoff = when(row['game_start_utc'])
            if freeze > stamp:
                raise ValueError('CAPTURE_TIME_AFTER_MANIFEST_ASOF')
            if freeze >= kickoff:
                raise ValueError('CAPTURE_NOT_PREGAME')
            if not digest_ok(row.get('quote_sha256')):
                raise ValueError('QUOTE_DIGEST_MISSING')
            if 'prop' in str(row.get('market', '')).lower() and not row.get('player_id'):
                raise ValueError('UNBOUND_PLAYER_ID')
        except (ValueError, KeyError, TypeError) as exc:
            flagged.append({'row': rownum, 'reason': str(exc)})
    census = market_census(rows)
    return {'status': 'PAPER_0U_SNAPSHOT_PRECHECK', 'provider_label': provider.strip(),
            'source_sha256': hashlib.sha256(source).hexdigest(),
            'asof_utc': stamp.isoformat(), 'row_count': len(rows),
            'rejected_rows': flagged, 'market_inventory_counts': census['status_counts'],
            'source_authenticated': False,
            'admission_allowed': False,
            'reason': ('ROW_GATES_FAILED' if flagged else 'PROVIDER_AUTHENTICATION_NOT_ESTABLISHED'),
            'disclaimer': 'Manifest of locally supplied bytes only; not a bookmaker receipt or betting authorization.'}


def write_create_only(path: str | Path, record: dict) -> None:
    """Create-only file. Owner must store in a private, access-controlled tree."""
    target = Path(path)
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError('SYMLINK_PATH_REFUSED')
    data = (json.dumps(record, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(target, flags, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
    finally:
        os.close(fd)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input_csv')
    p.add_argument('--asof-utc', required=True)
    p.add_argument('--provider', required=True)
    p.add_argument('--manifest', required=True)
    args = p.parse_args(argv)
    source = Path(args.input_csv).read_bytes()
    manifest = manifest_for_capture(source, asof_utc=args.asof_utc,
                                    provider=args.provider)
    write_create_only(args.manifest, manifest)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
