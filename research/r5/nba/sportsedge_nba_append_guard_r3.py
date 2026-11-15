#!/usr/bin/env python3
"""SportsEdge guarded game-final CSV admission; READ ONLY, research/PAPER lane.

Usage:
  python sportsedge_nba_append_guard_r3.py audit ratings_games.csv --as-of 2026-11-13
  python sportsedge_nba_append_guard_r3.py replay base.csv delta.csv merged.csv --as-of 2026-11-13

Exit 0 = structural PASS; 4 = FAIL; 2 = invocation error.
PASS never authenticates ESPN/DK provenance and NEVER promotes a model or releases bets.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import sys
from collections import Counter
from pathlib import Path

HEADER = ('sport', 'date', 'home', 'away', 'home_pts', 'away_pts', 'neutral', 'poss')
SPORTS = {'NBA', 'NHL', 'NFL', 'CFB', 'CBB', 'MLB', 'PGA'}
MAX_ERRORS = 100


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_csv(path: Path, data: bytes, *, as_of: dt.date | None = None) -> dict:
    errors: list[str] = []
    out: dict = {'path': str(path), 'sha256': digest(data), 'bytes': len(data),
                 'rows': 0, 'counts': {}, 'latest_by_sport': {}, 'errors': errors}
    def error(message: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(message)
    if not data:
        error('empty file')
        return out
    if data.startswith(b'\xef\xbb\xbf'):
        error('unexpected UTF-8 BOM; pinned byte format requires BOM-free text')
    if not data.endswith(b'\n'):
        error('missing trailing newline')
    try:
        content = data.decode('utf-8')
    except UnicodeDecodeError:
        error('file is not valid UTF-8')
        return out
    try:
        source = io.StringIO(content, newline='')
        reader = csv.reader(source, strict=True)
        header = next(reader, None)
        if header != list(HEADER):
            error(f'header mismatch: expected {list(HEADER)!r}, got {header!r}')
            return out
        seen: set[tuple[str, str, str, str]] = set()
        counts: Counter[str] = Counter()
        latest: dict[str, str] = {}
        for lineno, cells in enumerate(reader, 2):
            if not cells and lineno > 2:
                error(f'row {lineno}: blank record')
                continue
            if len(cells) != len(HEADER):
                error(f'row {lineno}: ragged cell count {len(cells)} (expected {len(HEADER)})')
                continue
            row = dict(zip(HEADER, cells))
            out['rows'] += 1
            sport, d, home, away = (row[k] for k in ('sport','date','home','away'))
            for key in ('sport', 'date', 'home', 'away'):
                value = row[key]
                if not value or value != value.strip() or any(ord(ch) < 32 for ch in value):
                    error(f'row {lineno}: invalid {key} text')
            if sport not in SPORTS:
                error(f'row {lineno}: unknown sport {sport!r}')
            try:
                parsed = dt.date.fromisoformat(d)
                if parsed.isoformat() != d:
                    raise ValueError('non-canonical')
                if as_of is not None and parsed > as_of:
                    error(f'row {lineno}: event date {d} later than as-of {as_of}')
            except ValueError:
                error(f'row {lineno}: invalid ISO date {d!r}')
            if home.casefold() == away.casefold():
                error(f'row {lineno}: identical home/away')
            ident = (sport.casefold(), d, home.casefold(), away.casefold())
            if ident in seen:
                error(f'row {lineno}: duplicate sport/date/home/away identity {ident!r}')
            seen.add(ident)
            for field in ('home_pts', 'away_pts'):
                value = row[field]
                if not value.isascii() or not value.isdecimal() or value != str(int(value)):
                    error(f'row {lineno}: {field} must be canonical nonnegative integer')
            if row['neutral'] not in {'0', '1'}:
                error(f'row {lineno}: neutral must be 0 or 1')
            poss = row['poss']
            if poss != '':
                try:
                    v = float(poss)
                    if not math.isfinite(v) or v <= 0:
                        raise ValueError('nonpositive or nonfinite')
                except ValueError:
                    error(f'row {lineno}: poss must be blank or finite positive number')
            counts[sport] += 1
            if not latest.get(sport) or d > latest[sport]:
                latest[sport] = d
        out['counts'] = dict(sorted(counts.items()))
        out['latest_by_sport'] = dict(sorted(latest.items()))
    except (csv.Error, UnicodeError, ValueError, OverflowError) as exc:
        error(f'CSV parsing failed: {exc}')
    return out


def replay_concat(base: bytes, delta: bytes) -> tuple[bytes | None, str | None]:
    # Delta must be an independent, complete CSV with the same exact header.
    # Byte-level verification deliberately avoids csv.writer normalizing CRLF.
    if not base.endswith(b'\n') or not delta.endswith(b'\n'):
        return None, 'base/delta must end in newlines'
    i = delta.find(b'\n')
    if i < 0:
        return None, 'delta has no header terminator'
    data = delta[i + 1:]
    if not data:
        return None, 'delta has zero data rows'
    return base + data, None


def run(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    a = sub.add_parser('audit', help='validate a current ratings CSV, no writes')
    a.add_argument('merged', type=Path)
    a.add_argument('--as-of', type=dt.date.fromisoformat)
    r = sub.add_parser('replay', help='check pinned base+delta reproduces merged exact bytes')
    r.add_argument('base', type=Path)
    r.add_argument('delta', type=Path)
    r.add_argument('merged', type=Path)
    r.add_argument('--as-of', type=dt.date.fromisoformat)
    ns = p.parse_args(argv)
    paths = [ns.merged] if ns.mode == 'audit' else [ns.base, ns.delta, ns.merged]
    try:
        payloads = [path.read_bytes() for path in paths]
    except OSError as exc:
        print(json.dumps({'status': 'FAIL', 'errors': [f'cannot read input: {exc}']}))
        return 4
    outputs = [parse_csv(path, data, as_of=ns.as_of) for path, data in zip(paths,payloads)]
    all_errors = [f"{x['path']}: {s}" for x in outputs for s in x['errors']]
    checks: dict = {'inputs': outputs}
    if ns.mode == 'replay':
        base, delta, merged = payloads
        expected, why = replay_concat(base,delta)
        if why:
            all_errors.append(why)
        elif expected != merged:
            all_errors.append('byte replay mismatch: merged is not exact base + delta data')
        if outputs[1]['rows'] == 0:
            all_errors.append('delta has no valid rows')
        checks['byte_replay'] = (expected == merged) if expected is not None else False
        checks['replayed_sha256'] = digest(expected) if expected is not None else None
        checks['expected_row_count'] = outputs[0]['rows'] + outputs[1]['rows']
        if outputs[2]['rows'] != checks['expected_row_count']:
            all_errors.append('merged row count differs from base+delta rows')
        # Reject overlapping rows even when the merged file has been tampered with.
        if outputs[0]['counts'].get('NBA', 0) == 0 and outputs[1]['counts'].get('NBA', 0) == 0:
            all_errors.append('NBA append replay requires an NBA row in base or delta')
    result = {'status': 'FAIL' if all_errors else 'PASS', 'mode': ns.mode,
              'as_of': ns.as_of.isoformat() if ns.as_of else None,
              'checks': checks, 'errors': all_errors,
              'meaning': ('structural and exact-byte checks only; not data provenance, '+
                          'model calibration, closing-line EV, or release authorization')}
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 4 if all_errors else 0


if __name__ == '__main__':
    sys.exit(run())
