#!/usr/bin/env python3
"""Additive verifier for the PENDING_OWNER_MERGE MLB input-safety transition (3f630532 -> 30c6cb33).

Never edits, wraps-and-weakens or bypasses verify_versioned_transition.py / verify_code_freezes.py. It
IMPORTS them and runs every one of their checks unchanged on the Nov 15 manifest and the Nov 18 transition
manifest (original blob hash, exact three-candidate transition, historical bytes and first-introducing-commit
provenance for CBB, MLB and NBA). It then adds a second, explicit MLB hop and checks that hop the same way:
the exact candidate manifest, the introducing commit's blob, a single parent still at the previously approved
blob, ancestry, and the pr-446 governance record. Only after all of that is the MLB pin replaced, in memory
only, and every pinned file is hashed against the working tree.

Per-sport results are reported; exit status 0 requires the requested scope to pass. `--scope MLB` (default)
gates on MLB and reports the other sports; `--scope ALL` gates on all seven sports (still red while the
separately-owned NBA drift is unresolved).
"""
from __future__ import annotations
import argparse
import copy
import json
import sys
from pathlib import Path

import verify_versioned_transition as vt
from verify_code_freezes import FreezeViolation, git_blob_digest, reject_constant, unique_pairs, verified_file

ROOT = vt.ROOT
HERE = Path(__file__).resolve().parent
CANDIDATE_MANIFEST = HERE / "code_identity_transitions_20261125_mlb_candidate.json"
MLB_PATH = "models/mlb/sportsedge_mlb_model.py"
STOCK_VERIFIER_BLOBS = {"verify_code_freezes.py": "27d2b51d27d4b7da6f22dad31d55257541af8f67",
                        "verify_versioned_transition.py": "522ee86d6a2608568dc456145b6bde461799cf3a"}
NOV18_MANIFEST_BLOB = "399a4df65036eb236f9f56699bc4090507786a3c"
PRIOR_BLOB = "3f630532e9ff499912bc06041906d3b7c11d9887"
PRIOR_COMMIT = "85adaf523dbc46b6a7839151d5593c1ceade2be9"
NEW_BLOB = "30c6cb3355ac5f6b6cbb018729c4fdc41255e057"
NEW_COMMIT = "b73874a2ecf8d558780bacf6b636b70e409f2cb4"
GOVERNANCE_RECORD = "docs/governance/changes/pr-446.json"

EXPECTED_CANDIDATE_MANIFEST = {
    "schema": "sportsedge-code-identity-transitions-v1",
    "status": "PENDING_OWNER_MERGE",
    "recording_act": "OWNER_MERGE",
    "owner_decision": "VERSIONED_RESEARCH_CANDIDATES_ONLY",
    "owner_decision_ct": "2026-11-25",
    "supplements_manifest": {
        "path": "research/freezes/code_identity_transitions_20261118.json",
        "git_blob_sha1": NOV18_MANIFEST_BLOB,
        "edited_by_this_change": False,
    },
    "original_baseline_commit": vt.BASELINE_COMMIT,
    "original_manifest_git_blob_sha1": vt.LEGACY_MANIFEST_BLOB,
    "frozen_engine_v5_unchanged": True,
    "official_counted": 0,
    "approved_stake_u": 0,
    "candidates": [{
        "sport": "MLB",
        "path": MLB_PATH,
        "original_git_blob_sha1": "bdedf10c09c307ee51fcec0f7da32cb4fa7974b8",
        "prior_approved_candidate_git_blob_sha1": PRIOR_BLOB,
        "prior_first_introducing_commit": PRIOR_COMMIT,
        "prior_change_pr": 293,
        "approved_candidate_git_blob_sha1": NEW_BLOB,
        "first_introducing_commit": NEW_COMMIT,
        "change_pr": 446,
        "governance_record": GOVERNANCE_RECORD,
        "change_class": "INPUT_SAFETY_FAIL_CLOSED_LOADER_ONLY",
    }],
}


def checked_candidate_manifest(manifest: dict) -> dict:
    """The candidate manifest must be exactly the reviewed one; any deviation is refused."""
    if manifest != EXPECTED_CANDIDATE_MANIFEST:
        raise FreezeViolation("UNAUTHORIZED_OR_UNVERSIONED_MLB_CODE_TRANSITION")
    return manifest


