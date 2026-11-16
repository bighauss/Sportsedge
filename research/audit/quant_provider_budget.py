"""Durable offline provider-request budget for PRIVATE SportsEdge capture jobs.

An admin calls reserve() BEFORE issuing a permitted request, then notes any 429
with record_429(). This file NEVER calls an API, authenticates the origin of a
quote or proves chronological sportsbook availability. SQLite locking makes a
process restart or two competing capture workers share a conservative budget.
No public dashboard may invoke this as a source accessor. PAPER / 0u only.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import sqlite3

REPO_ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r'^[A-Z][A-Z0-9_]{1,39}$')
REQUEST_ID = re.compile(r'^[A-Za-z0-9._-]{8,128}$')


def _utc(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        parsed = (datetime.fromisoformat(value.replace('Z', '+00:00'))
                  if isinstance(value, str) else value)
    except ValueError as exc:
        raise ValueError('INVALID_REQUEST_CLOCK') from exc
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError('UTC_REQUEST_CLOCK_REQUIRED')
    return parsed.astimezone(timezone.utc)


def _identity(provider: str, endpoint: str | None = None, request_id: str | None = None) -> None:
    if not isinstance(provider, str) or not NAME.fullmatch(provider):
        raise ValueError('PROVIDER_LABEL_INVALID')
    if endpoint is not None and (not isinstance(endpoint, str) or not NAME.fullmatch(endpoint)):
        raise ValueError('ENDPOINT_LABEL_INVALID')
    if request_id is not None and (not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id)):
        raise ValueError('REQUEST_ID_INVALID')


def _budget(max_hour: int, max_day: int, cache_age_seconds: int | float | None,
            min_cache_seconds: int) -> None:
    if any(type(v) is not int or v < 1 for v in (max_hour, max_day)):
        raise ValueError('INVALID_REQUEST_QUOTAS')
    if type(min_cache_seconds) is not int or min_cache_seconds < 0:
        raise ValueError('INVALID_CACHE_POLICY')
    if cache_age_seconds is not None and (isinstance(cache_age_seconds, bool) or
            not isinstance(cache_age_seconds, (int,float)) or
            not math.isfinite(cache_age_seconds) or cache_age_seconds < 0):
        raise ValueError('INVALID_CACHE_AGE')


@contextmanager
def _locked_database(database: str | Path):
    dest = Path(database)
    if dest.is_symlink() or dest.parent.is_symlink():
        raise ValueError('SYMLINK_BUDGET_DATABASE_REFUSED')
    resolved = dest.resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise ValueError('BUDGET_DB_INSIDE_PUBLIC_REPOSITORY')
    if not resolved.parent.is_dir():
        raise ValueError('PRIVATE_BUDGET_DIRECTORY_MISSING')
    if resolved.parent.stat().st_mode & 0o077:
        raise ValueError('BUDGET_DIRECTORY_NOT_PRIVATE')
    # Create only if absent, with private permissions. Never truncate a ledger.
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(resolved, flags, 0o600)
    try:
        if os.fstat(fd).st_mode & 0o077:
            raise ValueError('BUDGET_DATABASE_NOT_PRIVATE')
    finally:
        os.close(fd)
    conn = sqlite3.connect(str(resolved), isolation_level=None, timeout=30)
    try:
        conn.execute('PRAGMA busy_timeout=30000')
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''CREATE TABLE IF NOT EXISTS requests (
            provider TEXT NOT NULL, request_id TEXT NOT NULL,
            endpoint TEXT NOT NULL, requested_epoch INTEGER NOT NULL,
            PRIMARY KEY(provider, request_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS backoff (
            provider TEXT PRIMARY KEY, until_epoch INTEGER NOT NULL)''')
        yield conn
        conn.execute('COMMIT')
    except BaseException:
        if conn.in_transaction:
            conn.execute('ROLLBACK')
        raise
    finally:
        conn.close()


def _decision(status: str, allowed: bool, provider: str) -> dict:
    return {'status': status, 'allowed': allowed, 'provider': provider,
            'source_authenticated': False, 'official_counted': 0,
            'approved_stake_u': 0}


def reserve(database: str | Path, *, provider: str, endpoint: str,
            request_id: str, max_hour: int, max_day: int,
            cache_age_seconds: float | None, min_cache_seconds: int = 300,
            now_utc: str | datetime | None = None) -> dict:
    """Atomically consume quota BEFORE a permitted admin API call.

    A reservation costs budget even if the worker crashes or the call fails.
    Never interpret ``allowed`` as authentication or permission to scrape.
    """
    _identity(provider, endpoint, request_id)
    _budget(max_hour, max_day, cache_age_seconds, min_cache_seconds)
    moment = _utc(now_utc)
    now = int(moment.timestamp())
    with _locked_database(database) as conn:
        existing = conn.execute('SELECT 1 FROM requests WHERE provider=? AND request_id=?',
                                (provider, request_id)).fetchone()
        if existing:
            return _decision('DUPLICATE_REQUEST_ID_BLOCKED', False, provider)
        future = conn.execute('SELECT MAX(requested_epoch) FROM requests WHERE provider=?',
                              (provider,)).fetchone()[0]
        if future is not None and future > now:
            return _decision('REQUEST_CLOCK_ROLLBACK_BLOCKED', False, provider)
        if cache_age_seconds is not None and cache_age_seconds <= min_cache_seconds:
            return _decision('USE_EXISTING_PRIVATE_CACHE', False, provider)
        throttled = conn.execute('SELECT until_epoch FROM backoff WHERE provider=?',
                                 (provider,)).fetchone()
        if throttled and now < throttled[0]:
            return _decision('PROVIDER_429_BACKOFF', False, provider)
        hour = conn.execute('SELECT COUNT(*) FROM requests WHERE provider=? AND requested_epoch>?',
                            (provider, now-3600)).fetchone()[0]
        day = conn.execute('SELECT COUNT(*) FROM requests WHERE provider=? AND requested_epoch>?',
                           (provider, now-86400)).fetchone()[0]
        if day >= max_day:
            return _decision('DAILY_REQUEST_BUDGET_EXHAUSTED', False, provider)
        if hour >= max_hour:
            return _decision('HOURLY_REQUEST_BUDGET_EXHAUSTED', False, provider)
        conn.execute('INSERT INTO requests VALUES (?, ?, ?, ?)',
                     (provider, request_id, endpoint, now))
        return _decision('ADMIN_REQUEST_RESERVED_PAPER_ONLY', True, provider)


def record_429(database: str | Path, *, provider: str, request_id: str,
               retry_after_seconds: int, now_utc: str | datetime | None = None) -> dict:
    """Persist an operator-supplied Retry-After cooldown, NEVER shorten it.

    This does not authenticate a server's response; the calling adapter must
    independently verify the response and supplied Retry-After semantics.
    """
    _identity(provider, request_id=request_id)
    if type(retry_after_seconds) is not int or not 1 <= retry_after_seconds <= 86400:
        raise ValueError('INVALID_RETRY_AFTER')
    now = int(_utc(now_utc).timestamp())
    with _locked_database(database) as conn:
        exists = conn.execute('SELECT requested_epoch FROM requests WHERE provider=? AND request_id=?',
                              (provider, request_id)).fetchone()
        if not exists or exists[0] > now:
            raise ValueError('UNKNOWN_OR_FUTURE_REQUEST_FOR_429')
        before = conn.execute('SELECT until_epoch FROM backoff WHERE provider=?',
                              (provider,)).fetchone()
        until = max(now+retry_after_seconds, before[0] if before else 0)
        conn.execute('INSERT INTO backoff(provider,until_epoch) VALUES (?, ?) '
                     'ON CONFLICT(provider) DO UPDATE SET until_epoch=excluded.until_epoch',
                     (provider, until))
        return {**_decision('429_BACKOFF_RECORDED_PAPER_ONLY', False, provider),
                'backoff_until_utc': datetime.fromtimestamp(until,timezone.utc).isoformat()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, help='Private SQLite file outside repo')
    parser.add_argument('--provider', required=True, help='Registered admin source label, not URL')
    parser.add_argument('--request-id', required=True)
    parser.add_argument('--endpoint', help='Approved endpoint label (not URL)')
    parser.add_argument('--max-hour', type=int)
    parser.add_argument('--max-day', type=int)
    parser.add_argument('--cache-age-seconds', type=float)
    parser.add_argument('--cache-max-fresh-seconds', type=int, default=300)
    parser.add_argument('--record-429-seconds', type=int)
    args = parser.parse_args(argv)
    if args.record_429_seconds is None:
        if args.endpoint is None or args.max_hour is None or args.max_day is None:
            parser.error('reserve requires endpoint, max-hour and max-day')
        result = reserve(args.database,provider=args.provider,endpoint=args.endpoint,
                         request_id=args.request_id,max_hour=args.max_hour,
                         max_day=args.max_day,cache_age_seconds=args.cache_age_seconds,
                         min_cache_seconds=args.cache_max_fresh_seconds)
    else:
        result = record_429(args.database,provider=args.provider,
                            request_id=args.request_id,
                            retry_after_seconds=args.record_429_seconds)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
