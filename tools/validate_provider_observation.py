"""Fail-closed validation for research-only provider observation manifests.

This does not certify original point-in-time receipts or promote any market.
"""
import datetime
import json
import re

EXPECTED = {"cfbd_games_2026_w1", "odds_nfl_events", "apisports_football_status"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_manifest(document):
    errors = []
    if not isinstance(document, dict):
        return ["manifest_not_object"]
    if document.get("schema_version") != 1:
        errors.append("schema_version")
    if document.get("gate_a") != "OPEN" or document.get("market_state") != "PAPER/0u":
        errors.append("unsafe_market_state")
    if document.get("no_original_bytes_archived") is not True:
        errors.append("original_bytes_claim")
    if document.get("not_a_point_in_time_quote_receipt") is not True:
        errors.append("receipt_claim")
    rows = document.get("observations")
    if not isinstance(rows, list):
        return errors + ["observations_not_list"]
    names = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row_{index}_not_object")
            continue
        name = row.get("source")
        names.append(name if isinstance(name, str) else None)
        if name not in EXPECTED:
            errors.append(f"row_{index}_unknown_source")
        if row.get("status") != "observed" or row.get("research_only") is not True:
            errors.append(f"row_{index}_not_observed")
        if row.get("http_status") != 200:
            errors.append(f"row_{index}_http")
        if not isinstance(row.get("byte_count"), int) or isinstance(row.get("byte_count"), bool) or not 0 < row["byte_count"] <= 2000000:
            errors.append(f"row_{index}_bytes")
        if not isinstance(row.get("sha256"), str) or not SHA256.fullmatch(row["sha256"]):
            errors.append(f"row_{index}_sha")
        if row.get("top_level_type") not in ("list", "dict"):
            errors.append(f"row_{index}_type")
        try:
            stamp = row["observed_at_utc"]
            if not isinstance(stamp, str) or not (
                stamp.endswith("Z") or stamp.endswith("+00:00")
            ):
                raise ValueError("not_canonical_utc")
            normalized = stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp
            parsed = datetime.datetime.fromisoformat(normalized)
            if parsed.tzinfo is None or parsed.utcoffset() != datetime.timedelta(0):
                raise ValueError("not_utc")
            if parsed > datetime.datetime.now(datetime.timezone.utc):
                raise ValueError("future_observation")
        except (KeyError, ValueError, TypeError, AttributeError):
            errors.append(f"row_{index}_timestamp")
    if len(names) != len(EXPECTED) or set(names) != EXPECTED or len(set(names)) != len(names):
        errors.append("missing_or_duplicate_source")
    return errors


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()
    with open(args.manifest, encoding="utf-8") as f:
        errors = validate_manifest(json.load(f))
    if errors:
        print("INVALID: " + ", ".join(errors))
        raise SystemExit(1)
    print("VALID RESEARCH METADATA ONLY — NOT AN ODDS RECEIPT; GATE A OPEN")
