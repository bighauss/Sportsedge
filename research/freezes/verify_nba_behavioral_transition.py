#!/usr/bin/env python3
"""Verify the NBA *behavioral* code-identity transition da0c1503 -> b353de86 (PR #460).

Additive, fail-closed companion to verify_versioned_transition.py. It does NOT edit,
bypass or weaken that verifier, the Nov 15 freeze or the Nov 18 manifest: it imports
and re-runs their own checks first, then verifies the second link of the NBA chain

    0036cb9a (Nov 15 pin) -> da0c1503 (Nov 18, #294) -> b353de86 (8537ae4, #460)

Scope is the NBA model file ONLY.  It is not a replacement for the 'Seven code pin
verification' CI step, which stays red until MLB/NBA are approved in that step.
Hash = code identity, not authentication.  PAPER_0U; official_counted 0; no stake.
"""
from __future__ import annotations
import difflib
import hashlib
import json
from pathlib import Path

from verify_code_freezes import FreezeViolation, git_blob_digest, unique_pairs, reject_constant, verified_file
import verify_versioned_transition as vt

ROOT = vt.ROOT
HERE = Path(__file__).resolve().parent
NBA_PATH = 'models/nba/sportsedge_nba_model.py'
V0 = '0036cb9a2a7eff9fed9b175a0175a963d20e6b3e'   # Nov 15 pin
V1 = 'da0c1503af5ed9ad548d1458588505f695b749e5'   # Nov 18 approved (#294, 098c92b)
V2 = 'b353de86445188288cab4050f6cae13eee76bff6'   # candidate (#460, 8537ae4)
V2_COMMIT = '8537ae481a34fa6972a67389a6ac75172ee1f59c'
V2_PR = 460
NOV18_TRANSITION_BLOB = '399a4df65036eb236f9f56699bc4090507786a3c'
AFFECTED_MARKETS = ('1H_ML', '1Q_ML')
ENTRY = HERE / 'code_identity_transitions_20261125.json'
RECORD = HERE / 'nba_push_accounting_transition_20261125.json'
EVIDENCE = HERE / 'nba_push_accounting_20261125_equivalence.json'
PINNED_V1 = HERE / 'pinned_blobs' / 'da0c1503_sportsedge_nba_model.py.txt'
MAX_UNAFFECTED_MISMATCH = 0


def _load(path: Path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_pairs, parse_constant=reject_constant)


def expected_entry() -> dict:
    """Nov 18 format; chains from the Nov 18 manifest, never replaces it."""
    return {
        'schema': 'sportsedge-code-identity-transitions-v1',
        'status': 'PENDING_OWNER_MERGE',
        'transition_kind': 'BEHAVIORAL',
        'chains_from': 'research/freezes/code_identity_transitions_20261118.json',
        'chains_from_git_blob_sha1': NOV18_TRANSITION_BLOB,
        'original_baseline_commit': vt.BASELINE_COMMIT,
        'original_manifest_git_blob_sha1': vt.LEGACY_MANIFEST_BLOB,
        'owner_decision': 'VERSIONED_RESEARCH_CANDIDATES_ONLY',
        'frozen_engine_v5_unchanged': True,
        'official_counted': 0,
        'approved_stake_u': 0,
        'candidates': [{
            'sport': 'NBA', 'path': NBA_PATH,
            'original_git_blob_sha1': V0,
            'previous_approved_candidate_git_blob_sha1': V1,
            'approved_candidate_git_blob_sha1': V2,
            'first_introducing_commit': V2_COMMIT,
            'change_pr': V2_PR,
        }],
    }


def diff_text(old: bytes, new: bytes) -> str:
    return ''.join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                        'da0c1503', 'b353de86', n=0))


def check_chain_provenance(repo: Path) -> None:
    """V1 -> V2 must be a single, first-introducing change at 8537ae4 on HEAD's history."""
    introduced = vt._git(repo, 'show', V2_COMMIT + ':' + NBA_PATH)
    if git_blob_digest(introduced) != V2:
        raise FreezeViolation('INTRODUCING_COMMIT_BYTES_MISMATCH:NBA_V2')
    vt._git(repo, 'merge-base', '--is-ancestor', V2_COMMIT, 'HEAD')
    # the Nov 18 candidate's own introducing commit must precede it
    nov18_commit = [t for t in vt.TRANSITIONS if t[0] == 'NBA'][0][4]
    vt._git(repo, 'merge-base', '--is-ancestor', nov18_commit, V2_COMMIT)
    parents = vt._git(repo, 'rev-list', '--parents', '-n', '1', V2_COMMIT).decode('ascii').split()
    if len(parents) < 2 or parents[0] != V2_COMMIT:
        raise FreezeViolation('INTRODUCING_COMMIT_PARENTS_UNVERIFIABLE:NBA_V2')
    for parent in parents[1:]:
        if git_blob_digest(vt._git(repo, 'show', parent + ':' + NBA_PATH)) != V1:
            raise FreezeViolation('NOT_FIRST_INTRODUCING_COMMIT:NBA_V2')


