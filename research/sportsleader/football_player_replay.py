import argparse,glob,json,math
import pyarrow.parquet as pq
from research.sportsleader.player_baseline import evaluate
from research.sportsleader.player_metrics import metrics
from research.sportsleader.player_probability import evaluate as probabilities

def run(paths,dataset):
    stats={"passing_game_logs":["completions","attempts","yards","touchdowns","interceptions"],"player_game_logs":["points","rebounds","assists","fg3_made","steals","blocks","turnovers"],"rushing_game_logs":["carries","yards","touchdowns"],"receiving_game_logs":["receptions","yards","touchdowns"]}[dataset]
    rows=[]
    skipped=0
    for path in paths:
        for r in pq.read_table(path,columns=["game_date","game_id","player_id"]+stats+(["did_not_play"] if dataset=="player_game_logs" else [])).to_pylist():
            if dataset=="player_game_logs" and r["did_not_play"] is not False:
                skipped+=len(stats)
                continue
            if dataset=="player_game_logs":
                vals=[r[x] for x in ("points","rebounds","assists")]
                r["pra"]=sum(vals) if all(isinstance(x,(int,float)) for x in vals) else None
            for stat in stats+(["pra"] if dataset=="player_game_logs" else []):
                v=r[stat]
                if v is None or not isinstance(v,(int,float)) or not math.isfinite(v) or (v<0 and stat!='yards') or r["player_id"] is None or r["game_id"] is None or r["game_date"] is None:
                    skipped+=1
                    continue
                rows.append(dict(date=str(r["game_date"])[:10],game_id=str(r["game_id"]),player_id=str(r["player_id"]),stat=stat,value=v))
    result=evaluate(rows)
    return dict(probabilities=probabilities(result["predictions"]),metrics=metrics(result["predictions"]),input_rows=len(rows),skipped=skipped,limitations=result["limitations"],release_state=result["release_state"])
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("dataset")
    p.add_argument("directory")
    a=p.parse_args()
    print(json.dumps(run(sorted(glob.glob(a.directory+"/*.parquet")),a.dataset)))
