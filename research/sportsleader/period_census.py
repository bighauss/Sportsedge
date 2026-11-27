"""Discover period data availability without assuming dataset coverage."""
import argparse,json
def census(manifest):
    out=[]
    for league in ("cbb","cfb","nfl"):
        entries=[r for r in manifest["files"] if r.get("league")==league]
        candidates=[]
        for r in entries:
            cols=r.get("columns",[])
            if not isinstance(cols,list):
                continue
            matches=[c for c in cols if isinstance(c,str) and any(k in c.lower() for k in ("period","quarter","half","linescore","line_score"))]
            if matches:
                candidates.append(dict(dataset=r["dataset"],season=r["season"],columns=matches))
        out.append(dict(league=league,candidates=candidates,status="SCHEMA_CANDIDATE_ONLY" if candidates else "NO_PERIOD_COLUMNS_ADVERTISED"))
    return out
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("manifest")
    with open(p.parse_args().manifest) as f:
        print(json.dumps(census(json.load(f)),sort_keys=True))
