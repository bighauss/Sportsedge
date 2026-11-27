"""Research-only SportsLeader asset intake; never supplies sportsbook quotes."""
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

ROOT = "https://github.com/WalrusQuant/sportsleader-data/releases/download/"
SPORTS = {"cbb", "cfb", "nfl"}
DATASETS = {"games", "team_box_scores", "team_game_stats", "player_game_logs",
            "passing_game_logs", "rushing_game_logs", "receiving_game_logs"}

def validate_entry(entry):
    league, dataset, season = (entry[k] for k in ("league", "dataset", "season"))
    if league not in SPORTS or dataset not in DATASETS:
        raise ValueError("unsupported research scope")
    if not re.fullmatch(r"[0-9]{4}", str(season)):
        raise ValueError("invalid season")
    expected = f"{ROOT}{league}_{dataset}/{season}.parquet"
    if entry["url"] != expected:
        raise ValueError("unexpected asset URL")
    if not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]):
        raise ValueError("invalid SHA256")
    for key in ("bytes", "rows"):
        if type(entry[key]) is not int or entry[key] <= 0:
            raise ValueError(f"invalid {key}")
    return expected

def ingest(entry, destination, opener=urlopen):
    """Verify bytes and parquet row count before publishing a local immutable asset."""
    url = validate_entry(entry)
    import pyarrow.parquet as pq
    import tempfile
    import os
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    target = root / (entry["sha256"] + ".parquet")
    digest = hashlib.sha256()
    count = 0
    fd, temp = tempfile.mkstemp(dir=root)
    try:
        with os.fdopen(fd, "wb") as out, opener(url, timeout=60) as response:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > entry["bytes"]:
                    raise ValueError("asset exceeds manifest size")
                digest.update(chunk)
                out.write(chunk)
        if count != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
            raise ValueError("asset integrity mismatch")
        if pq.ParquetFile(temp).metadata.num_rows != entry["rows"]:
            raise ValueError("row count mismatch")
        try:
            os.link(temp, target)
        except FileExistsError:
            with target.open("rb") as existing:
                if hashlib.file_digest(existing, "sha256").hexdigest() != entry["sha256"]:
                    raise ValueError("existing asset corrupted")
        return target
    finally:
        Path(temp).unlink(missing_ok=True)

def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entry", type=Path, help="One manifest entry JSON, retained as evidence")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(ingest(json.loads(args.entry.read_text()), args.destination))

if __name__ == "__main__":
    main()
