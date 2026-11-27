import argparse
import json
from research.sportsleader.chronological_residuals import select

def audit(rows):
    seasons=sorted({r["season"] for r in rows})
    if len(seasons)<2:
        raise ValueError("insufficient seasons")
    return [{"target_season":s,"prior_residual_count":len(select(rows,s))}
            for s in seasons[1:]]

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("path")
    with open(p.parse_args().path) as f:
        print(json.dumps(audit(json.load(f)),sort_keys=True))
