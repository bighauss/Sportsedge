"""Point-in-time DFS Showdown retrospective scorer. No contest EV or ROI claims.

Inputs: a manifest JSON with an immutable pregame model snapshot and independently
sourced, post-final player DK fantasy points. Does not re-fit to final results.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

UTC = dt.timezone.utc

def instant(value):
    d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timestamps require UTC offset")
    return d.astimezone(UTC)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def score(manifest, root):
    required = ("event_id", "kickoff_at", "snapshot_at", "model_sha256",
                "projections_file", "projections_sha256", "final_at",
                "final_source_url", "actual_points_file", "actual_points_sha256")
    if any(not manifest.get(k) for k in required):
        raise ValueError("missing mandatory PIT, model, or final provenance")
    if not (instant(manifest["snapshot_at"]) < instant(manifest["kickoff_at"]) < instant(manifest["final_at"])):
        raise ValueError("invalid point-in-time ordering")
    for field in ("model_sha256", "projections_sha256", "actual_points_sha256"):
        v = manifest[field]
        if len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
            raise ValueError("invalid SHA256: " + field)
    def checked(name, digest):
        p = (root / manifest[name]).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file():
            raise ValueError("file outside backtest bundle")
        if sha(p) != manifest[digest]:
            raise ValueError("file digest mismatch: " + name)
        return p
    proj_path = checked("projections_file", "projections_sha256")
    actual_path = checked("actual_points_file", "actual_points_sha256")
    with proj_path.open(newline="") as f:
        projected = list(csv.DictReader(f))
    with actual_path.open(newline="") as f:
        actual = list(csv.DictReader(f))
    if not projected or not actual:
        raise ValueError("empty projections or actuals")
    def keyed(rows, field):
        out = {}
        for r in rows:
            name = r.get("player", "").strip()
            if not name or name in out:
                raise ValueError("missing/duplicate player identity")
            val = float(r[field])
            if not math.isfinite(val):
                raise ValueError("nonfinite score")
            out[name] = val
        return out
    p = keyed(projected, "mean")
    a = keyed(actual, "dk_points")
    overlap = sorted(set(p) & set(a))
    if not overlap:
        raise ValueError("no matched players")
    err = [p[x] - a[x] for x in overlap]
    result = {"event_id": manifest["event_id"], "status": "RESEARCH_ONLY",
              "matched_players": len(overlap), "projected_players": len(p),
              "actual_players": len(a), "unmatched_projected": sorted(set(p)-set(a)),
              "mae": round(sum(abs(x) for x in err)/len(err), 4),
              "rmse": round(math.sqrt(sum(x*x for x in err)/len(err)), 4),
              "bias": round(sum(err)/len(err), 4),
              "contest_ev": "BLOCKED_NO_OWNERSHIP_AND_PAYOUT_DATA"}
    if manifest.get("lineups_file"):
        lp = (root / manifest["lineups_file"]).resolve()
        if not lp.is_relative_to(root.resolve()) or sha(lp) != manifest.get("lineups_sha256"):
            raise ValueError("lineups digest/path mismatch")
        data = json.loads(lp.read_text())
        grades = []
        for group in ("top_by_mean", "top_by_opt_rate"):
            for i, lineup in enumerate(data.get(group, [])):
                names = [lineup["cpt"]] + lineup["flex"]
                if len(names) != 6 or len(set(names)) != 6:
                    raise ValueError("invalid lineup")
                if all(x in a for x in names):
                    grades.append({"group": group, "rank": i+1, "cpt": names[0],
                                   "realized_dk_points": round(1.5*a[names[0]]+sum(a[x] for x in names[1:]), 3)})
        result["graded_lineups"] = grades
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    args = ap.parse_args()
    print(json.dumps(score(json.loads(args.manifest.read_text()), args.manifest.parent.resolve()), indent=2))

if __name__ == "__main__":
    main()
