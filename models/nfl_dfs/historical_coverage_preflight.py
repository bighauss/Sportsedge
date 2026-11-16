"""Fail-closed prospective DFS historical replay coverage preflight (stdlib only).

This audits *claims* and local bytes, not upstream authenticity. Never upgrades
a retrospective slate to a real point-in-time capture without independent receipts.
"""
import argparse
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path

REQUIRED_ROLES = ("model", "game_config", "salary", "roster", "final")
PRE = {"model", "game_config", "salary", "roster"}

def utc(s):
    try:
        v = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as e:
        raise ValueError("INVALID_TIMESTAMP") from e
    if v.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return v.astimezone(dt.timezone.utc)

def check_slate(slate, root):
    reasons = []
    def reject(reason):
        if reason not in reasons:
            reasons.append(reason)
    event = slate.get("event_id")
    if not isinstance(event, str) or not event.strip():
        reject("MISSING_EVENT_ID")
    try:
        kickoff = utc(slate["kickoff_utc"])
    except (ValueError, KeyError, TypeError):
        kickoff = None
        reject("INVALID_KICKOFF")
    assets = slate.get("assets")
    if not isinstance(assets, list):
        assets = []
        reject("MISSING_ASSETS")
    by_role = {}
    for a in assets:
        if not isinstance(a, dict):
            reject("INVALID_ASSET")
            continue
        role = a.get("role")
        if role not in REQUIRED_ROLES:
            reject("UNKNOWN_ROLE")
            continue
        if role in by_role:
            reject("DUPLICATE_ROLE:" + role)
            continue
        by_role[role] = a
        digest = a.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            reject("BAD_SHA256:" + role)
        name = a.get("path")
        if not isinstance(name, str) or not name:
            reject("BAD_PATH:" + role)
        else:
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                reject("MISSING_OR_ESCAPED_FILE:" + role)
            elif isinstance(digest, str) and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                reject("HASH_MISMATCH:" + role)
        if not a.get("source_id") or not a.get("source_url"):
            reject("MISSING_SOURCE:" + role)
        try:
            observed = utc(a["observed_utc"])
            captured = utc(a["captured_utc"])
            if observed > captured:
                reject("OBSERVED_AFTER_CAPTURE:" + role)
            if kickoff and role in PRE and captured >= kickoff:
                reject("POST_KICKOFF_INPUT:" + role)
            if kickoff and role == "final" and observed <= kickoff:
                reject("PRE_KICKOFF_FINAL:" + role)
        except (ValueError, KeyError, TypeError):
            reject("INVALID_ASSET_TIME:" + role)
    for role in REQUIRED_ROLES:
        if role not in by_role:
            reject("MISSING_ROLE:" + role)
    # Local checks are necessary but cannot establish original provider authenticity.
    return {"event_id": event, "status": "LOCAL_PREFLIGHT_PASS_UNAUTHENTICATED" if not reasons else "BLOCK",
            "reasons": reasons, "roles_present": len(by_role), "roles_required": len(REQUIRED_ROLES),
            "provider_authenticated": False, "eligible_for_official": False}

def audit(manifest, root):
    slates = manifest.get("slates")
    if not isinstance(slates, list) or not slates:
        raise ValueError("nonempty slates required")
    event_counts = Counter(s.get("event_id") for s in slates if isinstance(s, dict) and s.get("event_id"))
    rows = []
    for slate in slates:
        if not isinstance(slate, dict):
            rows.append({"event_id": None, "status": "BLOCK", "reasons": ["INVALID_SLATE"],
                         "roles_present": 0, "roles_required": 5,
                         "provider_authenticated": False, "eligible_for_official": False})
            continue
        row = check_slate(slate, root)
        if row["event_id"] and event_counts[row["event_id"]] > 1:
            row["status"] = "BLOCK"
            row["reasons"].append("DUPLICATE_EVENT")
        rows.append(row)
    local_pass = sum(r["status"] != "BLOCK" for r in rows)
    return {"slates_total": len(rows), "local_pit_complete": local_pass,
            "local_pit_coverage": round(local_pass / len(rows), 6),
            "authenticated_pit_complete": 0, "official_eligible": 0,
            "note": "Local hash/timestamp claims are not independently authenticated source evidence",
            "slates": rows}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("manifest", type=Path)
    a = p.parse_args()
    print(json.dumps(audit(json.loads(a.manifest.read_text()), a.manifest.parent.resolve()), indent=2))

if __name__ == "__main__":
    main()
