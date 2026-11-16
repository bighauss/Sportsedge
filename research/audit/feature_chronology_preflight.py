#!/usr/bin/env python3
"""Fail-closed, cross-sport feature/publication chronology preflight.

Research-only. Inputs are private frozen CSVs. Exact SHA-256 text and claimed
timestamps are NOT independent provider authentication or external WORM proof.
No outputs here authorize bets or rewrite a historical model.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HEXDIGEST = re.compile(r"^[0-9a-fA-F]{64}$")
SPORTS = frozenset({"NFL", "CFB", "CBB", "NBA", "MLB", "NHL"})
PROJECTION_FIELDS = (
    "selection_id", "sport", "event_id", "market", "model_asof_utc",
    "quote_captured_utc", "kickoff_utc", "model_sha256", "quote_sha256",
)
FEATURE_FIELDS = (
    "selection_id", "feature_id", "published_utc", "captured_utc",
    "source_sha256",
)


def utc(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("MISSING_TIME")
    try:
        moment = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIME") from exc
    if moment.utcoffset() != dt.timedelta(0) or moment.tzinfo is None:
        raise ValueError("NOT_UTC")
    return moment


def required(record, fields):
    return [key for key in fields if not str(record.get(key) or "").strip()]


def assess(projections, features):
    """Retain every row; never select a favorable duplicate by input order."""
    projections, features = list(projections), list(features)
    feature_by_selection = defaultdict(list)
    for index, feature in enumerate(features, 2):
        feature_by_selection[str(feature.get("selection_id") or "").strip()].append((index, feature))
    seen_counts = Counter(str(p.get("selection_id") or "").strip() for p in projections)
    results = []
    encountered = set()

    for index, prediction in enumerate(projections, 2):
        selection_id = str(prediction.get("selection_id") or "").strip()
        if selection_id:
            encountered.add(selection_id)
        flags = []
        missing = required(prediction, PROJECTION_FIELDS)
        if missing:
            flags.append("MISSING_PROJECTION_FIELDS:" + ",".join(missing))
        if prediction.get("sport") not in SPORTS:
            flags.append("UNKNOWN_SPORT")
        if seen_counts[selection_id] > 1:
            flags.append("DUPLICATE_SELECTION_ID")
        for field in ("model_sha256", "quote_sha256"):
            if not HEXDIGEST.fullmatch(str(prediction.get(field) or "")):
                flags.append("INVALID_" + field.upper())

        try:
            forecast = utc(prediction.get("model_asof_utc"))
            quote = utc(prediction.get("quote_captured_utc"))
            kickoff = utc(prediction.get("kickoff_utc"))
            if forecast > quote:
                flags.append("MODEL_ASOF_AFTER_QUOTE_CAPTURE")
            if quote >= kickoff:
                flags.append("QUOTE_NOT_PREGAME")
            if forecast >= kickoff:
                flags.append("MODEL_NOT_PREGAME")
        except ValueError as exc:
            flags.append("INVALID_PREDICTION_TIME:" + str(exc))
            forecast = kickoff = None

        selected_features = feature_by_selection.get(selection_id, [])
        if not selected_features:
            flags.append("NO_FEATURE_EVIDENCE")
        counts = Counter(str(item.get("feature_id") or "").strip() for _, item in selected_features)
        for feature_row_number, feature in selected_features:
            no_fields = required(feature, FEATURE_FIELDS)
            if no_fields:
                flags.append(f"FEATURE_ROW_{feature_row_number}_MISSING:" + ",".join(no_fields))
            if counts[str(feature.get("feature_id") or "").strip()] > 1:
                flags.append("DUPLICATE_FEATURE_VERSION")
            if not HEXDIGEST.fullmatch(str(feature.get("source_sha256") or "")):
                flags.append(f"FEATURE_ROW_{feature_row_number}_BAD_HASH")
            try:
                published = utc(feature.get("published_utc"))
                captured = utc(feature.get("captured_utc"))
                if published > captured:
                    flags.append(f"FEATURE_ROW_{feature_row_number}_PUBLISHED_AFTER_CAPTURE")
                if forecast is not None and (published > forecast or captured > forecast):
                    flags.append(f"FEATURE_ROW_{feature_row_number}_AFTER_MODEL")
                if kickoff is not None and published >= kickoff:
                    flags.append(f"FEATURE_ROW_{feature_row_number}_AFTER_KICKOFF")
            except ValueError as exc:
                flags.append(f"FEATURE_ROW_{feature_row_number}_INVALID_TIME:" + str(exc))

        flags = sorted(set(flags))
        results.append({
            "prediction_row": index, "selection_id": selection_id,
            "chronology_consistent_unverified": not bool(flags),
            "flags": flags, "feature_count": len(selected_features),
        })

    orphan_features = [
        {"feature_row": index, "selection_id": str(item.get("selection_id") or "").strip(),
         "reason": "NO_MATCHING_PREDICTION"}
        for index, item in enumerate(features, 2)
        if str(item.get("selection_id") or "").strip() not in encountered
    ]
    return {
        "status": "PAPER_0U_SOURCE_AUTHENTICITY_NOT_VERIFIED",
        "prediction_rows": len(projections), "feature_rows": len(features),
        "chronology_consistent_unverified": sum(int(x["chronology_consistent_unverified"]) for x in results),
        "blocked": len(results) - sum(int(x["chronology_consistent_unverified"]) for x in results),
        "results": results, "orphan_features": orphan_features,
        "limitations": (
            "Hash format and claimed UTC chronology do not prove a bookmaker quote, "
            "feature publication time, provider authenticity, timestamp authority, "
            "or that feature bytes match the claim. No official or tradable edge."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen_predictions_csv", type=Path)
    parser.add_argument("feature_manifest_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.frozen_predictions_csv.open(newline="", encoding="utf-8-sig") as stream:
        predictions = list(csv.DictReader(stream))
    with args.feature_manifest_csv.open(newline="", encoding="utf-8-sig") as stream:
        features = list(csv.DictReader(stream))
    report = assess(predictions, features)
    # Create-only output: never mutate or overwrite original evidence.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({
        "status": report["status"], "blocked": report["blocked"],
        "chronology_consistent_unverified": report["chronology_consistent_unverified"],
        "orphan_features": len(report["orphan_features"]),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
