"""Fetch public sportsdataverse ESPN men's college basketball files (PAPER/0u research).

Source: GitHub releases of sportsdataverse/sportsdataverse-data (the hoopR/sportsdataverse
public mirror of ESPN data). Every downloaded file gets a sha256 and byte count in
``manifest.json`` so a later rebuild can prove it read identical bytes.

Usage:
    python research/cbb_halves/fetch_sdv.py --out /path/to/cache --seasons 2019-2026

Network access happens only here. Nothing in models/cbb/halves/ touches the network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
KINDS = {
    "pbp": "espn_mens_college_basketball_pbp/play_by_play_{y}.parquet",
    "schedule": "espn_mens_college_basketball_schedules/mbb_schedule_{y}.parquet",
    "team_box": "espn_mens_college_basketball_team_boxscores/team_box_{y}.parquet",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_seasons(text: str) -> list[int]:
    if "-" in text:
        a, b = text.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in text.split(",")]


def fetch(url: str, dest: Path, retries: int = 3) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            tmp.replace(dest)
            return
        except Exception:  # pragma: no cover - network
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seasons", default="2019-2026")
    ap.add_argument("--kinds", default="pbp,schedule,team_box")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    man_path = out / "manifest.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else {"files": {}}
    for y in parse_seasons(a.seasons):
        for kind in a.kinds.split(","):
            rel = KINDS[kind].format(y=y)
            url = f"{BASE}/{rel}"
            dest = out / Path(rel).name
            if a.force or not dest.exists():
                print("fetch", url, file=sys.stderr)
                fetch(url, dest)
            manifest["files"][dest.name] = {
                "url": url, "season": y, "kind": kind,
                "bytes": dest.stat().st_size, "sha256": sha256_file(dest),
                "fetched_utc": manifest["files"].get(dest.name, {}).get("fetched_utc")
                or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
    man_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    print(json.dumps({k: (v["bytes"], v["sha256"][:12]) for k, v in manifest["files"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
