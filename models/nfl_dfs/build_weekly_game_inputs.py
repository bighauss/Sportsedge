"""Build research-only Showdown JSON from frozen nflverse player-week CSV(.gz).

Unlike the richer PBP builder, this adapter consumes the actual public
stats_player_week_2026 release shape already captured by SportsEdge. It derives
pre-target-week passing/rushing/receiving opportunity means, strictly by GSIS
player ID. NGS receiving is optional coverage QA only. No DK AvgPointsPerGame,
no bookmaker/FD projections, no invented injuries, no contest ROI.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
from build_game_inputs import Blocked, utc, verified, records

CORE=("season","week","season_type","player_id","attempts","completions",
      "passing_tds","interceptions","carries","rushing_yards","rushing_tds",
      "targets","receptions","receiving_yards","receiving_tds")
NGS=("season","week","season_type","player_gsis_id","team_abbr","targets",
     "receptions","yards","rec_touchdowns")
ALIASES={"LA":"LAR"}


def load_snapshot_csv(path,columns):
    raw=path.read_bytes()
    if len(raw)>10_000_000: raise Blocked("Weekly release source too large")
    if path.name.endswith(".gz"):
        try: raw=gzip.decompress(raw)
        except (OSError,EOFError) as ex: raise Blocked("Corrupt weekly gzip") from ex
    if len(raw)>80_000_000: raise Blocked("Decompressed release too large")
    try: reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    except UnicodeDecodeError as ex: raise Blocked("Weekly release not UTF8") from ex
    if not set(columns).issubset(reader.fieldnames or ()):
        raise Blocked("Missing weekly columns: "+",".join(sorted(set(columns)-set(reader.fieldnames or ()))))
    return list(reader)


def numeric(row,col,*,positive=False):
    raw=row.get(col)
    try:
        n=float(raw)
    except (TypeError,ValueError) as ex:
        raise Blocked(f"Missing/invalid weekly numeric {col}") from ex
    if not math.isfinite(n) or abs(n)>100000 or (positive and n<0):
        raise Blocked(f"Unreasonable weekly numeric {col}")
    return n


def build(manifest_path,lookback=5,min_games=3):
    if not 1<=min_games<=lookback: raise Blocked("Invalid lookback")
    manifest_path=Path(manifest_path).resolve()
    root=manifest_path.parent
    meta=json.loads(manifest_path.read_text(encoding="utf-8"))
    kickoff=utc(meta["kickoff_utc"])
    if not isinstance(meta.get("game_date_local"),str):
        raise Blocked("game_date_local required (UTC rollover)")
    try:
        from datetime import date
        game_day=date.fromisoformat(meta["game_date_local"])
    except (ValueError,TypeError) as ex: raise Blocked("Invalid local game date") from ex
    if not 0<=(kickoff.date()-game_day).days<=1:
        raise Blocked("Kickoff/game date mismatch")
    season=meta.get("target_season")
    week=meta.get("target_week")
    if type(season)!=int or type(week)!=int or not 2000<=season<=2100 or not 1<=week<=22:
        raise Blocked("target_season and target_week required")
    keys=("template","roster","weekly")
    paths={k:verified(root,meta,k,kickoff) for k in keys}
    cfg=json.loads(paths["template"].read_text(encoding="utf-8"))
    teams=list(cfg["teams"])
    if len(teams)!=2 or len(set(teams))!=2: raise Blocked("Showdown exactly two teams")
    roster=records(paths["roster"],("player_name","team","gsis_id","position"))
    identities={}
    nameset=set()
    for r in roster:
        if r["team"] not in teams: continue
        pid=r["gsis_id"].strip()
        label=(r["player_name"],r["team"])
        if not pid or (pid in identities and identities[pid]!=label):
            raise Blocked("GSIS identity collision")
        if label in nameset: raise Blocked("Ambiguous duplicate roster identity")
        identities[pid]=label
        nameset.add(label)
    for name,info in cfg["players"].items():
        if info["pos"] not in ("DST","K") and (name,info["team"]) not in nameset:
            raise Blocked("Missing exact GSIS identity for "+name)
    raw=load_snapshot_csv(paths["weekly"],CORE)
    if not raw: raise Blocked("Empty weekly source")
    per_team=defaultdict(lambda:defaultdict(dict))
    excluded_current=0
    excluded_unbound=0
    for row in raw:
        y=int(numeric(row,"season"))
        if y!=season or row["season_type"] not in ("REG","REGULAR"):
            continue
        w=int(numeric(row,"week"))
        if w>=week:
            excluded_current+=1
            continue
        if w<1: raise Blocked("Invalid historical week")
        a=(row.get("team") or "").strip().upper()
        b=(row.get("recent_team") or "").strip().upper()
        if a and b and a!=b: raise Blocked("Conflicting team columns")
        tm=ALIASES.get(a or b,a or b)
        if tm not in teams: continue
        pid=row["player_id"].strip()
        if not pid:
            excluded_unbound+=1
            if any(numeric(row,k,positive=True)>0 for k in ("rushing_tds","receiving_tds")):
                raise Blocked("Unattributed offensive touchdown")
            continue
        if pid in per_team[tm][w]: raise Blocked("Duplicate weekly player ID")
        if pid in identities and identities[pid][1]!=tm:
            raise Blocked("Player identity team mismatch")
        stats={k:numeric(row,k,positive=k not in ("rushing_yards","receiving_yards"))
               for k in CORE if k not in ("season","week","season_type","player_id")}
        if stats["completions"]>stats["attempts"] or stats["receptions"]>stats["targets"]:
            raise Blocked("Completions/receptions exceed opportunities")
        per_team[tm][w][pid]=stats
    audits={}
    for tm in teams:
        windows=sorted(per_team[tm],reverse=True)[:lookback]
        if len(windows)<min_games: raise Blocked(tm+": missing prior game weeks")
        chosen=[per_team[tm][w] for w in windows]
        totals=Counter()
        players=defaultdict(Counter)
        for week_rows in chosen:
            for pid,st in week_rows.items():
                for k,v in st.items(): totals[k]+=v
                name=identities.get(pid,("_other",tm))[0]
                for k,v in st.items(): players[name][k]+=v
        n=len(chosen)
        att,car=totals["attempts"],totals["carries"]
        tg,rc=totals["targets"],totals["receptions"]
        if att<n*12 or car<n*8 or tg<1 or rc<1:
            raise Blocked(tm+": insufficient team usage")
        qb=cfg["teams"][tm]["qb"]
        if players[qb]["attempts"]/att<.75:
            raise Blocked(tm+": template QB low/ambiguous usage")
        mean_catch=rc/tg
        mean_rec_y=totals["receiving_yards"]/rc
        mean_rush_y=totals["rushing_yards"]/car
        if not .2<=mean_catch<=.95 or mean_rec_y<=0 or mean_rush_y<=0:
            raise Blocked(tm+": implausible team rates")
        team=cfg["teams"][tm]
        derived={
          "pass_att":round(att/n,4),"rush_att":round(car/n,4),
          "pass_td":round(totals["passing_tds"]/n,4),
          "rush_td":round(totals["rushing_tds"]/n,4),
          "int_rate":round(totals["interceptions"]/att,6),
          "targets":{},"rush":{},
          "recv":{"_default":[round(mean_catch,5),round(mean_rec_y,5)]},
          "ypc":{},"pass_td_w":{},"rush_td_w":{}
        }
        # Fumbles remain MANUAL: weekly total does not establish loss
        # provenance without confirming fumble columns and double-counting.
        for name,st in players.items():
            if st["targets"]>0:
                tar=st["targets"]
                derived["targets"][name]=round(tar,4)
                derived["recv"][name]=[
                    round((st["receptions"]+3*mean_catch)/(tar+3),5),
                    round((st["receiving_yards"]+3*mean_rec_y)/(st["receptions"]+3),5)]
                derived["pass_td_w"][name]=round(3*st["receiving_tds"]+.03*tar,5)
            if st["carries"]>0:
                rush=st["carries"]
                derived["rush"][name]=round(rush,4)
                derived["ypc"][name]=round((st["rushing_yards"]+4*mean_rush_y)/(rush+4),5)
                derived["rush_td_w"][name]=round(3*st["rushing_tds"]+.03*rush,5)
        if not derived["pass_td_w"] or not derived["rush_td_w"]:
            raise Blocked(tm+": missing TD allocation basis")
        team.update(derived)
        audits[tm]={"prior_weeks":windows,"unbound_targets":players["_other"]["targets"],
                    "unbound_carries":players["_other"]["carries"],
                    "observed_pass_att":int(att),"observed_carries":int(car)}
        if players["_other"]["targets"]>tg*.15 or players["_other"]["carries"]>car*.20:
            raise Blocked(tm+": unbound opportunity share exceeds limit")
    ngs_meta=None
    if "ngs_receiving" in meta:
        src=verified(root,meta,"ngs_receiving",kickoff)
        rows=load_snapshot_csv(src,NGS)
        accepted=0
        exclude_aggregate=0
        for row in rows:
            if row["season"]!=str(season) or row["season_type"]!="REG": continue
            w=int(numeric(row,"week"))
            if w==0: exclude_aggregate+=1;continue
            if w>=week:continue
            if row["player_gsis_id"] in identities and row["team_abbr"] in teams:
                if numeric(row,"receptions",positive=True)>numeric(row,"targets",positive=True):
                    raise Blocked("NGS catches exceed targets")
                accepted+=1
        ngs_meta={"matched_prior_player_weeks":accepted,
                  "excluded_week_zero_aggregates":exclude_aggregate,
                  "role":"coverage QA only, not an NGS point multiplier"}
    cfg["_auto_build"]={
      "status":"PAPER_RESEARCH_ONLY",
      "mode":"NFLVERSE_WEEKLY_PLAYER_STATS","game_date_local":meta["game_date_local"],
      "target_season":season,"target_week":week,"kickoff_utc":meta["kickoff_utc"],
      "excluded_current_or_future_rows":excluded_current,
      "excluded_unbound_non_scoring_rows":excluded_unbound,
      "team_coverage":audits,"ngs":ngs_meta,
      "snapshots":{k:{"sha256":meta[k]["sha256"],"captured_at_utc":meta[k]["captured_at_utc"]}
                   for k in (*keys,"ngs_receiving") if k in meta},
      "preserved_unverified":["market","weather","players.p_active","fum_lost",
                              "fg accuracy","DST parameters"],
      "assumptions":"Last 5 completed weeks; 3-target/4-carry empirical shrinkage and observed TD-weight smoothing; UNCALIBRATED",
      "provider_fantasy_points_used":False}
    return cfg


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest",type=Path)
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--lookback",type=int,default=5)
    p.add_argument("--min-games",type=int,default=3)
    a=p.parse_args()
    cfg=build(a.manifest,a.lookback,a.min_games)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(cfg,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PAPER","output":str(a.out),"coverage":cfg["_auto_build"]},indent=2))


if __name__=="__main__":
    main()
