"""Retrospective research only; not PIT-certified or D-I filtered."""
import argparse
import json
from collections import defaultdict
from statistics import mean
import pyarrow.parquet as pq

def evaluate(paths):
    seasons = defaultdict(list)
    seen = set()
    for path in paths:
        for r in pq.read_table(path).to_pylist():
            if r["completed"] is not True or type(r["neutral_site"]) is not bool:
                continue
            if any(type(r[k]) is not int or r[k] < 0 for k in ("home_score","away_score")):
                continue
            if r["game_id"] is None or r["game_id"] in seen:
                raise ValueError("missing or duplicate game ID")
            seen.add(r["game_id"])
            seasons[r["season"]].append(r)
    out = []
    for season in sorted(seasons):
        train = [r for s in seasons if s < season for r in seasons[s] if not r["neutral_site"]]
        if not train:
            continue
        hfa = mean(r["home_score"]-r["away_score"] for r in train)
        for neutral in (False, True):
            test = [r["home_score"]-r["away_score"] for r in seasons[season] if r["neutral_site"] is neutral]
            if test:
                prediction = 0 if neutral else hfa
                out.append(dict(season=season, neutral=neutral, n=len(test),
                    train_n=len(train), prediction=prediction,
                    actual_mean=mean(test), mae=mean(abs(y-prediction) for y in test),
                    zero_mae=mean(abs(y) for y in test)))
    return dict(results=out, release_state="PAPER_0U_NON_COUNTED",
                limitations=["unadjusted team strength", "retrospective", "membership unverified"])

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("assets", nargs="+")
    print(json.dumps(evaluate(p.parse_args().assets), sort_keys=True))
