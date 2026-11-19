#!/usr/bin/env python3
"""Verify approved CBB research-code identity transition; never rewrite Nov 15 freeze."""
from __future__ import annotations
import copy
import json
import subprocess
from pathlib import Path
from verify_code_freezes import FreezeViolation, git_blob_digest, verify, unique_pairs, reject_constant

ROOT = Path(__file__).resolve().parents[2]
BASELINE_COMMIT = '29c85365e27665f16ba378cf2c7fc9c81f5754c1'
LEGACY_MANIFEST_BLOB = 'fd90e7d493739584bf59bd9d81a69f4174f119e8'
TRANSITIONS = (
    ('CBB', 'models/cbb/sportsedge_cbb_model.py',
     'f02dd29ef444f49cdf4560a86d5b8a517519081d',
     '8bbe83b7a17d184b3521094b40e00be66ba0f852',
     '45f44c08d5e735bad842e64f336328d078b0765b', 292),
    ('MLB', 'models/mlb/sportsedge_mlb_model.py',
     'bdedf10c09c307ee51fcec0f7da32cb4fa7974b8',
     '3f630532e9ff499912bc06041906d3b7c11d9887',
     '85adaf523dbc46b6a7839151d5593c1ceade2be9', 293),
    ('NBA', 'models/nba/sportsedge_nba_model.py',
     '0036cb9a2a7eff9fed9b175a0175a963d20e6b3e',
     'da0c1503af5ed9ad548d1458588505f695b749e5',
     '098c92bfd538fbb664b1c8eccccf61779cabe2b2', 294),
)
LEGACY = Path(__file__).with_name('frozen_baselines_20261115.json')
TRANSITION = Path(__file__).with_name('code_identity_transitions_20261118.json')

def checked_manifest(legacy: dict, transition: dict, raw_legacy: bytes) -> dict:
    """Authorize exactly three reviewed research-code identities, in memory only."""
    if git_blob_digest(raw_legacy) != LEGACY_MANIFEST_BLOB:
        raise FreezeViolation('ORIGINAL_FREEZE_MANIFEST_MODIFIED')
    if (legacy.get('schema') != 'sportsedge-research-code-freezes-v1'
            or legacy.get('baseline_commit') != BASELINE_COMMIT
            or legacy.get('recorded_ct') != '2026-11-15'):
        raise FreezeViolation('ORIGINAL_FREEZE_MANIFEST_METADATA_INVALID')
    expected = {
        'schema': 'sportsedge-code-identity-transitions-v1',
        'original_baseline_commit': BASELINE_COMMIT,
        'original_manifest_git_blob_sha1': LEGACY_MANIFEST_BLOB,
        'owner_decision': 'VERSIONED_RESEARCH_CANDIDATES_ONLY',
        'frozen_engine_v5_unchanged': True,
        'official_counted': 0,
        'approved_stake_u': 0,
        'candidates': [
            {'sport': sport, 'path': path, 'original_git_blob_sha1': old,
             'approved_candidate_git_blob_sha1': new,
             'first_introducing_commit': commit, 'change_pr': pr}
            for sport, path, old, new, commit, pr in TRANSITIONS
        ],
    }
    if transition != expected:
        raise FreezeViolation('UNAUTHORIZED_OR_UNVERSIONED_CODE_TRANSITION')
    candidate = copy.deepcopy(legacy)
    for sport, path, old, new, commit, pr in TRANSITIONS:
        if candidate.get('sports', {}).get(sport, {}).get('sources', {}).get(path) != old:
            raise FreezeViolation('ORIGINAL_CODE_FREEZE_PIN_INVALID:' + sport)
        candidate['sports'][sport]['sources'][path] = new
    return candidate

def _git(repo: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as e:
        raise FreezeViolation('UNVERIFIABLE_GIT_PROVENANCE:' + ' '.join(args[:2])) from e

def check_provenance(repo: Path) -> None:
    """Validate both frozen and introduced Git objects for each changed sport."""
    for sport, path, old, new, commit, pr in TRANSITIONS:
        original = _git(repo, 'show', BASELINE_COMMIT + ':' + path)
        introduced = _git(repo, 'show', commit + ':' + path)
        if git_blob_digest(original) != old:
            raise FreezeViolation('HISTORICAL_BASELINE_BYTES_MISMATCH:' + sport)
        if git_blob_digest(introduced) != new:
            raise FreezeViolation('INTRODUCING_COMMIT_BYTES_MISMATCH:' + sport)
        _git(repo, 'merge-base', '--is-ancestor', BASELINE_COMMIT, commit)
        _git(repo, 'merge-base', '--is-ancestor', commit, 'HEAD')

def run(repo: Path = ROOT, legacy_path: Path = LEGACY, transition_path: Path = TRANSITION) -> dict:
    raw = legacy_path.read_bytes()
    legacy = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    transition = json.loads(transition_path.read_bytes(), object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    candidate = checked_manifest(legacy, transition, raw)
    check_provenance(repo)
    report = verify(candidate, repo)
    return {**report, 'status': 'VERSIONED_CODE_IDENTITY_ONLY_PAPER_0U',
            'legacy_manifest_unchanged': True,
            'candidate_changes': [
                {'sport': sport, 'original_git_blob_sha1': old,
                 'candidate_git_blob_sha1': new, 'introducing_commit': commit}
                for sport, path, old, new, commit, pr in TRANSITIONS
            ],
            'source_authenticated': False, 'model_release_certified': False}


if __name__ == '__main__':
    print(json.dumps(run(), sort_keys=True))
