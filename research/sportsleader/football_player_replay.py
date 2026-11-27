import argparse,glob,json,math
import pyarrow.parquet as pq
from research.sportsleader.player_baseline import evaluate
from research.sportsleader.player_metrics import metrics

def run(paths,dataset):
    stats={"rushing_game_logs":["carries","yards","touchdowns"],"receiving_game_logs":["receptions","yards","touchdowns"]}[dataset]
    rows=[]
    skipped=0
    for path in paths:
        for r in pq.read_table(path,columns=["game_date","game_id","player_id"]+stats).to_pylist():
            for stat in stats:
                v=r[stat]
                if v is None or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 or r["player_id"] is None or r["game_id"] is None or r["game_date"] is None:
                    skipped+=1
                    continue
                rows.append(dict(date=str(r["game_date"])[:10],game_id=str(r["game_id"]),player_id=str(r["player_id"]),stat=stat,value=v))
    result=evaluate(rows)
    return dict(metrics=metrics(result["predictions"]),input_rows=len(rows),skipped=skipped,limitations=result["limitations"],release_state=result["release_state"])
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("dataset")
    p.add_argument("directory")
    a=p.parse_args()
    print(json.dumps(run(sorted(glob.glob(a.directory+"/*.parquet")),a.dataset)))
