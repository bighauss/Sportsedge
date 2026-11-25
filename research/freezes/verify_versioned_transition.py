#!/usr/bin/env python3
"""Verify approved research-code identity transitions; never rewrite the Nov 15 freeze.

The Nov 15 freeze (frozen_baselines_20261115.json) and the Nov 18 first-hop manifest
(code_identity_transitions_20261118.json) are byte-immutable; their git-blob SHA-1s are
hard-coded below. Additional reviewed hops live in
code_identity_transitions_20261125.json and are applied in memory only.

Each additional hop is data: prior and approved blobs, the first introducing commit,
single-parent ancestry (every parent holds the prior blob), and a governance record.
An unknown extra hop, a mutated manifest, or a tampered verifier/freeze exits non-zero.

Entry format for a further hop (the NBA stream's candidate on
grok-cbb/nba-push-accounting-transition-20261125 matches this; both the MLB and NBA
hops are registered in the 20261125 manifest):

    sport, path,
    original_git_blob_sha1,                 # Nov 15 pin
    prior_approved_candidate_git_blob_sha1, # previous hop's approved blob
    prior_first_introducing_commit,
    prior_change_pr,
    approved_candidate_git_blob_sha1,
    first_introducing_commit,
    change_pr,
    governance_record,                      # docs/governance/changes/pr-<N>.json
    change_class
"""
from __future__ import annotations
import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from verify_code_freezes import FreezeViolation, git_blob_digest, verify, unique_pairs, reject_constant

ROOT = Path(__file__).resolve().parents[2]
BASELINE_COMMIT = '29c85365e27665f16ba378cf2c7fc9c81f5754c1'
LEGACY_MANIFEST_BLOB = 'fd90e7d493739584bf59bd9d81a69f4174f119e8'
NOV18_MANIFEST_BLOB = '399a4df65036eb236f9f56699bc4090507786a3c'
CODE_FREEZES_VERIFIER_BLOB = '27d2b51d27d4b7da6f22dad31d55257541af8f67'
# First hops (Nov 18). Tuple shape is part of the public test surface; do not drop fields.
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
HOPS = Path(__file__).with_name('code_identity_transitions_20261125.json')
CODE_FREEZES_VERIFIER = Path(__file__).with_name('verify_code_freezes.py')

# Reviewed additional hops. Exact match required; an unlisted hop is refused.
# MLB: PR #446 / b73874a (input-safety). NBA: evidence from
# grok-cbb/nba-push-accounting-transition-20261125 @ 737dd2a3,
# research/freezes/code_identity_transitions_20261125_nba_candidate.json
# (PR #460 / 8537ae48, behavioral period-ML push accounting).
EXPECTED_ADDITIONAL_CANDIDATES = (
    {
        'sport': 'MLB',
        'path': 'models/mlb/sportsedge_mlb_model.py',
        'original_git_blob_sha1': 'bdedf10c09c307ee51fcec0f7da32cb4fa7974b8',
        'prior_approved_candidate_git_blob_sha1': '3f630532e9ff499912bc06041906d3b7c11d9887',
        'prior_first_introducing_commit': '85adaf523dbc46b6a7839151d5593c1ceade2be9',
        'prior_change_pr': 293,
        'approved_candidate_git_blob_sha1': '30c6cb3355ac5f6b6cbb018729c4fdc41255e057',
        'first_introducing_commit': 'b73874a2ecf8d558780bacf6b636b70e409f2cb4',
        'change_pr': 446,
        'governance_record': 'docs/governance/changes/pr-446.json',
        'change_class': 'INPUT_SAFETY_FAIL_CLOSED_LOADER_ONLY',
    },
    {
        'sport': 'NBA',
        'path': 'models/nba/sportsedge_nba_model.py',
        'original_git_blob_sha1': '0036cb9a2a7eff9fed9b175a0175a963d20e6b3e',
        'prior_approved_candidate_git_blob_sha1': 'da0c1503af5ed9ad548d1458588505f695b749e5',
        'prior_first_introducing_commit': '098c92bfd538fbb664b1c8eccccf61779cabe2b2',
        'prior_change_pr': 294,
        'approved_candidate_git_blob_sha1': 'b353de86445188288cab4050f6cae13eee76bff6',
        'first_introducing_commit': '8537ae481a34fa6972a67389a6ac75172ee1f59c',
        'change_pr': 460,
        'governance_record': 'docs/governance/changes/pr-460.json',
        'change_class': 'BEHAVIORAL_TWO_WAY_1H_1Q_ML_TIE_PUSH_ACCOUNTING',
    },
)


