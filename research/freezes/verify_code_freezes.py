#!/usr/bin/env python3
"""Verify pinned research-code baselines. Git blob SHA-1 asserts code identity, not PIT authenticity."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

SPORTS = frozenset(("NFL", "CBB", "CFB", "NBA", "MLB", "NHL", "PGA"))
REPO = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("frozen_baselines_20261115.json")


class FreezeViolation(ValueError):
    pass


def git_blob_digest(body: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(body)).encode("ascii") + b"\\0" + body).hexdigest()


def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise FreezeViolation("DUPLICATE_MANIFEST_KEY:" + key)
        out[key] = value
    return out


def reject_constant(value):
    raise FreezeViolation("NONFINITE_MANIFEST_VALUE")


def verified_file(root: Path, relative: str, expected: str):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise FreezeViolation("INVALID_RELATIVE_PATH")
    target = root / relative
    if not target.is_file() or target.is_symlink() or root.resolve() not in target.resolve().parents:
        raise FreezeViolation("UNSAFE_OR_MISSING_CODE:" + relative)
    if not isinstance(expected, str) or len(expected) != 40 or any(c not in "0123456789abcdef" for c in expected):
        raise FreezeViolation("INVALID_CODE_DIGEST:" + relative)
    actual = git_blob_digest(target.read_bytes())
    if actual != expected:
        raise FreezeViolation("CODE_CHANGED_SINCE_FREEZE:" + relative)
    return {"path": relative, "git_blob_sha1": actual}


def verify(manifest: dict, repo: Path) -> dict:
    if not isinstance(manifest, dict) or manifest.get("schema") != "sportsedge-research-code-freezes-v1":
        raise FreezeViolation("UNSUPPORTED_FREEZE_MANIFEST")
    sports = manifest.get("sports")
    if not isinstance(sports, dict) or set(sports) != SPORTS:
        raise FreezeViolation("SEVEN_SPORT_REGISTRY_REQUIRED")
    seen = []
    for sport in sorted(SPORTS):
        record = sports[sport]
        if not isinstance(record, dict) or record.get("status") not in (
            "CODE_BASELINE_LOCKED_RESEARCH", "CODE_BASELINE_LOCKED_UNCALIBRATED",
            "CODE_PINNED_ORIGINAL_496_MISSING", "PREFREEZE_CODE_PIN_ONLY_G18_ORIGINAL_MISSING",
            "PREFREEZE_CODE_PIN_ONLY_PIT_DATA_MISSING", "PREFREEZE_CODE_PIN_ONLY_NEEDS_KERNEL_INTEGRATION"):
            raise FreezeViolation("FREEZE_STATE_INVALID:" + sport)
        sources = record.get("sources")
        if not isinstance(sources, dict) or not sources:
            raise FreezeViolation("NO_CODE_SOURCES:" + sport)
        for path, sha in sorted(sources.items()):
            seen.append(verified_file(repo, path, sha))
    engine = manifest.get("frozen_engine")
    if not isinstance(engine, dict):
        raise FreezeViolation("MISSING_FROZEN_ENGINE")
    seen.append(verified_file(repo, engine["path"], engine["git_blob_sha1"]))
    risk = manifest.get("risk_contract")
    if not isinstance(risk, dict):
        raise FreezeViolation("MISSING_RISK_CONTRACT")
    seen.append(verified_file(repo, risk["path"], risk["git_blob_sha1"]))
    seen.append(verified_file(repo, risk["overlay_path"], risk["overlay_git_blob_sha1"]))
    if risk.get("limits", {}).get("game_u") != 2 or risk.get("limits", {}).get("daily_u") != 5:
        raise FreezeViolation("RISK_LOCK_MISMATCH")
    if manifest.get("release") != "PAPER_0U" or manifest.get("official_counted") != 0:
        raise FreezeViolation("NO_OFFICIAL_RELEASE_ALLOWED")
    return {"status": "CODE_IDENTITY_MATCH_ONLY_PAPER_0U", "sports": sorted(sports), "files": len(seen)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, default=MANIFEST)
    p.add_argument("--repo", type=Path, default=REPO)
    a = p.parse_args()
    data = json.loads(a.manifest.read_text(encoding="utf-8"),
                      object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    print(json.dumps(verify(data, a.repo), sort_keys=True))


if __name__ == "__main__":
    main()
