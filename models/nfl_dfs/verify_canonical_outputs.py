"""Verify committed DFS projections and lineups without changing either."""
import argparse,csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def verify(tag,root=ROOT):
    if not tag or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for c in tag): raise ValueError("bad tag")
    paths={"engine":root/"showdown_mc.py","config":root/"games"/(tag+".json"),"salary":root/"data"/("DKSalaries_"+tag+".csv"),"projections":root/"out"/(tag+"_projections.csv"),"lineups":root/"out"/(tag+"_lineups.json")}
    if any(not p.is_file() for p in paths.values()): raise ValueError("missing required canonical file")
    cfg=json.loads(paths["config"].read_text())
    if cfg.get("tag")!=tag or cfg.get("salary_file")!="data/DKSalaries_"+tag+".csv": raise ValueError("config mismatch")
    with paths["projections"].open(newline="") as f: rows=list(csv.DictReader(f))
    names={r["player"]:r for r in rows}
    if not rows or len(names)!=len(rows): raise ValueError("duplicate or empty projection")
    data=json.loads(paths["lineups"].read_text())
    if data.get("summary",{}).get("sims")!=20000: raise ValueError("unexpected sim count")
    if "BLOCKED" not in data["summary"].get("contest_ev","").upper(): raise ValueError("EV not blocked")
    counts={}
    for key in ("top_by_mean","top_by_opt_rate"):
        lineups=data.get(key,[])
        if not lineups: raise ValueError("missing lineups")
        counts[key]=len(lineups)
        for lineup in lineups:
            ps=[lineup["cpt"]]+lineup["flex"]
            if len(ps)!=6 or len(set(ps))!=6 or any(p not in names for p in ps): raise ValueError("invalid players")
            cost=int(names[ps[0]]["cpt_sal"])+sum(int(names[p]["flex_sal"]) for p in ps[1:])
            if cost!=int(lineup["salary"]) or cost>50000: raise ValueError("invalid salary")
    return {"tag":tag,"status":"PAPER_NO_VERIFIED_EV","simulations_claimed":20000,"players":len(rows),"lineups":counts,"sha256":{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()},"independently_reproduced":False}
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("tag");a=parser.parse_args()
    print(json.dumps(verify(a.tag),indent=2,sort_keys=True))
