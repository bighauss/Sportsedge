#!/usr/bin/env python3
"""Verify approved CBB research-code identity transition; never rewrite Nov 15 freeze."""
from __future__ import annotations
import copy
import json
import subprocess
from pathlib import Path
from verify_code_freezes import FreezeViolation, git_blob_digest, verify, unique_pairs, reject_constant

ROOT = Path(__file__).resolve().parents[2]
FROZEN_PATH = 'models/cbb/sportsedge_cbb_model.py'
BASELINE_COMMIT = '29c85365e27665f16ba378cf2c7fc9c81f5754c1'
INTRODUCING_COMMIT = '45f44c08d5e735bad842e64f336328d078b0765b'
BASELINE_BLOB = 'f02dd29ef444f49cdf4560a86d5b8a517519081d'
CANDIDATE_BLOB = '8bbe83b7a17d184b3521094b40e00be66ba0f852'
LEGACY_MANIFEST_BLOB = 'fd90e7d493739584bf59bd9d81a69f4174f119e8'
LEGACY = Path(__file__).with_name('frozen_baselines_20261115.json')
TRANSITION = Path(__file__).with_name('cbb_identity_transition_20261118.json')

def checked_manifest(legacy: dict, transition: dict, raw_legacy: bytes) -> dict:
    """Construct IN-MEMORY current-code assertion; historical source file stays frozen."""
    if git_blob_digest(raw_legacy) != LEGACY_MANIFEST_BLOB:
        raise FreezeViolation('ORIGINAL_FREEZE_MANIFEST_MODIFIED')
    if (legacy.get('schema') != 'sportsedge-research-code-freezes-v1'
            or legacy.get('baseline_commit') != BASELINE_COMMIT
            or legacy.get('recorded_ct') != '2026-11-15'
            or legacy.get('sports', {}).get('CBB', {}).get('sources', {}).get(FROZEN_PATH) != BASELINE_BLOB):
        raise FreezeViolation('ORIGINAL_CBB_FREEZE_PIN_INVALID')
    expected = {
        'schema': 'sportsedge-code-identity-transition-v1',
        'sport': 'CBB', 'path': FROZEN_PATH,
        'original_baseline_commit': BASELINE_COMMIT,
        'original_manifest_git_blob_sha1': LEGACY_MANIFEST_BLOB,
        'original_git_blob_sha1': BASELINE_BLOB,
        'first_introducing_commit': INTRODUCING_COMMIT,
        'approved_candidate_git_blob_sha1': CANDIDATE_BLOB,
        'change_pr': 292,
        'owner_decision': 'VERSIONED_RESEARCH_CANDIDATE_ONLY',
        'frozen_engine_v5_unchanged': True,
        'official_counted': 0, 'approved_stake_u': 0,
    }
    if transition != expected:
        raise FreezeViolation('UNAUTHORIZED_OR_UNVERSIONED_CODE_TRANSITION')
    candidate = copy.deepcopy(legacy)
    candidate['sports']['CBB']['sources'][FROZEN_PATH] = CANDIDATE_BLOB
    return candidate

def _git(repo: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as e:
        raise FreezeViolation('UNVERIFIABLE_GIT_PROVENANCE:' + ' '.join(args[:2])) from e

def check_provenance(repo: Path) -> None:
    original = _git(repo, 'show', BASELINE_COMMIT + ':' + FROZEN_PATH)
    introduced = _git(repo, 'show', INTRODUCING_COMMIT + ':' + FROZEN_PATH)
    if git_blob_digest(original) != BASELINE_BLOB:
        raise FreezeViolation('HISTORICAL_BASELINE_BYTES_MISMATCH')
    if git_blob_digest(introduced) != CANDIDATE_BLOB:
        raise FreezeViolation('INTRODUCING_COMMIT_BYTES_MISMATCH')
    _git(repo, 'merge-base', '--is-ancestor', BASELINE_COMMIT, INTRODUCING_COMMIT)
    _git(repo, 'merge-base', '--is-ancestor', INTRODUCING_COMMIT, 'HEAD')

def run(repo: Path = ROOT, legacy_path: Path = LEGACY, transition_path: Path = TRANSITION) -> dict:
    raw = legacy_path.read_bytes()
    legacy = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    transition = json.loads(transition_path.read_bytes(), object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    candidate = checked_manifest(legacy, transition, raw)
    check_provenance(repo)
    report = verify(candidate, repo)
    return {**report, 'status': 'VERSIONED_CODE_IDENTITY_ONLY_PAPER_0U',
            'legacy_manifest_unchanged': True,
            'original_cbb_blob': BASELINE_BLOB, 'approved_cbb_candidate_blob': CANDIDATE_BLOB,
            'change_commit': INTRODUCING_COMMIT,
            'source_authenticated': False, 'model_release_certified': False}

if __name__ == '__main__':
    print(json.dumps(run(), sort_keys=True))
