"""SportsEdge fail-closed local snapshot preflight; NO network or model mutation.

Reads an existing provider capture file, validates timestamps and offer
inventory, then saves a create-only manifest. It does NOT authenticate the
source or collect any sportsbook quote. A scheduler/dashboard should call
this only in an admin/private job, never for public traffic.
"""
from __future__ import annotations

import argparse
import csv
import io
import datetime as dt
import hashlib
import json
import os
import math
from collections import Counter
from pathlib import Path

from quant_foundation import when
from quant_evidence import digest_ok, market_census

REPO_ROOT = Path(__file__).resolve().parents[2]


def require_private_path(value):
    """A source or output must not resolve inside this public repository."""
    resolved = Path(value).resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise ValueError('PRIVATE_CAPTURE_PATH_INSIDE_PUBLIC_REPO')
    return resolved



def quota_decision(now_utc: str, observed_calls: list[str], *, max_hour: int,
                   max_day: int, cache_age_seconds: float | None,
                   min_cache_seconds: int = 300) -> dict:
    """Decision ONLY; durable request counters must come from external storage.

    Never makes a network call. Rejects future/naive counter times.
    """
    now = when(now_utc)
    # Reject NaN/Infinity and bools. Otherwise a NaN cache age bypasses the
    # stale-cache gate and a fractional quota silently changes rate limits.
    if any(type(n) is not int for n in (max_hour, max_day, min_cache_seconds)):
        raise ValueError('INVALID_QUOTA_POLICY')
    if max_hour < 1 or max_day < 1 or min_cache_seconds < 0:
        raise ValueError('INVALID_QUOTA_POLICY')
    if cache_age_seconds is not None:
        if (isinstance(cache_age_seconds, bool)
                or not isinstance(cache_age_seconds, (int,float))
                or not math.isfinite(cache_age_seconds)
                or cache_age_seconds < 0):
            raise ValueError('INVALID_CACHE_AGE')
    within_hour = within_day = 0
    for value in observed_calls:
        tick = when(value)
        if tick > now:
            raise ValueError('FUTURE_REQUEST_LOG')
        diff = (now-tick).total_seconds()
        within_hour += diff < 3600
        within_day += diff < 86400
    if cache_age_seconds is not None and cache_age_seconds <= min_cache_seconds:
        return {'allowed': False, 'code': 'USE_CACHE'}
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
    if not isinstance(provider,str) or not provider.strip():
        raise ValueError('SOURCE_PROVIDER_MISSING')
    if not isinstance(source,bytes) or not source or len(source)>20_000_000:
        raise ValueError('INVALID_SOURCE_BYTES')
    try:
        # csv.DictReader silently skips blank records and allows colliding
        # headers such as captured_utc vs captured_utc<space>. Use a strict
        # positional parser so the original denominator cannot silently shrink.
        reader = csv.reader(io.StringIO(source.decode('utf-8-sig'), newline=''),
                            strict=True)
        records = list(reader)
        fields = records[0] if records else []
        if not fields or any(not name.strip() for name in fields):
            raise ValueError('INVALID_CAPTURE_CSV_HEADERS')
        if len(fields) != len(set(name.strip().casefold() for name in fields)):
            raise ValueError('DUPLICATE_CAPTURE_CSV_HEADERS')
        if any(name != name.strip() for name in fields):
            raise ValueError('UNNORMALIZED_CAPTURE_CSV_HEADERS')
        if any(len(record) > len(fields) for record in records[1:]):
            raise ValueError('CAPTURE_CSV_EXTRA_FIELDS')
        if any(len(record) < len(fields) for record in records[1:]):
            raise ValueError('CAPTURE_CSV_MISSING_OR_BLANK_RECORD')
        rows = [dict(zip(fields, record)) for record in records[1:]]
    except UnicodeError as exc:
        raise ValueError('NON_UTF8_CAPTURE') from exc
    except csv.Error as exc:
        raise ValueError('MALFORMED_CAPTURE_CSV') from exc
    if not rows:
        raise ValueError('EMPTY_CAPTURE')
    if any(None in row for row in rows):
        raise ValueError('CAPTURE_CSV_EXTRA_FIELDS')
    flagged = []
    for rownum, row in enumerate(rows, 2):
        try:
            freeze = when(row['captured_utc'])
            kickoff = when(row['game_start_utc'])
            if freeze > stamp:
                raise ValueError('CAPTURE_TIME_AFTER_MANIFEST_ASOF')
            if freeze >= kickoff:
                raise ValueError('CAPTURE_NOT_PREGAME')
            # Optional provider and model clocks, when supplied, must still be
            # temporally consistent. A missing clock never proves provenance.
            published = (when(row['source_published_utc'])
                         if row.get('source_published_utc') else None)
            source_captured = (when(row['source_captured_utc'])
                               if row.get('source_captured_utc') else None)
            if published is not None and published > freeze:
                raise ValueError('SOURCE_PUBLISHED_AFTER_LOCAL_CAPTURE')
            if source_captured is not None and source_captured > freeze:
                raise ValueError('SOURCE_CAPTURED_AFTER_LOCAL_CAPTURE')
            if (published is not None and source_captured is not None
                    and published > source_captured):
                raise ValueError('SOURCE_CAPTURE_PRECEDES_PUBLICATION')
            if row.get('model_asof_utc'):
                model_time = when(row['model_asof_utc'])
                if model_time >= kickoff:
                    raise ValueError('MODEL_FORECAST_NOT_PREGAME')
                if (row.get('feature_available_utc')
                        and when(row['feature_available_utc']) > model_time):
                    raise ValueError('FEATURE_AVAILABLE_AFTER_MODEL_FORECAST')
                if (row.get('fitted_until_utc')
                        and when(row['fitted_until_utc']) >= model_time):
                    raise ValueError('MODEL_FITTED_USING_FUTURE_INFORMATION')
            if not digest_ok(row.get('quote_sha256')):
                raise ValueError('QUOTE_DIGEST_MISSING')
            if 'prop' in str(row.get('market', '')).lower() and not row.get('player_id'):
                raise ValueError('UNBOUND_PLAYER_ID')
        except (ValueError, KeyError, TypeError) as exc:
            flagged.append({'row': rownum, 'reason': str(exc)})
    # All copies of an ambiguous original offer are marked, including the
    # first occurrence; no first-row-wins selection or silent deletion.
    # Require a genuine book and side before comparing offer identities:
    # a family inventory alone does not describe a specific priced offer.
    from decimal import Decimal, InvalidOperation
    identity_rows = {}
    for rownum, row in enumerate(rows, 2):
        if not all(str(row.get(field) or '').strip() for field in (
                'sport', 'event_id', 'book', 'period', 'market', 'side',
                'captured_utc')):
            continue
        line = str(row.get('line') or '').strip()
        if line:
            try:
                numeric = Decimal(line)
                if not numeric.is_finite():
                    raise InvalidOperation
                line = ('0' if numeric == 0 else format(numeric.normalize(), 'f'))
            except (InvalidOperation, ValueError):
                flagged.append({'row': rownum, 'reason': 'INVALID_OFFER_LINE'})
                continue
        # Normalization is for duplicate detection only; the source bytes and
        # exact original field values remain untouched in the capture manifest.
        book = str(row['book']).strip().casefold()
        book = {'dk': 'draftkings', 'draft kings': 'draftkings',
                'fd': 'fanduel', 'fan duel': 'fanduel'}.get(book, book)
        try:
            captured_time = when(str(row['captured_utc'])).isoformat()
        except (ValueError, TypeError):
            flagged.append({'row': rownum, 'reason': 'INVALID_IDENTITY_CAPTURE_TIME'})
            continue
        key = tuple(
            book if field == 'book' else
            captured_time if field == 'captured_utc' else
            str(row.get(field) or '').strip().casefold()
            for field in ('sport', 'event_id', 'book', 'period', 'market',
                          'side', 'captured_utc', 'player_id', 'team_id', 'stat')
        ) + (line,)
        identity_rows.setdefault(key, []).append(rownum)
    for group in identity_rows.values():
        if len(group) > 1:
            flagged.extend({'row': rownum,
                            'reason': 'DUPLICATE_OR_CONFLICTING_OFFER_IDENTITY'}
                           for rownum in group)
    flagged.sort(key=lambda entry: (entry['row'], entry['reason']))
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
    require_private_path(target)
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
    require_private_path(args.input_csv)
    require_private_path(args.manifest)
    source = Path(args.input_csv).read_bytes()
    manifest = manifest_for_capture(source, asof_utc=args.asof_utc,
                                    provider=args.provider)
    write_create_only(args.manifest, manifest)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
