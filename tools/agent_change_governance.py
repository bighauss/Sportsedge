"""Trusted, fail-closed high-risk PR change-intake control for SportsEdge.

The GitHub pull_request_target job runs THIS code from the trusted base SHA,
reads changed paths and a manifest from the untrusted PR head as DATA, and
does not execute PR-head scripts or provide secrets. It cannot independently
verify a human approval, genuine model calibration, provider PIT provenance,
or betting-market release. ALL output stays PAPER / 0u.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

SCHEMA = "sportsedge-high-risk-agent-change-v1"
GOLDEN_SCHEMA = "sportsedge-agent-safety-golden-v1"
GOLDEN_SHA256 = "sha256:c09d93c207f122be752f0860cc844af99568eeed73766681f3ce6ba82652b6e0"
GOLDEN_CASES = 9
MAX_MANIFEST_BYTES = 50_000
SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
ISSUE = re.compile(r"^https://github\.com/bighauss/Sportsedge/issues/[1-9][0-9]*$")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
RISK_POLICY = "SPORTSEDGE_STRICT_V21_V22_20261115_R1"
REQUIRED = frozenset({
    "schema", "pr_number", "base_commit", "protected_paths", "ticket_url",
    "change_summary", "assumptions", "agent_identity", "permissions",
    "baseline", "golden", "evaluation", "rollback", "cost", "release_claims",
})


class GovernanceError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise GovernanceError("DUPLICATE_JSON_KEY")
        result[k] = v
    return result


def _not_number(raw):
    raise GovernanceError("NONFINITE_JSON_NUMBER")


def parse(raw: bytes):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_MANIFEST_BYTES:
        raise GovernanceError("JSON_EMPTY_OR_OVERSIZE")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=_not_number)
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, GovernanceError):
            raise
        raise GovernanceError("MALFORMED_JSON") from exc


def _keys(obj, required, name):
    if not isinstance(obj, dict) or set(obj) != set(required):
        raise GovernanceError("FIELDS_MISMATCH:" + name)
    return obj


def _text(value, name, limit=400):
    if (type(value) is not str or not value.strip() or
            value.strip() != value or len(value) > limit or
            any(ord(c) < 32 for c in value)):
        raise GovernanceError("INVALID_TEXT:" + name)
    return value


def _sha(value, label):
    if type(value) is not str or not SHA.fullmatch(value):
        raise GovernanceError("INVALID_GIT_SHA:" + label)
    return value


def _valid_path(value):
    if (type(value) is not str or not value or len(value) > 400 or
            value.startswith("/") or "\\" in value or
            any(part in ("", ".", "..") for part in value.split("/")) or
            any(ord(c) < 32 or ord(c) > 126 for c in value)):
        raise GovernanceError("INVALID_GIT_PATH")
    return value


def is_protected(path):
    path = _valid_path(path)
    return (path in {
        "RISK_POLICY.md", "CLAUDE.md", "AGENTS.md",
        "sportsedge_v5.py", "engine/sportsedge_v5.py",
        "tools/agent_change_governance.py",
        "tools/test_agent_change_governance.py",
    } or path.startswith((
        "models/", "research/risk/", "research/freezes/",
        "sportsedge/odds/", ".github/workflows/",
        "research/ai_governance/",
    )))


def classify_candidate(candidate):
    """ONLY synthetic agent-output safety behavior; not source attestation."""
    if (not isinstance(candidate, dict) or set(candidate) !=
            {"state", "official", "stake_u", "source_authenticated"}):
        return "BLOCK"
    if (candidate["state"] == "PAPER_0U" and
        candidate["official"] is False and
        type(candidate["stake_u"]) is int and candidate["stake_u"] == 0 and
        candidate["source_authenticated"] is False):
        return "ALLOW_RESEARCH"
    return "BLOCK"


def golden_regression(raw):
    if "sha256:" + sha256(raw).hexdigest() != GOLDEN_SHA256:
        raise GovernanceError("GOLDEN_DATASET_HASH_DRIFT")
    data = parse(raw)
    _keys(data, {"schema", "scope", "cases"}, "golden")
    if data["schema"] != GOLDEN_SCHEMA or type(data["cases"]) is not list or (
            len(data["cases"]) != GOLDEN_CASES):
        raise GovernanceError("GOLDEN_DATASET_SHAPE_DRIFT")
    seen = set()
    for case in data["cases"]:
        if not isinstance(case, dict) or set(case) not in (
                {"id", "candidate", "expected"},
                {"id", "candidate", "expected", "untrusted_input"}):
            raise GovernanceError("INVALID_GOLDEN_CASE")
        name = _text(case["id"], "golden.id", 128)
        if name in seen:
            raise GovernanceError("DUPLICATE_GOLDEN_CASE")
        seen.add(name)
        if case["expected"] not in ("BLOCK", "ALLOW_RESEARCH") or (
                classify_candidate(case["candidate"]) != case["expected"]):
            raise GovernanceError("GOLDEN_SAFETY_REGRESSION:" + name)
    return {"dataset_sha256": GOLDEN_SHA256, "cases": len(seen),
            "failed": 0, "official_counted": 0, "approved_stake_u": 0}


def _same_typed_dict(given, expected):
    """Prevent bool==0, 0==False, or 1==True in policy/security fields."""
    return (type(given) is dict and set(given) == set(expected) and all(
        type(given[key]) is type(value) and given[key] == value
        for key, value in expected.items()
    ))


def _finite_usd(raw, name):
    if type(raw) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,4})?", raw):
        raise GovernanceError("INVALID_USD_AMOUNT:" + name)
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise GovernanceError("INVALID_USD_AMOUNT:" + name) from exc
    if not value.is_finite() or value < 0 or value > 1000000:
        raise GovernanceError("USD_OUT_OF_BOUNDS:" + name)


def validate_manifest(raw, *, pr_number, base_commit, changed_paths):
    if type(pr_number) is not int or pr_number < 1:
        raise GovernanceError("INVALID_PR_NUMBER")
    _sha(base_commit, "base")
    if not isinstance(changed_paths, (list, tuple)) or not changed_paths:
        raise GovernanceError("NO_CHANGED_PATHS")
    checked = [_valid_path(p) for p in changed_paths]
    if len(checked) != len(set(checked)):
        raise GovernanceError("DUPLICATE_CHANGED_PATH")
    protected = sorted(path for path in checked if is_protected(path))
    if not protected:
        return {"state": "PASS_NO_PROTECTED_DIFF", "protected_paths": [],
                "external_owner_approval_verified": False,
                "model_release_certified": False,
                "official_counted": 0, "approved_stake_u": 0}
    if raw is None:
        raise GovernanceError("HIGH_RISK_CHANGE_MANIFEST_REQUIRED")
    doc = parse(raw)
    _keys(doc, REQUIRED, "manifest")
    if doc["schema"] != SCHEMA or type(doc["pr_number"]) is not int or (
            doc["pr_number"] != pr_number) or doc["base_commit"] != base_commit:
        raise GovernanceError("MANIFEST_PR_OR_BASE_MISMATCH")
    _sha(doc["base_commit"], "manifest_base")
    if doc["protected_paths"] != protected:
        raise GovernanceError("MANIFEST_PROTECTED_PATH_CENSUS_MISMATCH")
    if not isinstance(doc["ticket_url"], str) or not ISSUE.fullmatch(doc["ticket_url"]):
        raise GovernanceError("ISSUE_URL_REQUIRED")
    _text(doc["change_summary"], "change_summary", 1000)
    assumptions = doc["assumptions"]
    if (not isinstance(assumptions, list) or not 1 <= len(assumptions) <= 20 or
            any(type(s) is not str for s in assumptions)):
        raise GovernanceError("ASSUMPTIONS_REQUIRED")
    for s in assumptions:
        _text(s, "assumption", 500)
    _text(doc["agent_identity"], "agent_identity", 128)
    permissions = _keys(doc["permissions"], {
        "role", "repo_write", "secrets_read", "production_deploy",
        "market_release", "merge_rights",
    }, "permissions")
    if (not _same_typed_dict(permissions, {
        "role": "CODING_AGENT", "repo_write": "BRANCH_ONLY",
        "secrets_read": False, "production_deploy": False,
        "market_release": False, "merge_rights": "REPO_RULES_ONLY",
    })):
        raise GovernanceError("AGENT_LEAST_PRIVILEGE_NOT_DECLARED")
    baseline = _keys(doc["baseline"], {
        "metric", "before", "unit", "source_state",
    }, "baseline")
    _text(baseline["metric"], "baseline.metric", 160)
    _text(baseline["unit"], "baseline.unit", 80)
    if baseline["source_state"] == "UNKNOWN":
        if baseline["before"] is not None:
            raise GovernanceError("UNKNOWN_BASELINE_MUST_BE_NULL")
    elif baseline["source_state"] == "SELF_REPORTED":
        _finite_usd(baseline["before"], "baseline.before")
    else:
        raise GovernanceError("BASELINE_SOURCE_STATE_INVALID")
    golden = _keys(doc["golden"], {"sha256", "cases", "suite"}, "golden")
    if not _same_typed_dict(golden, {
            "sha256": GOLDEN_SHA256, "cases": GOLDEN_CASES,
            "suite": "SYNTHETIC_AGENT_SAFETY"}):
        raise GovernanceError("GOLDEN_PIN_INVALID")
    evaluation = _keys(doc["evaluation"], {
        "method", "test_command", "external_review_state",
        "unseen_data_verified",
    }, "evaluation")
    if (evaluation["method"] != "DETERMINISTIC_REGRESSION" or
            evaluation["external_review_state"] != "NOT_VERIFIED" or
            evaluation["unseen_data_verified"] is not False):
        raise GovernanceError("EVALUATION_SELF_CERTIFICATION_REFUSED")
    command = _text(evaluation["test_command"], "evaluation.test_command", 250)
    if not command.startswith("python -m unittest "):
        raise GovernanceError("REPRODUCIBLE_UNIT_TEST_COMMAND_REQUIRED")
    rollback = _keys(doc["rollback"], {
        "target_base_sha", "strategy", "verification_command",
    }, "rollback")
    if rollback["target_base_sha"] != base_commit or (
            rollback["strategy"] != "REVIEWED_REVERT_PR"):
        raise GovernanceError("ROLLBACK_BASE_OR_STRATEGY_MISMATCH")
    _sha(rollback["target_base_sha"], "rollback_sha")
    rollback_test = _text(rollback["verification_command"], "rollback.verification_command")
    if not rollback_test.startswith("python -m unittest "):
        raise GovernanceError("ROLLBACK_VERIFICATION_REQUIRED")
    cost = _keys(doc["cost"], {
        "currency", "measurement", "usd", "receipt_sha256",
        "outcome_per_dollar",
    }, "cost")
    if cost["currency"] != "USD" or cost["outcome_per_dollar"] is not None:
        raise GovernanceError("UNSUPPORTED_COST_CLAIM")
    if cost["measurement"] == "UNKNOWN":
        if cost["usd"] is not None or cost["receipt_sha256"] is not None:
            raise GovernanceError("UNKNOWN_COST_MUST_BE_NULL")
    elif cost["measurement"] == "SELF_REPORTED":
        _finite_usd(cost["usd"], "cost.usd")
        if type(cost["receipt_sha256"]) is not str or not SHA256.fullmatch(cost["receipt_sha256"]):
            raise GovernanceError("MEASURED_COST_RECEIPT_DIGEST_REQUIRED")
    else:
        raise GovernanceError("COST_MEASUREMENT_STATE_INVALID")
    if not _same_typed_dict(doc["release_claims"], {
            "policy_id": RISK_POLICY, "production_ready": False,
            "external_owner_approval_verified": False,
            "source_authenticated": False, "model_release_certified": False,
            "official_counted": 0, "approved_stake_u": 0}):
        raise GovernanceError("PRODUCTION_OR_SOURCE_PROMOTION_CLAIM_REFUSED")
    # A manifest is untrusted PR data. Its assertions are NOT verification,
    # a merge approval, proof of outside review, or permission to bet.
    return {"state": "PASS_DECLARED_REVIEW_ONLY",
            "protected_paths": protected,
            "external_owner_approval_verified": False,
            "model_release_certified": False,
            "official_counted": 0, "approved_stake_u": 0}


def _git(repo, args):
    result = subprocess.run(["git", "-C", str(repo), *args], check=False,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=30)
    if result.returncode:
        raise GovernanceError("GIT_READ_OR_REVISION_FAILED")
    return result.stdout


def inspect_pr(repo: Path, *, base_commit, head_commit, pr_number):
    """Trusted base checkout: inspect PR HEAD solely via git diff/show, no exec."""
    _sha(base_commit, "base")
    _sha(head_commit, "head")
    if base_commit == head_commit:
        raise GovernanceError("PR_HEAD_EQUALS_BASE")
    paths = _git(repo, ["diff", "--no-renames", "--name-only", "-z",
                         base_commit, head_commit])
    try:
        changed = [x.decode("utf-8") for x in paths.split(b"\x00") if x]
    except UnicodeError as exc:
        raise GovernanceError("NON_UTF8_CHANGED_PATH") from exc
    protected = [p for p in changed if is_protected(p)]
    data = None
    if protected:
        manifest_path = f"docs/governance/changes/pr-{pr_number}.json"
        try:
            data = _git(repo, ["show", f"{head_commit}:{manifest_path}"])
        except GovernanceError as exc:
            raise GovernanceError("HIGH_RISK_CHANGE_MANIFEST_REQUIRED") from exc
    return validate_manifest(data, pr_number=pr_number,
                             base_commit=base_commit, changed_paths=changed)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", default=".")
    p.add_argument("--base-sha", required=True)
    p.add_argument("--head-sha", required=True)
    p.add_argument("--pr-number", type=int, required=True)
    p.add_argument("--golden", default="research/ai_governance/golden_agent_safety_v1.json")
    args = p.parse_args(argv)
    try:
        golden = golden_regression(Path(args.golden).read_bytes())
        result = inspect_pr(Path(args.repo), base_commit=args.base_sha,
                            head_commit=args.head_sha, pr_number=args.pr_number)
    except (GovernanceError, OSError, subprocess.TimeoutExpired) as exc:
        # The exception must never contain original untrusted manifest bytes.
        print(json.dumps({"state": "BLOCK", "reason_code": str(exc),
                          "official_counted": 0, "approved_stake_u": 0}))
        return 2
    print(json.dumps({**result, "golden": golden}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
