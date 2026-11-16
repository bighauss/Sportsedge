"""Seven-sport, per-market *structural* research audit for Issue #10.

This is intentionally separate from the original aggregate forward_acceptance
assessor. Operator-provided manifests cannot authenticate upstream observations,
prove market inventory completeness or authorize stakes. It ALWAYS returns
PAPER/0u regardless of the reported numbers.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from sportsedge.validation.forward_acceptance import analyze, require_private_path
from research.risk.strict_v21_v22 import POLICY_VERSION as LOCKED_POLICY_VERSION

SCHEMA = "sportsedge-seven-sport-market-gates-v1"
POLICY = LOCKED_POLICY_VERSION
SPORTS = frozenset(("NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"))
FAMILIES = frozenset(("ML", "SPREAD", "TOTAL", "TEAM_TOTAL",
                       "PLAYER_PROP", "PERIOD", "ALTERNATE", "SPECIAL",
                       "SGP", "DFS", "OUTRIGHT", "MATCHUP", "OTHER"))
PERIOD = re.compile(r"^[A-Z0-9_]{1,24}$")
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:/.+~-]{0,95}$")
ROOT_FIELDS = frozenset(("schema", "rules_version", "markets"))
ROW_FIELDS = frozenset(("sport", "market_family", "period",
                        "market_key", "evidence_manifest"))


def _strict_object(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("INVALID_FIELDS:" + label)
    return value


def _pairs_no_duplicates(pairs):
    out = {}
    for name, value in pairs:
        if name in out:
            raise ValueError("DUPLICATE_JSON_KEY:" + name)
        out[name] = value
    return out


def _reject_constant(token):
    raise ValueError("NONFINITE_JSON:" + token)


def assess(matrix):
    """Assess every declared market separately; never promote any market."""
    _strict_object(matrix, ROOT_FIELDS, "root")
    if matrix["schema"] != SCHEMA:
        raise ValueError("INVALID_MATRIX_SCHEMA")
    if matrix["rules_version"] != POLICY:
        raise ValueError("UNAPPROVED_RISK_POLICY_VERSION")
    entries = matrix["markets"]
    if not isinstance(entries, list) or not (7 <= len(entries) <= 5000):
        raise ValueError("INVALID_MARKET_ENTRY_COUNT")

    seen = set()
    cross_scope = {"card_id": set(), "bet_id": set(), "cycle_id": set()}
    covered = set()
    assessments = []
    for i, entry in enumerate(entries):
        _strict_object(entry, ROW_FIELDS, "market")
        sport = entry["sport"]
        family = entry["market_family"]
        period = entry["period"]
        key = entry["market_key"]
        if type(sport) is not str or sport not in SPORTS:
            raise ValueError("UNKNOWN_SPORT")
        if type(family) is not str or family not in FAMILIES:
            raise ValueError("UNKNOWN_MARKET_FAMILY")
        if type(period) is not str or PERIOD.fullmatch(period) is None:
            raise ValueError("INVALID_PERIOD")
        if type(key) is not str or KEY.fullmatch(key) is None:
            raise ValueError("INVALID_MARKET_KEY")
        identity = (sport, family, period, key)
        if identity in seen:
            raise ValueError("DUPLICATE_MARKET_IDENTITY")
        seen.add(identity)
        covered.add(sport)

        evidence = entry["evidence_manifest"]
        if evidence is None:
            summary = {"reported_structural_thresholds": {},
                       "reported_all_structural_thresholds_met": False,
                       "reason": "NO_SUBMITTED_EVIDENCE"}
        else:
            # Evidence must be scoped to this exact market; a single unscoped
            # card/cycle/close must not be counted again under another key.
            if not isinstance(evidence, dict):
                raise ValueError("INVALID_EVIDENCE_MANIFEST")
            for collection, id_key in (("cards", "card_id"),
                                       ("clv_triples", "bet_id"),
                                       ("calibration_cycles", "cycle_id")):
                values = evidence.get(collection)
                if not isinstance(values, list):
                    raise ValueError("INVALID_EVIDENCE_COLLECTION:" + collection)
                for value in values:
                    if not isinstance(value, dict) or type(value.get(id_key)) is not str:
                        raise ValueError("INVALID_EVIDENCE_ID:" + id_key)
                    # Prefixes do not add proof; identical IDs reused across
                    # two market partitions are conservatively quarantined.
                    ident = value[id_key]
                    if ident in cross_scope[id_key]:
                        raise ValueError("CROSS_MARKET_EVIDENCE_REUSE:" + id_key)
                    cross_scope[id_key].add(ident)
            result = analyze(evidence)
            summary = {
                "reported_structural_thresholds": {
                    name: gate["structural_threshold_met"]
                    for name, gate in result["gates"].items()
                },
                "reported_all_structural_thresholds_met":
                    result["reported_all_structural_thresholds_met"],
                "reason": "EXTERNAL_AUTHENTICATION_AND_SIGNED_PROMOTION_REQUIRED"
            }
        assessments.append({
            "sport": sport, "market_family": family,
            "period": period, "market_key": key,
            "status": "PAPER_0U_NOT_CERTIFIED",
            "externally_certified": False, "approved_stake_u": 0,
            **summary
        })

    if covered != SPORTS:
        raise ValueError("MISSING_SPORT_COVERAGE:" + ",".join(sorted(SPORTS - covered)))

    by_sport = Counter(entry["sport"] for entry in assessments)
    return {
        "schema": SCHEMA, "rules_version": POLICY,
        "status": "PAPER_0U_EXTERNAL_PROOF_MISSING",
        "approved_stake_u": 0, "official_market_count": 0,
        "release_certified": False,
        "market_entries": len(assessments),
        "declared_market_count_by_sport": dict(sorted(by_sport.items())),
        "coverage_is_authenticated_inventory": False,
        "notes": [
            "A declared market row is not proof it was offered or captured",
            "Structural thresholds never authenticate provider identity or PIT source publication",
            "No cross-market pooling, official picks, wagers, or automatic promotion"
        ],
        "markets": assessments
    }


def report_file(source, destination):
    """Read and write private files only, and never overwrite a report."""
    src = require_private_path(source, label="MARKET_MATRIX_INPUT")
    dst = require_private_path(destination, label="MARKET_MATRIX_REPORT")
    if src == dst:
        raise ValueError("INPUT_AND_OUTPUT_MUST_DIFFER")
    data = src.read_bytes()
    if not data or len(data) > 20_000_000:
        raise ValueError("INPUT_EMPTY_OR_TOO_LARGE")
    matrix = json.loads(data.decode("utf-8"),
                        object_pairs_hook=_pairs_no_duplicates,
                        parse_constant=_reject_constant)
    report = assess(matrix)
    report["input_sha256"] = "sha256:" + sha256(data).hexdigest()
    payload = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
               + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(dst, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix_json")
    parser.add_argument("--report", required=True, help="new private output JSON")
    args = parser.parse_args(argv)
    result = report_file(args.matrix_json, args.report)
    print(json.dumps({"status": result["status"],
                      "market_entries": result["market_entries"],
                      "release_certified": False,
                      "approved_stake_u": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