def check_record(repo: Path) -> dict:
    rec = _load(RECORD)
    if rec.get('schema') != 'sportsedge-nba-behavioral-transition-record-v1':
        raise FreezeViolation('RECORD_SCHEMA_INVALID')
    must = {'status': 'PENDING_OWNER_MERGE', 'recording_act': 'OWNER_MERGE', 'release': 'PAPER_0U',
            'official_counted': 0, 'approved_stake_u': 0, 'model_release_certified': False,
            'source_authenticated': False, 'transition_kind': 'BEHAVIORAL', 'sport': 'NBA', 'path': NBA_PATH,
            'original_nov15_blob': V0, 'previous_approved_blob': V1, 'candidate_blob': V2,
            'first_introducing_commit': V2_COMMIT, 'change_pr': V2_PR,
            'affected_markets': list(AFFECTED_MARKETS)}
    for k, v in must.items():
        if rec.get(k) != v:
            raise FreezeViolation('RECORD_FIELD_INVALID:' + k)
    imm = rec.get('immutable_inputs', {})
    if git_blob_digest(vt.LEGACY.read_bytes()) != vt.LEGACY_MANIFEST_BLOB:
        raise FreezeViolation('ORIGINAL_FREEZE_MANIFEST_MODIFIED')
    if git_blob_digest(vt.TRANSITION.read_bytes()) != NOV18_TRANSITION_BLOB or imm.get('nov18_transition_git_blob_sha1') != NOV18_TRANSITION_BLOB:
        raise FreezeViolation('NOV18_TRANSITION_MANIFEST_MODIFIED')
    # evidence + pinned old bytes are content-addressed by the record
    if git_blob_digest(PINNED_V1.read_bytes()) != V1:
        raise FreezeViolation('PINNED_PREVIOUS_BLOB_COPY_MISMATCH')
    if git_blob_digest(EVIDENCE.read_bytes()) != rec['equivalence']['evidence_git_blob_sha1']:
        raise FreezeViolation('EQUIVALENCE_EVIDENCE_MISMATCH')
    for key, rel in (('hist_analysis_git_blob_sha1', 'nba_push_accounting_hist/analysis.json'),
                     ('hist_games_csv_git_blob_sha1', 'nba_push_accounting_hist/games.csv')):
        if git_blob_digest((HERE / rel).read_bytes()) != rec['historical_backtest'][key]:
            raise FreezeViolation('HISTORICAL_EVIDENCE_MISMATCH:' + key)
    gov = repo / rec['governance_record']
    if git_blob_digest(gov.read_bytes()) != rec['governance_record_git_blob_sha1']:
        raise FreezeViolation('GOVERNANCE_RECORD_MISMATCH')
    # the exact diff is content-addressed; any extra/changed byte is refused
    d = diff_text(PINNED_V1.read_bytes(), (repo / NBA_PATH).read_bytes())
    if hashlib.sha256(d.encode()).hexdigest() != rec['diff']['unified_diff_n0_sha256']:
        raise FreezeViolation('MODEL_DIFF_NOT_THE_RECORDED_DIFF')
    evid = _load(EVIDENCE)
    if evid.get('old_blob') != V1 or evid.get('new_blob') != V2:
        raise FreezeViolation('EVIDENCE_BLOBS_MISMATCH')
    for r in evid['results']:
        if r['unaffected_mismatch'] != MAX_UNAFFECTED_MISMATCH or r['projection_mismatch'] or r['prop_mismatch'] \
                or r['card_unaffected_mismatch'] or not r['card_run_unaffected_identical'] \
                or r['affected_norm_violations'] or r['affected_new_push_zero'] or r['affected_old_push_nonzero']:
            raise FreezeViolation('EVIDENCE_REPORTS_NON_ISOLATED_BEHAVIOR_CHANGE')
    return rec


def run(repo: Path = ROOT, legacy_path: Path = vt.LEGACY, transition_path: Path = vt.TRANSITION,
        entry_path: Path = ENTRY) -> dict:
    # 1. Re-run the Nov 15 / Nov 18 authority unchanged (raises on any tamper).
    raw = legacy_path.read_bytes()
    legacy = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    nov18 = _load(transition_path)
    candidate = vt.checked_manifest(legacy, nov18, raw)
    vt.check_provenance(repo)                       # Nov 18 chain links incl. NBA da0c1503
    # 2. Candidate entry must be exactly the reviewed Nov-18-format entry.
    if _load(entry_path) != expected_entry():
        raise FreezeViolation('UNAUTHORIZED_OR_UNVERSIONED_CODE_TRANSITION:NBA_V2')
    # 3. Link V1 -> V2 provenance, then the exact bytes on disk.
    check_chain_provenance(repo)
    if candidate['sports']['NBA']['sources'][NBA_PATH] != V1:
        raise FreezeViolation('NBA_V1_PIN_INVALID')
    on_disk = verified_file(repo, NBA_PATH, V2)
    rec = check_record(repo)
    others = {}
    for sport, rec_ in sorted(candidate['sports'].items()):
        if sport == 'NBA':
            continue
        try:
            for path, sha in sorted(rec_['sources'].items()):
                verified_file(repo, path, sha)
            others[sport] = 'PIN_OK'
        except FreezeViolation as e:
            others[sport] = str(e)
    return {'status': 'NBA_BEHAVIORAL_TRANSITION_VERIFIED_PAPER_0U_PENDING_OWNER_MERGE',
            'scope': 'NBA model file only; NOT a replacement for the seven-code-pin CI step',
            'nba_chain': [V0, V1, V2], 'nba_on_disk': on_disk,
            'other_sport_pin_status_informational': others,
            'record_status': rec['status'], 'official_counted': 0, 'approved_stake_u': 0,
            'model_release_certified': False, 'source_authenticated': False}


if __name__ == '__main__':
    print(json.dumps(run(), sort_keys=True))