def check_second_hop_provenance(repo: Path) -> None:
    """3f630532 (85adaf5, PR #293) -> 30c6cb33 (b73874a, PR #446): bytes, single-parent lineage, ancestry."""
    git = vt._git
    introduced = git(repo, "show", NEW_COMMIT + ":" + MLB_PATH)
    if git_blob_digest(introduced) != NEW_BLOB:
        raise FreezeViolation("INTRODUCING_COMMIT_BYTES_MISMATCH:MLB:HOP2")
    prior = git(repo, "show", PRIOR_COMMIT + ":" + MLB_PATH)
    if git_blob_digest(prior) != PRIOR_BLOB:
        raise FreezeViolation("PRIOR_APPROVED_BYTES_MISMATCH:MLB:HOP2")
    git(repo, "merge-base", "--is-ancestor", PRIOR_COMMIT, NEW_COMMIT)
    git(repo, "merge-base", "--is-ancestor", NEW_COMMIT, "HEAD")
    parents = git(repo, "rev-list", "--parents", "-n", "1", NEW_COMMIT).decode("ascii").split()
    if len(parents) != 2 or parents[0] != NEW_COMMIT:
        raise FreezeViolation("INTRODUCING_COMMIT_PARENTS_UNVERIFIABLE:MLB:HOP2")
    if git_blob_digest(git(repo, "show", parents[1] + ":" + MLB_PATH)) != PRIOR_BLOB:
        raise FreezeViolation("NOT_FIRST_INTRODUCING_COMMIT:MLB:HOP2")
    record = (repo / GOVERNANCE_RECORD)
    if not record.is_file():
        raise FreezeViolation("GOVERNANCE_RECORD_MISSING:MLB:HOP2")
    gov = json.loads(record.read_bytes(), object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    if (gov.get("pr_number") != 446 or MLB_PATH not in gov.get("protected_paths", ())
            or gov.get("release_claims", {}).get("official_counted") != 0
            or gov.get("release_claims", {}).get("approved_stake_u") != 0):
        raise FreezeViolation("GOVERNANCE_RECORD_INVALID:MLB:HOP2")


def two_hop_manifest(candidate18: dict) -> dict:
    """Nov 15 + Nov 18 candidate manifest with the MLB pin advanced one reviewed hop, in memory only."""
    out = copy.deepcopy(candidate18)
    pins = out["sports"]["MLB"]["sources"]
    if pins.get(MLB_PATH) != PRIOR_BLOB:
        raise FreezeViolation("PRIOR_MLB_PIN_INVALID")
    pins[MLB_PATH] = NEW_BLOB
    return out


def per_sport_results(manifest: dict, repo: Path) -> dict:
    """Hash every pinned file; report each sport separately (the stock verify() stops at the first failure)."""
    if manifest.get("release") != "PAPER_0U" or manifest.get("official_counted") != 0:
        raise FreezeViolation("NO_OFFICIAL_RELEASE_ALLOWED")
    results = {}
    for sport in sorted(manifest["sports"]):
        try:
            for path, sha in sorted(manifest["sports"][sport]["sources"].items()):
                verified_file(repo, path, sha)
            results[sport] = "OK"
        except FreezeViolation as e:
            results[sport] = str(e)
    shared = {}
    for label, path, sha in (("frozen_engine", manifest["frozen_engine"]["path"], manifest["frozen_engine"]["git_blob_sha1"]),
                             ("risk_contract", manifest["risk_contract"]["path"], manifest["risk_contract"]["git_blob_sha1"]),
                             ("risk_overlay", manifest["risk_contract"]["overlay_path"], manifest["risk_contract"]["overlay_git_blob_sha1"])):
        try:
            verified_file(repo, path, sha)
            shared[label] = "OK"
        except FreezeViolation as e:
            shared[label] = str(e)
    return {"sports": results, "shared": shared}


def run(repo: Path = ROOT, scope: str = "MLB", candidate_path: Path = CANDIDATE_MANIFEST) -> dict:
    if scope not in ("MLB", "ALL"):
        raise FreezeViolation("UNSUPPORTED_SCOPE")
    # 1. Every unchanged check of the existing verifier, on the immutable manifests.
    raw = vt.LEGACY.read_bytes()
    legacy = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    raw18 = vt.TRANSITION.read_bytes()
    if git_blob_digest(raw18) != NOV18_MANIFEST_BLOB:
        raise FreezeViolation("NOV18_TRANSITION_MANIFEST_MODIFIED")
    transition18 = json.loads(raw18, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    candidate18 = vt.checked_manifest(legacy, transition18, raw)
    vt.check_provenance(repo)
    # 2. The new, exact MLB candidate manifest and its second-hop provenance.
    cand = json.loads(candidate_path.read_bytes(), object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    checked_candidate_manifest(cand)
    check_second_hop_provenance(repo)
    # 3. Hash the working tree against the two-hop manifest.
    res = per_sport_results(two_hop_manifest(candidate18), repo)
    failing = sorted(s for s, v in res["sports"].items() if v != "OK")
    gated = ["MLB"] if scope == "MLB" else sorted(res["sports"])
    gate_failures = sorted(s for s in gated if res["sports"][s] != "OK") + \
        sorted(k for k, v in res["shared"].items() if v != "OK")
    return {"status": "MLB_INPUT_SAFETY_TRANSITION_VERIFIED_PENDING_OWNER_MERGE_PAPER_0U" if not gate_failures
            else "GATE_FAILED", "scope": scope, "sports": res["sports"], "shared": res["shared"],
            "sports_not_matching_pins_outside_scope": [s for s in failing if s not in gated],
            "gate_failures": gate_failures, "legacy_manifest_unchanged": True,
            "nov18_transition_manifest_unchanged": True, "existing_verifiers_unmodified": {
                n: git_blob_digest((HERE / n).read_bytes()) == b for n, b in STOCK_VERIFIER_BLOBS.items()},
            "source_authenticated": False, "model_release_certified": False,
            "official_counted": 0, "approved_stake_u": 0}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scope", choices=("MLB", "ALL"), default="MLB")
    a = p.parse_args(argv)
    try:
        report = run(scope=a.scope)
    except FreezeViolation as e:
        print(json.dumps({"status": "REFUSED", "reason": str(e)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True, indent=1))
    return 0 if not report["gate_failures"] else 1


if __name__ == "__main__":
    sys.exit(main())
