"""Whole SportsEdge repository release-readiness audit, strictly non-certifying.

A local code freeze digest, self-declared market gate flags, and successful
synthetic GitHub CI are NOT evidence of real authenticated bookmaker offers,
contemporaneous PIT observations, independent signed reviews or +EV.

This tool NEVER issues a production certificate, wager or promotion. It
compares the current strict risk policy with the 49-row historical release
matrix, verifies frozen code identity and accurately names missing evidence.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from research.freezes.verify_code_freezes import FreezeViolation, verify as verify_freezes
from research.risk.strict_v21_v22 import POLICY_VERSION
from sportsedge.validation.daily_safety_sweep import inspect_matrix

REPO = Path(__file__).resolve().parents[1]
MATRIX_PATH = Path("research/freezes/market_release_matrix_20261115.json")
FREEZE_PATH = Path("research/freezes/frozen_baselines_20261115.json")
RISK_PATH = Path("RISK_POLICY.md")
SCHEMA = "sportsedge-whole-repo-precertification-v1"


class PolicyError(ValueError):
    """The requested local reporting context is invalid."""


def parse_unique_json(raw: bytes):
    """Strict, duplicate-safe JSON parse; never trust last-key-wins evidence."""
    if type(raw) is not bytes or not raw or len(raw) > 50_000_000:
        raise ValueError("MISSING_OR_OVERSIZED_AUDIT_INPUT")

    def unique(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise ValueError("DUPLICATE_JSON_KEY:" + key)
            data[key] = value
        return data

    def nonfinite(raw_value):
        raise ValueError("NONFINITE_JSON:" + raw_value)

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=nonfinite)


def audit(repo: Path, *, matrix: dict, freeze: dict,
          asof_date_ct: str) -> dict:
    """Inspect current checkout; separate identity checks from release claims.

    The five external A–E gates and signed promotion are NOT independently
    verifiable from public repo contents. No self-reported array of 100
    cards/200 closes or all-green CI can change this conclusion.
    """
    try:
        asof = date.fromisoformat(asof_date_ct)
        if asof.isoformat() != asof_date_ct:
            raise ValueError("NONCANONICAL_DATE")
    except (TypeError, ValueError) as exc:
        raise PolicyError("ASOF_MUST_BE_EXACT_YYYY_MM_DD") from exc

    root = Path(repo).resolve()
    blockers = []
    findings = []

    policy_file = root / RISK_PATH
    if not policy_file.is_file():
        blockers.append("ROOT_RISK_POLICY_MISSING")
        locked_text = ""
        risk_digest = None
    else:
        original = policy_file.read_bytes()
        locked_text = original.decode("utf-8")
        risk_digest = "sha256:" + sha256(original).hexdigest()
        if "**Policy ID:** `" + POLICY_VERSION + "`" not in locked_text:
            blockers.append("ROOT_RISK_POLICY_ID_INCONSISTENT")

    if not isinstance(matrix, dict):
        raise ValueError("RELEASE_MATRIX_MUST_BE_OBJECT")
    risk_claim = matrix.get("policy")
    if risk_claim != POLICY_VERSION:
        blockers.append("MATRIX_POLICY_MISMATCH")
        findings.append("Default historical matrix carries a different risk-policy version; "
                        "do not rewrite it into a new supposedly original snapshot.")
    matrix_date = matrix.get("asof_date_ct")
    try:
        parsed_matrix_date = date.fromisoformat(matrix_date)
    except (ValueError, TypeError):
        blockers.append("MATRIX_ASOF_INVALID")
    else:
        if parsed_matrix_date > asof:
            blockers.append("MATRIX_FROM_FUTURE")
        elif parsed_matrix_date < asof:
            blockers.append("MATRIX_ASOF_NOT_CURRENT")

    try:
        release = inspect_matrix(matrix)
    except (TypeError, ValueError, KeyError) as exc:
        # The older standalone daily sweep can raise on unexpected unhashable
        # market identities. A whole-repo certification report must record a
        # fail-closed reason rather than lose the audit to a traceback.
        release = {
            "status": "BLOCK",
            "issues": ["MALFORMED_MARKET_MATRIX:" + type(exc).__name__],
        }
    if release.get("status") != "PAPER_0U_SAFE_MATRIX" or release.get("issues"):
        blockers.append("RELEASE_MATRIX_UNSAFE_OR_INCOMPLETE")

    markets = matrix.get("markets", [])
    if not isinstance(markets, list):
        markets = []
    claims = 0
    for row in markets:
        if not isinstance(row, dict):
            continue
        flags = row.get("gates")
        if isinstance(flags, dict):
            claims += sum(flags.get(name) is True for name in "ABCDE")
    if claims:
        # A boolean in this repo is NEVER an independent publisher witness.
        blockers.append("UNVERIFIED_SELF_REPORTED_GATE_PASSES")
    if len(markets) != 49:
        blockers.append("EXPECTED_SEVEN_SPORT_FORTY_NINE_FAMILY_ROWS_MISSING")

    try:
        pinned = verify_freezes(freeze, root)
        code_freeze = {
            "status": pinned["status"],
            "pinned_sports": pinned["sports"],
            "pinned_files_checked": pinned["files"],
        }
    except (FreezeViolation, KeyError, ValueError, TypeError) as exc:
        blockers.append("FROZEN_CODE_IDENTITY_INVALID")
        code_freeze = {
            "status": "CODE_IDENTITY_CHECK_FAILED",
            "reason_code": type(exc).__name__,
        }

    # No public source can authenticate a real bookmaker-independent original
    # receipt, completeness across all actual offered markets, preregistered
    # forward sets, or independently signed per-market promotion.
    blockers.extend([
        "ORIGINAL_BOOKMAKER_AND_PIT_PROOF_MISSING",
        "FORWARD_CALIBRATION_AND_CLV_PROOF_MISSING",
        "AUTHENTIC_100_CARD_5_DAY_EVIDENCE_MISSING",
        "INDEPENDENT_SIGNED_PROMOTION_MISSING",
    ])

    # Never allow an untrusted input to choose or claim an official stake.
    return {
        "schema": SCHEMA,
        "assessed_asof_ct": asof.isoformat(),
        "release_verdict": "NOT_CERTIFIED",
        "production_certified": False,
        "research_software_certified": False,
        "official_market_count": 0,
        "approved_stake_u": 0,
        "source_authenticated": False,
        "independent_review_verified": False,
        "frozen_engine_or_risk_may_be_used_for_wagering": False,
        "locked_risk_policy_id": POLICY_VERSION,
        "matrix_claimed_risk_policy_id": risk_claim,
        "risk_policy_file_sha256": risk_digest,
        "matrix_asof_ct": matrix_date,
        "declared_market_families": len(markets),
        "declared_closed_gate_claims": claims,
        "unverified_gate_requirements": 5 * len(markets),
        "market_safety_audit_status": release.get("status"),
        "market_safety_issue_count": len(release.get("issues", [])),
        "code_freeze": code_freeze,
        "gates": {gate: {"state": "OPEN", "external_proof_verified": False}
                  for gate in "ABCDE"},
        "whole_program": {
            "complete_real_slate_runs_verified": 0,
            "settled_comparable_triples_verified": 0,
            "registered_leak_free_cycles_verified": 0,
            "continuous_five_day_acceptance_verified": False,
            "owner_signed_market_promotion_verified": False,
        },
        "blockers": sorted(set(blockers)),
        "findings": findings,
        "scope_limits": [
            "Code freeze identity is not model calibration or original data provenance.",
            "The local matrix is a declared status inventory, not a bookmaker-offered slate.",
            "This tool does not inspect private receipts, GitHub Actions logs, "
            "external review signatures or all 76 workflows.",
            "It does not certify each of the 622 tracked source files or prove absence of bugs.",
            "Verified evidence must be collected independently and reviewed under Issue #10.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=REPO)
    p.add_argument("--asof-date-ct", default=datetime.now(
        ZoneInfo("America/Chicago")).date().isoformat())
    p.add_argument("--require-production-certification", action="store_true")
    args = p.parse_args(argv)
    root = args.repo.resolve()
    matrix = parse_unique_json((root / MATRIX_PATH).read_bytes())
    freeze = parse_unique_json((root / FREEZE_PATH).read_bytes())
    report = audit(root, matrix=matrix, freeze=freeze,
                   asof_date_ct=args.asof_date_ct)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    # A successful audit invocation does NOT mean that a certificate was issued.
    # Strict mode is intentionally nonzero as long as external A-E proofs are
    # unavailable; no user-supplied JSON can override the release hold.
    return 3 if args.require_production_certification else 0


if __name__ == "__main__":
    raise SystemExit(main())
