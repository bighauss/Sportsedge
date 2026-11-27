"""Research-only manifest-to-asset CLI. Retain the original manifest."""
import argparse
import json
from pathlib import Path
from research.sportsleader.manifest import select
from research.sportsleader.intake import ingest

def run(manifest, league, dataset, season, destination):
    receipt = select(Path(manifest).read_bytes(), league, dataset, season)
    asset = ingest(receipt["entry"], destination)
    return dict(receipt, asset=str(asset))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "league", "dataset", "season", "destination"):
        p.add_argument(name)
    a = p.parse_args()
    print(json.dumps(run(a.manifest, a.league, a.dataset, a.season, a.destination),
                     sort_keys=True))

if __name__ == "__main__":
    main()
