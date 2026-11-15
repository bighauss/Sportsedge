"""Replay frozen historical NFL Showdown slates (research-only, NO ROI claims).

Reads a manifest listing pre-kickoff model/config/DK salary snapshots and
postgame raw box-score results. Model engine unchanged: showdown_mc.run/optimize.
Every actual DK score is reconstructed from raw stats, never AvgPointsPerGame.

Strict AS-OF requires source hashes and capture times, including model bytes.
--allow-reconstruction runs changed model versions but labels results
RECONSTRUCTED, NOT A HISTORICAL FORWARD TEST.
"""
import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics

import showdown_mc as mc
from build_game_inputs import Blocked, utc


OFFENSE = ("pass_yd","pass_td","pass_int","rush_yd","rush_td",
           "receptions","rec_yd","rec_td","fumbles_lost",
           "two_point_conversions","return_tds","offensive_fumble_td")
KICKER = ("fg_0_39","fg_40_49","fg_50_plus","xp_made")
DEFENSE = ("points_allowed","sacks","dst_int","fumble_recoveries","dst_td","safeties",
           "blocked_kicks","two_point_returns")
RESULT_HEADER = ("player_name","team","pos") + OFFENSE + KICKER + DEFENSE


def file_record(root, spec, kickoff, before=True):
    if not all(k in spec for k in ("path","sha256","captured_at_utc")):
        raise Blocked("Every archived file needs path/SHA256/capture UTC")
    path=(root / spec["path"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise Blocked("Archive path traversal")
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=spec["sha256"]:
        raise Blocked(f"Archive missing/hash mismatch: {spec['path']}")
    when=utc(spec["captured_at_utc"])
    if (when >= kickoff) if before else (when <= kickoff):
        raise Blocked(f"Incorrect capture timing: {spec['path']}")
    return path


def observed_score(row):
    def get(k):
        try:
            v=float(row[k])
            if not (v==v and abs(v)<100000): raise ValueError("non-finite/outlier")
            return v
        except (KeyError,ValueError,TypeError) as ex:
            raise Blocked(f"Invalid or missing raw box-score stat {k}") from ex
    pos=row["pos"]
    if pos=="K":
        return 3*get("fg_0_39")+4*get("fg_40_49")+5*get("fg_50_plus")+get("xp_made")
    if pos=="DST":
        return (mc.dk_dst(get("points_allowed"),get("sacks"),get("dst_int"),
                          get("fumble_recoveries"),get("dst_td"),get("safeties"))
                + 2*get("blocked_kicks") + 2*get("two_point_returns"))
    if pos in ("QB","RB","WR","TE"):
        return (mc.dk_offense(py=get("pass_yd"),ptd=get("pass_td"),ints=get("pass_int"),
                              ry=get("rush_yd"),rtd=get("rush_td"),rec=get("receptions"),
                              rcy=get("rec_yd"),rctd=get("rec_td"),fum=get("fumbles_lost"))
                + 2*get("two_point_conversions") + 6*get("return_tds")
                + 6*get("offensive_fumble_td"))
    raise Blocked(f"Unsupported position {pos}")


def actual_results(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        r=csv.DictReader(f)
        if not set(RESULT_HEADER).issubset(r.fieldnames or ()):
            raise Blocked("Missing independent raw box-score fields")
        data=list(r)
    results={}
    for row in data:
        key=row["player_name"]
        if not key or key in results: raise Blocked("Duplicate/empty result player")
        results[key]={"team":row["team"],"pos":row["pos"],
                      "score":round(observed_score(row),4)}
    return results


def evaluate(entry, root, sims_count, seed, allow_reconstruction):
    kickoff=utc(entry["kickoff_utc"])
    cfg_path=file_record(root,entry["config"],kickoff,before=True)
    sal_path=file_record(root,entry["salaries"],kickoff,before=True)
    results_path=file_record(root,entry["results"],kickoff,before=False)
    code=Path(mc.__file__).resolve()
    codehash=hashlib.sha256(code.read_bytes()).hexdigest()
    model=entry.get("engine")
    same=(isinstance(model,dict) and model.get("sha256")==codehash
          and utc(model["captured_at_utc"])<kickoff)
    if not same and not allow_reconstruction:
        raise Blocked(f"{entry['tag']}: model version not proven pre-kickoff")
    cfg=json.loads(cfg_path.read_text(encoding="utf-8"))
    if cfg["tag"]!=entry["tag"]:
        raise Blocked("Tag mismatch")
    salary=mc.load_salaries(sal_path)
    truth=actual_results(results_path)
    for player,info in cfg["players"].items():
        if player not in salary: raise Blocked(f"DK salary missing {player}")
        if player not in truth: raise Blocked(f"Raw final score missing {player}")
        if (salary[player]["team"],salary[player]["pos"])!=(info["team"],info["pos"]):
            raise Blocked(f"DK identity mismatch: {player}")
        if (truth[player]["team"],truth[player]["pos"])!=(info["team"],info["pos"]):
            raise Blocked(f"Final score identity mismatch: {player}")
    pred,_=mc.run(cfg,sims_count,seed=seed)
    means={p:statistics.fmean(x) for p,x in pred.items()}
    pool=[p for p in means if means[p]>=cfg.get("pool_min_mean",1.5)]
    if len(pool)<6: raise Blocked("Insufficient player pool")
    stats,_,_,candidates=mc.optimize(pred,salary,pool)
    if not stats: raise Blocked("No feasible shortlisted lineups")
    def score(line):
        names=line["flex"]+[line["cpt"]]
        if len(set(names))!=6: raise Blocked("Duplicate roster slot")
        total=sum(salary[x]["CPT"] if x==line["cpt"] else salary[x]["FLEX"] for x in names)
        if total>50000 or len({salary[x]["team"] for x in names})!=2:
            raise Blocked("Illegal lineup in candidate list")
        return round(1.5*truth[line["cpt"]]["score"]+
                     sum(truth[x]["score"] for x in line["flex"]),3)
    cash=max(stats,key=lambda x:x["mean"])
    gpp=max(stats,key=lambda x:(x["opt_rate"],x["p99"]))
    hindsight=max(score(line) for line in stats)
    player_errors=[means[p]-truth[p]["score"] for p in cfg["players"]]
    return {"tag":entry["tag"],
            "status":"VERIFIED_AS_OF_REPLAY" if same else "RECONSTRUCTED_NOT_FORWARD_TEST",
            "n_sims":sims_count,"seed":seed,
            "filtered_candidates":candidates,"scored_shortlist":len(stats),
            "player_mae":round(statistics.fmean(abs(e) for e in player_errors),3),
            "player_rmse":round(statistics.fmean(e*e for e in player_errors)**.5,3),
            "cash_cpt":cash["cpt"],"cash_actual_points":score(cash),
            "gpp_cpt":gpp["cpt"],"gpp_actual_points":score(gpp),
            "shortlist_hindsight_points":hindsight,
            "cash_shortlist_regret":round(hindsight-score(cash),3),
            "gpp_shortlist_regret":round(hindsight-score(gpp),3),
            "ownership":"NOT_AVAILABLE","contest_ev":"BLOCKED_NO_FIELD_OR_PAYOUTS",
            "note":"Hindsight is BEST OF FILTERED SHORTLIST; not all DK-legal lineups."}


def replay(manifest_path, n_sims=500, seed=7, allow_reconstruction=False):
    if n_sims<2: raise Blocked("Need at least two simulations")
    root=Path(manifest_path).resolve().parent
    manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not manifest.get("slates"): raise Blocked("No archived slates")
    tags=[e["tag"] for e in manifest["slates"]]
    if len(set(tags))!=len(tags): raise Blocked("Duplicate slate tags")
    details=[evaluate(e,root,n_sims,seed,allow_reconstruction) for e in manifest["slates"]]
    return {"status":"PAPER / NO ROI","count":len(details),
            "all_verified_asof":all(x["status"]=="VERIFIED_AS_OF_REPLAY" for x in details),
            "mean_player_mae":round(statistics.fmean(x["player_mae"] for x in details),3),
            "slates":details}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("manifest",type=Path)
    p.add_argument("--sims",type=int,default=500)
    p.add_argument("--seed",type=int,default=7)
    p.add_argument("--allow-reconstruction",action="store_true")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    result=replay(a.manifest,a.sims,a.seed,a.allow_reconstruction)
    data=json.dumps(result,indent=2)+"\n"
    if a.out:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(data,encoding="utf-8")
    else: print(data)


if __name__=="__main__":
    main()
