"""Research NBA regulation minutes: exact player IDs, as-of logs, 240 team minutes.

Separate from Claude's canonical NBA model. Does not simulate props, invent
availability, copy today's code onto historical predictions, or place bets.
"""
import argparse,csv,datetime as dt,hashlib,io,json,math
from collections import defaultdict
from pathlib import Path

class Blocked(ValueError):pass
def utc(s):
    try:x=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    except (ValueError,AttributeError) as e:raise Blocked("bad timestamp") from e
    if x.utcoffset()!=dt.timedelta(0):raise Blocked("not UTC")
    return x

def candidate(data,manifest):
    if hashlib.sha256(data).hexdigest()!=manifest.get("logs_sha256"):raise Blocked("logs hash mismatch")
    snap=utc(manifest["captured_at_utc"]);tip=utc(manifest["tipoff_utc"])
    if not snap<tip:raise Blocked("lookahead capture")
    statuses=manifest.get("players")
    if not isinstance(statuses,list) or not statuses:raise Blocked("availability unverified")
    active=defaultdict(list); seen=set()
    for p in statuses:
        if not isinstance(p,dict):raise Blocked("bad player entry")
        pid=p.get("player_id");team=p.get("team");status=p.get("status")
        if not pid or not team or status not in ("ACTIVE","OUT") or pid in seen:
            raise Blocked("ambiguous/unknown player status")
        seen.add(pid)
        if status=="ACTIVE":active[team].append(pid)
    if len(active)!=2 or any(len(x)<8 for x in active.values()):
        raise Blocked("at least eight confirmed ACTIVE players per team")
    try:reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    except UnicodeDecodeError as e:raise Blocked("non-UTF8") from e
    required={"game_id","game_utc","player_id","team","minutes","is_regulation"}
    if not required.issubset(reader.fieldnames or []):raise Blocked("missing history columns")
    logs=defaultdict(list); seen_log=set()
    for r in reader:
        t=utc(r["game_utc"])
        if t>=tip:raise Blocked("future/post-tipoff game in historical logs")
        if r["is_regulation"]!="1":raise Blocked("OT or unknown regulation game")
        try:m=float(r["minutes"])
        except (ValueError,TypeError) as e:raise Blocked("bad minutes") from e
        if not math.isfinite(m) or m<0 or m>48:raise Blocked("minutes outside regulation")
        key=(r["game_id"],r["player_id"])
        if key in seen_log:raise Blocked("duplicate player-game")
        seen_log.add(key)
        logs[(r["team"],r["player_id"])].append((t,m))
    cap=float(manifest.get("max_projected_minutes",48))
    if not math.isfinite(cap) or not 30<=cap<=48:raise Blocked("invalid minutes cap")
    out=[];team_report={}
    for team,ids in sorted(active.items()):
        raw=[]
        for pid in ids:
            history=sorted(logs[(team,pid)],reverse=True)[:10]
            if len(history)<3:raise Blocked(pid+": fewer than 3 prior games")
            ww=[0.5**(((tip-t).total_seconds()/86400)/30) for t,_ in history]
            est=sum(w*m for w,(_,m) in zip(ww,history))/sum(ww)
            raw.append([pid,est])
        if sum(v for _,v in raw)<=0:raise Blocked("all active player minutes zero")
        remaining=240.;free={pid for pid,_ in raw};allocated={pid:0. for pid,_ in raw}
        # Capped proportional water-fill: exact team total if feasible.
        weights=dict(raw)
        while free:
            s=sum(weights[p] for p in free)
            if s<=0:raise Blocked("remaining minutes without historical weight")
            to_cap={p for p in free if remaining*weights[p]/s>=cap}
            if not to_cap:
                for p in free:allocated[p]=remaining*weights[p]/s
                break
            for p in to_cap:
                allocated[p]=cap;remaining-=cap
            free-=to_cap
            if remaining < -1e-7:raise Blocked("infeasible cap")
            if not free and remaining>1e-6:raise Blocked("infeasible regulation total")
        for pid in sorted(allocated):
            out.append(dict(player_id=pid,team=team,minutes=round(allocated[pid],6),
                            baseline_history_minutes=round(weights[pid],6)))
        team_report[team]={"active":len(ids),"allocated_minutes":round(sum(allocated.values()),6)}
    return {"status":"PAPER_0U_RESEARCH_CANDIDATE","logs_sha256":manifest["logs_sha256"],
            "captured_at_utc":manifest["captured_at_utc"],"tipoff_utc":manifest["tipoff_utc"],
            "team_regulation_minutes":team_report,"players":out,
            "limitations":["availability status is a manifest claim, not verified in code",
                           "no foul/blowout scenarios, no overtime, no market validation",
                           "no production model or DFS changes"]}

def main():
    p=argparse.ArgumentParser();p.add_argument("manifest",type=Path);p.add_argument("--output",required=True,type=Path)
    a=p.parse_args();path=a.manifest.resolve();m=json.loads(path.read_text())
    rel=Path(m["logs_path"]);full=(path.parent/rel).resolve()
    if rel.is_absolute() or not full.is_relative_to(path.parent):raise Blocked("source escape")
    r=candidate(full.read_bytes(),m)
    with a.output.open("x",encoding="utf-8") as f:json.dump(r,f,indent=2);f.write("\n")
    print("NBA minutes candidate PAPER/0u; no canonical changes")
if __name__=="__main__":main()
