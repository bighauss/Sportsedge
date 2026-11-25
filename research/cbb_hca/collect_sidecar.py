"""Prospective four-cell sidecar from the actual CBB RUN IT capture contract.

Read original private files only, verify local receipts, rebuild native context
and check parent forecast parity. Never mutates parent card or ledger.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from .evidence_io import atomic_publish
from .cbb_score_factorial import compare, freeze

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read_private(root, path):
    root=Path(root).resolve(strict=True)
    p=Path(path)
    if p.is_symlink() or p.resolve(strict=True)!=p.absolute() or root not in p.resolve().parents:
        raise ValueError("SOURCE_PATH_OUTSIDE_PRIVATE_ROOT_OR_SYMLINK")
    if p.stat().st_mode & 0o077 or not p.is_file():
        raise ValueError("PRIVATE_SOURCE_FILE_REQUIRED")
    return p.read_bytes()

def verify_blob(raw, receipt, *, source, cutoff):
    import cbbd_native_score_model as native
    if receipt.get("source")!=source or receipt.get("sha256","").removeprefix("sha256:")!=digest(raw) or type(receipt.get("bytes")) is not int or receipt["bytes"]!=len(raw):
        raise ValueError("SOURCE_RECEIPT_MISMATCH_"+source)
    observed=native.utc(receipt.get("observed_utc"),source)
    if observed>=cutoff:raise ValueError("SOURCE_NOT_STRICTLY_PRIOR_"+source)
    return observed

def unique_receipt(receipts, source):
    rows=[r for r in receipts if isinstance(r,dict) and r.get("source")==source]
    if len(rows)!=1:raise ValueError("SOURCE_RECEIPT_COUNT_"+source)
    return rows[0]

def source_context(card_path, capture_dir):
    import cbbd_paper_card as pc
    import cbbd_native_score_model as native
    import cbb_run_it as runner
    from cbbd_prospective_capture import BASE
    card_path=Path(card_path).absolute()
    capture_dir=Path(capture_dir).absolute()
    root=capture_dir.parent
    if root.resolve()!=root or root.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_EVIDENCE_ROOT_REQUIRED")
    def read(p):return read_private(root,p)
    def decode(raw):return pc._json_loads(raw)
    card_raw=read(card_path);card=decode(card_raw)
    if (card.get("schema")!=pc.CARD_SCHEMA or card.get("status")!=pc.CARD_STATUS
        or type(card.get("approved_stake_u")) is not int or card["approved_stake_u"]!=0
        or type(card.get("official_counted")) is not int or card["official_counted"]!=0
        or card.get("card_sha256")!=pc.card_digest(card)
        or card.get("model_code_sha256")!=native.MODEL_CODE_SHA256):
        raise ValueError("PARENT_CARD_INVALID")
    cutoff=native.utc(card["freeze_utc"],"freeze")
    season=card["season"]
    receipts_raw=read(card_path.parent/"receipts.json")
    receipts=decode(receipts_raw)
    ratings_manifest_raw=read(capture_dir/"ratings"/"receipt.json")
    rr=unique_receipt(decode(ratings_manifest_raw)["receipts"],"cbbd_ratings_adjusted")
    if rr.get("file")!="cbbd_ratings_adjusted.json":raise ValueError("RATINGS_FILE_CONTRACT")
    rating_raw=read(capture_dir/"ratings"/rr["file"])
    rating_obs=verify_blob(rating_raw,rr,source="cbbd_ratings_adjusted",cutoff=cutoff)
    card_r=card["ratings_receipt"]
    if any(card_r.get(k)!=rr.get(k) for k in ("source","season","observed_utc","sha256","row_count")):
        raise ValueError("PARENT_RATINGS_RECEIPT_MISMATCH")
    rr_public=unique_receipt(receipts,"cbbd_ratings_adjusted")
    verify_blob(rating_raw,rr_public,source="cbbd_ratings_adjusted",cutoff=cutoff)
    if rr_public["observed_utc"]!=rr["observed_utc"]:raise ValueError("RATINGS_OBSERVATION_CONFLICT")
    games_dir=capture_dir/"games"
    matches=[p for p in games_dir.iterdir() if re.fullmatch(r"cbbd_games_"+str(season)+r"_\d{8}T\d{12}Z\.raw\.json",p.name)]
    if len(matches)!=1:raise ValueError("TODAY_GAMES_CAPTURE_COUNT")
    today_path=matches[0]
    today_raw=read(today_path)
    today_manifest_raw=read(today_path.with_name(today_path.name.replace(".raw.json",".manifest.json")))
    man=decode(today_manifest_raw)
    if (man.get("format")!="CBBD_GAMES_CAPTURE_V1" or man.get("provider")!="collegebasketballdata" or man.get("documented_endpoint")!=BASE
        or man.get("season")!=season or man.get("source_sha256")!=digest(today_raw)
        or type(man.get("source_bytes")) is not int or man["source_bytes"]!=len(today_raw)):
        raise ValueError("TODAY_MANIFEST_MISMATCH")
    today_rec=unique_receipt(receipts,"cbbd_games")
    if today_rec.get("sha256")!=digest(today_raw) or today_rec.get("observed_utc")!=man["local_observed_utc"]:raise ValueError("TODAY_RECEIPT_MISMATCH")
    today_obs=native.utc(man["local_observed_utc"],"today")
    if today_obs>=cutoff:raise ValueError("TODAY_NOT_PRIOR")
    season_raw=read(games_dir/"cbbd_games_season.raw.json")
    boxes_raw=read(games_dir/"cbbd_games_teams.raw.json")
    season_obs=verify_blob(season_raw,unique_receipt(receipts,"cbbd_games_season"),source="cbbd_games_season",cutoff=cutoff)
    boxes_obs=verify_blob(boxes_raw,unique_receipt(receipts,"cbbd_games_teams"),source="cbbd_games_teams",cutoff=cutoff)
    today,history,boxes=map(decode,(today_raw,season_raw,boxes_raw))
    if not all(isinstance(a,list) for a in (today,history,boxes)) or man.get("returned_rows")!=len(today):
        raise ValueError("SOURCE_ROW_SCHEMA")
    def unique_games(rows):
        out={}
        for r in rows:
            if not isinstance(r,dict) or type(r.get("id")) is not int or r["id"]<=0 or r["id"] in out:
                raise ValueError("SOURCE_GAME_ID_INVALID_OR_DUPLICATE")
            out[r["id"]]=r
        return out
    t,h=unique_games(today),unique_games(history)
    for k in t.keys()&h.keys():
        if any(t[k].get(f)!=h[k].get(f) for f in ("season","homeTeamId","awayTeamId","startDate","neutralSite")):
            raise ValueError("OVERLAPPING_GAME_IDENTITY_CONFLICT")
    merged=list({**h,**t}.values())
    # Replay the parent's admission cutoff; never label evidence as captured
    # before the latest of its actual source observations.
    prior,_=runner.prior_games(merged,boxes,man["local_observed_utc"],season)
    observed=native.stamp(max(today_obs,season_obs,boxes_obs))
    for row in prior:row["final_captured_utc"]=observed
    settings=card["context"]["settings"]
    body=pc.eligible_bytes(rating_raw,rr,source=pc.RATINGS_SOURCE,season=season,
        decision=cutoff,kickoff=cutoff+timedelta(microseconds=1),max_age_seconds=36*3600)
    ctx=native.fit_context(body,prior,season=season,freeze_utc=card["freeze_utc"],settings=settings)
    for k in ("model_version","model_code_sha256","league_mean_ortg","league_pace","hca","prior_game_census","prior_games_used","settings"):
        if pc.canonical_bytes(ctx[k])!=pc.canonical_bytes(card["context"][k]):
            raise ValueError("PARENT_CONTEXT_REPLAY_MISMATCH_"+k)
    hashes={"ratings":digest(rating_raw),"prior_games":digest(pc.canonical_bytes(prior)),
        "season_games":digest(season_raw),"today_games":digest(today_raw),"team_boxes":digest(boxes_raw),
        "parent_card_bytes":digest(card_raw),"runner_receipts":digest(receipts_raw),
        "ratings_manifest":digest(ratings_manifest_raw),"today_manifest":digest(today_manifest_raw)}
    return card,ctx,hashes

def discover_and_record(card_path,capture_dir,out_dir,*,clock=None):
    import cbbd_native_score_model as native
    out_dir=Path(out_dir).absolute()
    root=Path(capture_dir).absolute()
    if out_dir.parent!=root or out_dir.name!="factorial_sidecar":raise ValueError("SIDECAR_OUTPUT_CONTRACT")
    out_dir.mkdir(mode=0o700,exist_ok=False)
    card,ctx,hashes=source_context(card_path,capture_dir)
    rows=[];counts=Counter(r.get("game_id") for r in card["rows"])
    for r in card["rows"]:
        gid=r.get("game_id")
        try:
            if counts[gid]!=1 or native.canonical_id(gid)!=gid:raise ValueError("PARENT_GAME_ID_INVALID")
            if r["status"]!="PROJECTED":raise ValueError("PARENT_GAME_NOT_PROJECTED")
            game=dict(game_id=gid,season=card["season"],home_team_id=r["home_team_id"],
                away_team_id=r["away_team_id"],tipoff_utc=r["tipoff_utc"],neutral=r["neutral"])
            expected=compare(ctx,game["home_team_id"],game["away_team_id"],neutral=game["neutral"])["additive_product"]
            for k in ("home_points","away_points","margin","total","possessions"):
                if not math.isclose(expected[k],r["projection"][k],rel_tol=1e-12,abs_tol=1e-10):
                    raise ValueError("PARENT_FORECAST_PARITY_FAILED")
            forecast=freeze(ctx,game,out_dir/(gid+".json"),parent_card_sha256=card["card_sha256"],source_receipts=hashes,clock=clock)
            rows.append(dict(game_id=gid,state="FROZEN_RESEARCH",file=gid+".json"))
        except (ValueError,KeyError,TypeError,OSError) as exc:
            rows.append(dict(game_id=gid,state="HOLD",reason=str(exc)))
    status=dict(state="COMPLETE_WITH_EXPLICIT_HOLDS",forecasts_written=sum(r["state"]=="FROZEN_RESEARCH" for r in rows),
        rows=rows,parent_card_sha256=card["card_sha256"],source_receipts=hashes,approved_stake_u=0,official_counted=0)
    atomic_publish(out_dir/"status.json",(json.dumps(status,sort_keys=True,allow_nan=False)+"\n").encode())
    return status

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--card",required=True);p.add_argument("--capture-dir",required=True);p.add_argument("--out",required=True)
    a=p.parse_args(argv)
    try:status=discover_and_record(a.card,a.capture_dir,a.out)
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps(dict(state="BLOCK_SOURCE_CONTRACT",reason=str(exc),forecasts_written=0,approved_stake_u=0),sort_keys=True))
        return 2
    print(json.dumps(status,sort_keys=True));return 0

if __name__=="__main__":raise SystemExit(main())