def expected_hops_document():
    """Exact reviewed 20261125 hops document, excluding the self-hash filled at check time."""
    return {
        'schema': 'sportsedge-code-identity-transitions-v1',
        'status': 'PENDING_OWNER_MERGE',
        'recording_act': 'OWNER_MERGE',
        'owner_decision': 'VERSIONED_RESEARCH_CANDIDATES_ONLY',
        'owner_decision_ct': '2026-11-25',
        'chains_from': 'research/freezes/code_identity_transitions_20261118.json',
        'supplements_manifest': {
            'path': 'research/freezes/code_identity_transitions_20261118.json',
            'git_blob_sha1': NOV18_MANIFEST_BLOB,
            'edited_by_this_change': False,
        },
        'original_baseline_commit': BASELINE_COMMIT,
        'original_manifest_git_blob_sha1': LEGACY_MANIFEST_BLOB,
        'nov18_transition_manifest_git_blob_sha1': NOV18_MANIFEST_BLOB,
        'verify_code_freezes_git_blob_sha1': CODE_FREEZES_VERIFIER_BLOB,
        'frozen_engine_v5_unchanged': True,
        'official_counted': 0,
        'approved_stake_u': 0,
        'candidates': [copy.deepcopy(c) for c in EXPECTED_ADDITIONAL_CANDIDATES],
    }


def checked_manifest(legacy: dict, transition: dict, raw_legacy: bytes) -> dict:
    """Authorize exactly the three reviewed Nov 18 research-code identities, in memory only."""
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


def checked_hops(hops: dict) -> list:
    """Refuse any hops document that is not the exact reviewed set; hash mismatch fails closed."""
    actual_self = git_blob_digest(Path(__file__).read_bytes())
    if hops.get('verify_versioned_transition_git_blob_sha1') != actual_self:
        raise FreezeViolation('VERSIONED_TRANSITION_VERIFIER_TAMPERED')
    expected = expected_hops_document()
    expected['verify_versioned_transition_git_blob_sha1'] = actual_self
    if hops != expected:
        raise FreezeViolation('UNAUTHORIZED_OR_UNVERSIONED_CODE_TRANSITION')
    if hops.get('official_counted') != 0 or hops.get('approved_stake_u') != 0:
        raise FreezeViolation('NO_OFFICIAL_RELEASE_ALLOWED')
    return hops['candidates']


