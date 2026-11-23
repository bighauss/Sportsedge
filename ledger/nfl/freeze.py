"""Pregame freeze: write an immutable run folder for one NFL run.

Usage (from repo root):
  python3 ledger/nfl/freeze.py --game CIN@WAS --board board.csv --projection proj.json \
      --picks challenger=picks_nfl.csv [--picks baseline=base.csv] \
      [--commit engine=<sha>] [--start-utc 2026-11-24T01:15:00Z] [--note "..."]
  python3 ledger/nfl/freeze.py --game X --board x --projection x --verify ledger/nfl/runs/<run_id>

Layout (mirrors the CIN@WAS research package):
  ledger/nfl/runs/<UTC ts>_<game>/
    inputs/board.csv
    projection/frozen.json
    <label>/picks_nfl.csv        (baseline/, challenger/, ...)
    manifest.json                (capture time, commits, sha256 of every file)
Refuses to overwrite an existing run folder. Files are chmod read-only.
Postgame results go to ledger/nfl/settlements/ (settle.py), never into this folder.
"""
import argparse, json, os, re, shutil, stat, subprocess, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RUNS_DIR, sha256_file  # noqa: E402


def _git_head():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip() or None
    except Exception:
        return None


def safe_game(game):
    return re.sub(r"[^A-Za-z0-9@_-]", "_", game)


def freeze(game, board, projection, picks, commits=None, start_utc=None, note=None,
           runs_dir=RUNS_DIR, now=None):
    """picks: dict label -> csv path. Returns run folder path."""
    now = now or datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{ts}_{safe_game(game)}"
    out = os.path.join(runs_dir, run_id)
    if os.path.exists(out):
        raise FileExistsError(f"run folder exists, refusing to overwrite: {out}")
    if start_utc and now.isoformat() >= start_utc.replace("Z", "+00:00"):
        print("WARNING: capture time is at/after start_utc - run is NOT pregame", file=sys.stderr)
    plan = {"inputs/board.csv": board, "projection/frozen.json": projection}
    for label, path in picks.items():
        plan[f"{label}/picks_nfl.csv"] = path
    for src in plan.values():
        if not os.path.isfile(src):
            raise FileNotFoundError(src)
    with open(projection) as f:
        json.load(f)  # must be valid JSON
    os.makedirs(out)
    files = {}
    for rel, src in plan.items():
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        files[rel] = sha256_file(dst)
    commits = dict(commits or {})
    commits.setdefault("repo_head", _git_head())
    manifest = {
        "run_id": run_id, "sport": "NFL", "game": game,
        "capture_utc": now.isoformat(timespec="seconds"),
        "start_utc": start_utc, "pregame": (not start_utc) or now.isoformat() < start_utc.replace("Z", "+00:00"),
        "commits": commits, "board_sha256": files["inputs/board.csv"],
        "files": files, "pick_sets": sorted(picks), "note": note,
    }
    mpath = os.path.join(out, "manifest.json")
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    for root, _, names in os.walk(out):
        for n in names:
            p = os.path.join(root, n)
            os.chmod(p, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return out


def verify(run_dir):
    """Re-hash every file; returns list of mismatched relative paths (empty = intact)."""
    with open(os.path.join(run_dir, "manifest.json")) as f:
        m = json.load(f)
    return [rel for rel, h in m["files"].items()
            if not os.path.exists(os.path.join(run_dir, rel)) or sha256_file(os.path.join(run_dir, rel)) != h]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", required=True)
    ap.add_argument("--board", required=True)
    ap.add_argument("--projection", required=True)
    ap.add_argument("--picks", action="append", default=[], help="label=path (repeatable)")
    ap.add_argument("--commit", action="append", default=[], help="name=sha (repeatable)")
    ap.add_argument("--start-utc")
    ap.add_argument("--note")
    ap.add_argument("--runs-dir", default=RUNS_DIR)
    ap.add_argument("--verify", help="verify an existing run folder instead")
    a = ap.parse_args(argv)
    if a.verify:
        bad = verify(a.verify)
        print("OK" if not bad else "MISMATCH: " + ", ".join(bad))
        return 1 if bad else 0
    picks = dict(p.split("=", 1) if "=" in p else ("challenger", p) for p in a.picks)
    commits = dict(c.split("=", 1) for c in a.commit)
    print(freeze(a.game, a.board, a.projection, picks, commits, a.start_utc, a.note, a.runs_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
