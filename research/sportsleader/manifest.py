"""Select a unique supported asset from a retained upstream manifest."""
import hashlib
import json
from pathlib import Path
from research.sportsleader.intake import validate_entry

def select(raw, league, dataset, season):
    manifest = json.loads(raw)
    # Require an explicit list; reject unknown upstream layouts.
    entries = manifest if isinstance(manifest, list) else manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError("unrecognized manifest layout")
    matches = [e for e in entries if isinstance(e, dict)
               and e.get("league") == league and e.get("dataset") == dataset
               and str(e.get("season")) == str(season)]
    if len(matches) != 1:
        raise ValueError("asset missing or ambiguous")
    entry = matches[0]
    validate_entry(entry)
    return {"manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "entry": entry, "release_state": "PAPER_0U_NON_COUNTED"}

def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("league")
    p.add_argument("dataset")
    p.add_argument("season")
    a = p.parse_args()
    print(json.dumps(select(a.manifest.read_bytes(), a.league, a.dataset, a.season),
                     sort_keys=True))

if __name__ == "__main__":
    main()