def _git(repo: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as e:
        raise FreezeViolation('UNVERIFIABLE_GIT_PROVENANCE:' + ' '.join(args[:2])) from e


def check_provenance(repo: Path) -> None:
    """Validate both frozen and introduced Git objects for each Nov 18 first hop."""
    for sport, path, old, new, commit, pr in TRANSITIONS:
        original = _git(repo, 'show', BASELINE_COMMIT + ':' + path)
        introduced = _git(repo, 'show', commit + ':' + path)
        if git_blob_digest(original) != old:
            raise FreezeViolation('HISTORICAL_BASELINE_BYTES_MISMATCH:' + sport)
        if git_blob_digest(introduced) != new:
            raise FreezeViolation('INTRODUCING_COMMIT_BYTES_MISMATCH:' + sport)
        _git(repo, 'merge-base', '--is-ancestor', BASELINE_COMMIT, commit)
        _git(repo, 'merge-base', '--is-ancestor', commit, 'HEAD')
        # A descendant that merely *contains* the candidate is not the first
        # introducing commit. Require the file to be at the original frozen
        # blob in every immediate parent and changed at the nominated commit.
        # For merges, checking every parent avoids an ambiguous first-parent
        # assumption. If any parent differs, refuse rather than guess.
        parents = _git(repo, 'rev-list', '--parents', '-n', '1', commit).decode('ascii').split()
        if len(parents) < 2 or parents[0] != commit:
            raise FreezeViolation('INTRODUCING_COMMIT_PARENTS_UNVERIFIABLE:' + sport)
        if new == old:
            raise FreezeViolation('INTRODUCING_COMMIT_NO_SOURCE_CHANGE:' + sport)
        for parent in parents[1:]:
            parent_bytes = _git(repo, 'show', parent + ':' + path)
            if git_blob_digest(parent_bytes) != old:
                raise FreezeViolation('NOT_FIRST_INTRODUCING_COMMIT:' + sport)


def check_governance_record(repo: Path, relative: str, pr: int, model_path: str) -> None:
    """Fail closed if the hop's governance record is missing, linked, or not zero-release."""
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
            or '..' in Path(relative).parts):
        raise FreezeViolation('GOVERNANCE_RECORD_INVALID_PATH')
    record = repo / relative
    if not record.is_file() or record.is_symlink() or repo.resolve() not in record.resolve().parents:
        raise FreezeViolation('GOVERNANCE_RECORD_MISSING:' + relative)
    gov = json.loads(record.read_bytes(), object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    claims = gov.get('release_claims') if isinstance(gov.get('release_claims'), dict) else {}
    if (gov.get('pr_number') != pr or model_path not in tuple(gov.get('protected_paths') or ())
            or claims.get('official_counted') != 0 or claims.get('approved_stake_u') != 0):
        raise FreezeViolation('GOVERNANCE_RECORD_INVALID:' + relative)


def check_hop_provenance(repo: Path, hop: dict) -> None:
    """Prior blob, introducing commit bytes, single-parent ancestry, governance record."""
    sport, path = hop['sport'], hop['path']
    prior, new = hop['prior_approved_candidate_git_blob_sha1'], hop['approved_candidate_git_blob_sha1']
    commit, prior_commit = hop['first_introducing_commit'], hop['prior_first_introducing_commit']
    if git_blob_digest(_git(repo, 'show', commit + ':' + path)) != new:
        raise FreezeViolation('INTRODUCING_COMMIT_BYTES_MISMATCH:' + sport)
    if git_blob_digest(_git(repo, 'show', prior_commit + ':' + path)) != prior:
        raise FreezeViolation('PRIOR_APPROVED_BYTES_MISMATCH:' + sport)
    _git(repo, 'merge-base', '--is-ancestor', prior_commit, commit)
    _git(repo, 'merge-base', '--is-ancestor', commit, 'HEAD')
    parents = _git(repo, 'rev-list', '--parents', '-n', '1', commit).decode('ascii').split()
    # Additional hops must be a single-parent commit whose only parent holds the prior blob.
    if len(parents) != 2 or parents[0] != commit:
        raise FreezeViolation('INTRODUCING_COMMIT_PARENTS_UNVERIFIABLE:' + sport)
    if new == prior:
        raise FreezeViolation('INTRODUCING_COMMIT_NO_SOURCE_CHANGE:' + sport)
    if git_blob_digest(_git(repo, 'show', parents[1] + ':' + path)) != prior:
        raise FreezeViolation('NOT_FIRST_INTRODUCING_COMMIT:' + sport)
    check_governance_record(repo, hop['governance_record'], hop['change_pr'], path)


def apply_additional_hops(candidate: dict, hops: list) -> dict:
    """Advance in-memory pins along the reviewed chain; refuse a hop that does not chain."""
    state = {}
    for sport, path, old, new, commit, pr in TRANSITIONS:
        state[sport] = {'path': path, 'blob': new, 'commit': commit, 'pr': pr, 'original': old}
    out = copy.deepcopy(candidate)
    for hop in hops:
        sport = hop['sport']
        if sport not in state:
            raise FreezeViolation('HOP_SPORT_HAS_NO_PRIOR_TRANSITION:' + str(sport))
        cur = state[sport]
        if (hop['path'] != cur['path']
                or hop['original_git_blob_sha1'] != cur['original']
                or hop['prior_approved_candidate_git_blob_sha1'] != cur['blob']
                or hop['prior_first_introducing_commit'] != cur['commit']
                or hop['prior_change_pr'] != cur['pr']):
            raise FreezeViolation('HOP_PRIOR_PIN_INVALID:' + sport)
        if out['sports'][sport]['sources'][hop['path']] != cur['blob']:
            raise FreezeViolation('CANDIDATE_PIN_DESYNC:' + sport)
        out['sports'][sport]['sources'][hop['path']] = hop['approved_candidate_git_blob_sha1']
        cur['blob'] = hop['approved_candidate_git_blob_sha1']
        cur['commit'] = hop['first_introducing_commit']
        cur['pr'] = hop['change_pr']
    return out


def check_immutable_verifiers() -> None:
    if git_blob_digest(CODE_FREEZES_VERIFIER.read_bytes()) != CODE_FREEZES_VERIFIER_BLOB:
        raise FreezeViolation('CODE_FREEZE_VERIFIER_TAMPERED')


def run(repo: Path = ROOT, legacy_path: Path = LEGACY, transition_path: Path = TRANSITION,
        hops_path: Path = HOPS) -> dict:
    check_immutable_verifiers()
    raw = legacy_path.read_bytes()
    legacy = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    raw18 = transition_path.read_bytes()
    if git_blob_digest(raw18) != NOV18_MANIFEST_BLOB:
        raise FreezeViolation('NOV18_TRANSITION_MANIFEST_MODIFIED')
    transition = json.loads(raw18, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    candidate = checked_manifest(legacy, transition, raw)
    check_provenance(repo)
    for sport, path, old, new, commit, pr in TRANSITIONS:
        check_governance_record(repo, 'docs/governance/changes/pr-%d.json' % pr, pr, path)
    hops = checked_hops(json.loads(hops_path.read_bytes(), object_pairs_hook=unique_pairs,
                                   parse_constant=reject_constant))
    for hop in hops:
        check_hop_provenance(repo, hop)
    candidate = apply_additional_hops(candidate, hops)
    report = verify(candidate, repo)
    first = [{'sport': sport, 'original_git_blob_sha1': old,
              'candidate_git_blob_sha1': new, 'introducing_commit': commit, 'change_pr': pr}
             for sport, path, old, new, commit, pr in TRANSITIONS]
    additional = [{'sport': h['sport'], 'from_git_blob_sha1': h['prior_approved_candidate_git_blob_sha1'],
                   'candidate_git_blob_sha1': h['approved_candidate_git_blob_sha1'],
                   'introducing_commit': h['first_introducing_commit'], 'change_pr': h['change_pr']}
                  for h in hops]
    return {**report, 'status': 'VERSIONED_CODE_IDENTITY_ONLY_PAPER_0U',
            'legacy_manifest_unchanged': True,
            'nov18_transition_manifest_unchanged': True,
            'code_freeze_verifier_unmodified': True,
            'candidate_changes': first,
            'additional_hops': additional,
            'source_authenticated': False, 'model_release_certified': False}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Versioned research-code identity verifier')
    p.add_argument('--legacy', type=Path, default=LEGACY)
    p.add_argument('--transition', type=Path, default=TRANSITION)
    p.add_argument('--hops', type=Path, default=HOPS)
    p.add_argument('--repo', type=Path, default=ROOT)
    a = p.parse_args(argv)
    try:
        report = run(repo=a.repo, legacy_path=a.legacy, transition_path=a.transition, hops_path=a.hops)
    except FreezeViolation as e:
        print(json.dumps({'status': 'REFUSED', 'reason': str(e)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
