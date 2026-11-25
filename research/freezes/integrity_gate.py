#!/usr/bin/env python3
"""Independent, base-pinned integrity gate for the research-code freeze verifiers.

Why: verify_versioned_transition.py checks its own git blob against a value stored in
code_identity_transitions_20261125.json. A PR can edit both, so that self-hash is not
an independent trust anchor. This gate supplies one.

How: the pull_request_target workflow .github/workflows/freeze-integrity-trusted.yml
checks out the trusted BASE commit and runs THIS file from the base. Expected blob
values come only from integrity_pins.json as committed on the BASE commit. The PR head
is read solely as git objects (git rev-parse / git show); no head code is executed and
no secrets are used.

Rules (fail closed, exit 2):
  * the base tree must itself match the base pins (INTEGRITY_BASE_PINS_INCONSISTENT);
  * any pinned path whose head blob differs from the base pin, or a head
    integrity_pins.json whose blob differs from the base one, is an integrity change;
  * an integrity change without an exact declaration in
    docs/governance/integrity/pr-<N>.json -> INTEGRITY_PIN_CHANGE_UNDECLARED;
  * an integrity change WITH an exact declaration still fails
    (INTEGRITY_PIN_CHANGE_DECLARED_REQUIRES_OWNER_MERGE): the owner merge is the
    only recording act, after which the new base pins become the trusted values.

Nothing here certifies a model, a source, or a release. PAPER / 0u, NON_COUNTED.
This module is stdlib-only and imports no repository code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PINS_PATH = 'research/freezes/integrity_pins.json'
PINS_SCHEMA = 'sportsedge-freeze-integrity-pins-v1'
DECLARATION_SCHEMA = 'sportsedge-freeze-integrity-change-v1'
MAX_JSON_BYTES = 50_000
SHA = re.compile(r'^[0-9a-f]{40}$')
EXIT_BLOCK = 2


class IntegrityError(ValueError):
    pass


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b'blob %d\x00' % len(data) + data).hexdigest()


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise IntegrityError('DUPLICATE_JSON_KEY')
        out[k] = v
    return out


def _no_constant(_):
    raise IntegrityError('NONFINITE_JSON_NUMBER')


def _parse(raw: bytes, label: str):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_JSON_BYTES:
        raise IntegrityError('JSON_EMPTY_OR_OVERSIZE:' + label)
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                          parse_constant=_no_constant)
    except IntegrityError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise IntegrityError('MALFORMED_JSON:' + label) from exc


def _sha(value, label):
    if type(value) is not str or not SHA.fullmatch(value):
        raise IntegrityError('INVALID_GIT_SHA:' + label)
    return value


def _valid_path(value):
    if (type(value) is not str or not value or len(value) > 400 or value.startswith('/')
            or '\\' in value or any(p in ('', '.', '..') for p in value.split('/'))
            or any(ord(c) < 33 or ord(c) > 126 for c in value)):
        raise IntegrityError('INVALID_PINNED_PATH')
    return value


def _git(repo: Path, *args: str, allow_missing: bool = False):
    try:
        res = subprocess.run(['git', '-C', str(repo), *args], check=False,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IntegrityError('GIT_READ_FAILED') from exc
    if res.returncode:
        if allow_missing:
            return None
        raise IntegrityError('GIT_READ_OR_REVISION_FAILED')
    return res.stdout


def blob_at(repo: Path, commit: str, path: str):
    """Git blob id of path at commit, or None if absent; never executes content."""
    _sha(commit, 'commit')
    _valid_path(path)
    out = _git(repo, 'ls-tree', '-z', '--full-tree', commit, '--', path, allow_missing=True)
    if out is None:
        raise IntegrityError('GIT_READ_OR_REVISION_FAILED')
    entries = [e for e in out.split(b'\x00') if e]
    if not entries:
        return None
    if len(entries) != 1:
        raise IntegrityError('AMBIGUOUS_TREE_ENTRY')
    meta, _, name = entries[0].partition(b'\t')
    mode, kind, oid = meta.decode('ascii').split(' ')
    if name.decode('utf-8') != path or kind != 'blob' or mode not in ('100644', '100755'):
        # Symlinks, submodules or directories at a pinned path fail closed.
        raise IntegrityError('PINNED_PATH_NOT_REGULAR_FILE:' + path)
    return _sha(oid, 'blob')


def read_at(repo: Path, commit: str, path: str):
    if blob_at(repo, commit, path) is None:
        return None
    return _git(repo, 'show', f'{commit}:{path}')


def parse_pins(raw: bytes) -> dict:
    doc = _parse(raw, 'pins')
    if (type(doc) is not dict or set(doc) != {'schema', 'description', 'recording_act', 'pins'}
            or doc['schema'] != PINS_SCHEMA or doc['recording_act'] != 'OWNER_MERGE'
            or type(doc['description']) is not str or type(doc['pins']) is not dict
            or not doc['pins']):
        raise IntegrityError('INTEGRITY_PINS_MALFORMED')
    pins = {}
    for path, blob in doc['pins'].items():
        _valid_path(path)
        if path == PINS_PATH:
            raise IntegrityError('INTEGRITY_PINS_SELF_ENTRY_FORBIDDEN')
        pins[path] = _sha(blob, 'pin:' + path)
    return pins


def integrity_changes(repo: Path, base_commit: str, head_commit: str) -> tuple:
    """Return (base_pins, sorted change list) computed only from BASE-committed values."""
    raw = read_at(repo, base_commit, PINS_PATH)
    if raw is None:
        raise IntegrityError('INTEGRITY_PINS_MISSING_ON_BASE')
    pins = parse_pins(raw)
    for path, want in sorted(pins.items()):
        if blob_at(repo, base_commit, path) != want:
            raise IntegrityError('INTEGRITY_BASE_PINS_INCONSISTENT:' + path)
    expected = dict(pins)
    expected[PINS_PATH] = git_blob_sha1(raw)
    changes = []
    for path, want in sorted(expected.items()):
        got = blob_at(repo, head_commit, path)
        if got != want:
            changes.append({'path': path, 'base_git_blob_sha1': want, 'head_git_blob_sha1': got})
    return pins, changes


def declaration_matches(repo: Path, head_commit: str, pr_number: int, base_commit: str,
                        changes: list) -> bool:
    raw = read_at(repo, head_commit, f'docs/governance/integrity/pr-{pr_number}.json')
    if raw is None:
        return False
    try:
        doc = _parse(raw, 'declaration')
    except IntegrityError:
        return False
    want = {
        'schema': DECLARATION_SCHEMA,
        'pr_number': pr_number,
        'base_commit': base_commit,
        'recording_act': 'OWNER_MERGE',
        'changes': changes,
    }
    if type(doc) is not dict or set(doc) != set(want) | {'reason'}:
        return False
    if type(doc['reason']) is not str or not doc['reason'].strip():
        return False
    if type(doc['pr_number']) is not int:
        return False
    return all(doc[k] == want[k] for k in want)


def evaluate(repo: Path, *, base_commit: str, head_commit: str, pr_number: int) -> dict:
    _sha(base_commit, 'base')
    _sha(head_commit, 'head')
    if type(pr_number) is not int or pr_number < 1:
        raise IntegrityError('INVALID_PR_NUMBER')
    if base_commit == head_commit:
        raise IntegrityError('PR_HEAD_EQUALS_BASE')
    _pins, changes = integrity_changes(repo, base_commit, head_commit)
    result = {'pins_source': f'{base_commit}:{PINS_PATH}', 'changes': changes,
              'official_counted': 0, 'approved_stake_u': 0}
    if not changes:
        return {**result, 'state': 'PASS_INTEGRITY_PINS_UNCHANGED'}
    if declaration_matches(repo, head_commit, pr_number, base_commit, changes):
        return {**result, 'state': 'BLOCK',
                'reason_code': 'INTEGRITY_PIN_CHANGE_DECLARED_REQUIRES_OWNER_MERGE'}
    return {**result, 'state': 'BLOCK', 'reason_code': 'INTEGRITY_PIN_CHANGE_UNDECLARED'}


def self_check(repo: Path, commit: str) -> dict:
    """Tree at commit must match the pins committed at that same commit (main push)."""
    _sha(commit, 'commit')
    raw = read_at(repo, commit, PINS_PATH)
    if raw is None:
        raise IntegrityError('INTEGRITY_PINS_MISSING')
    for path, want in sorted(parse_pins(raw).items()):
        if blob_at(repo, commit, path) != want:
            raise IntegrityError('INTEGRITY_TREE_PIN_MISMATCH:' + path)
    return {'state': 'PASS_TREE_MATCHES_OWN_PINS', 'commit': commit,
            'official_counted': 0, 'approved_stake_u': 0}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Base-pinned freeze integrity gate')
    p.add_argument('--repo', default='.')
    p.add_argument('--base-sha')
    p.add_argument('--head-sha')
    p.add_argument('--pr-number', type=int)
    p.add_argument('--self-check', metavar='SHA')
    a = p.parse_args(argv)
    try:
        if a.self_check:
            result = self_check(Path(a.repo), a.self_check)
        else:
            if not (a.base_sha and a.head_sha and a.pr_number is not None):
                raise IntegrityError('ARGUMENTS_REQUIRED')
            result = evaluate(Path(a.repo), base_commit=a.base_sha, head_commit=a.head_sha,
                              pr_number=a.pr_number)
    except IntegrityError as exc:
        print(json.dumps({'state': 'BLOCK', 'reason_code': str(exc),
                          'official_counted': 0, 'approved_stake_u': 0}, sort_keys=True))
        return EXIT_BLOCK
    print(json.dumps(result, sort_keys=True))
    return 0 if result['state'].startswith('PASS') else EXIT_BLOCK


if __name__ == '__main__':
    sys.exit(main())
