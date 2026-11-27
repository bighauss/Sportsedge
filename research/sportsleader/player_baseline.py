"""Generic player history baseline; requires normalized, verified game logs."""
import math
from collections import defaultdict
from datetime import date

def evaluate(rows, min_games=5, window=20):
    if not 1<=min_games<=window:
        raise ValueError("invalid history window")
    days=defaultdict(list)
    seen=set()
    for r in rows:
        day=date.fromisoformat(r["date"])
        player,game,stat=r["player_id"],r["game_id"],r["stat"]
        key=(player,game,stat)
        if not all(isinstance(x,str) and x for x in key) or key in seen:
            raise ValueError("invalid or duplicate identity")
        seen.add(key)
        value=r["value"]
        if not math.isfinite(value) or (value<0 and stat not in ('yards','passing_yards','rushing_yards','receiving_yards')):
            raise ValueError("invalid stat")
        days[day].append((player,stat,value,game))
    history=defaultdict(list)
    out=[]
    for day in sorted(days):
        for player,stat,value,game in days[day]:
            prior=history[player,stat][-window:]
            if len(prior)>=min_games:
                mean=sum(prior)/len(prior)
                out.append(dict(date=day.isoformat(),player_id=player,game_id=game,stat=stat,
                    prediction=mean,actual=value,history_n=len(prior)))
        for player,stat,value,game in days[day]:
            history[player,stat].append(value)
    return dict(predictions=out,release_state="PAPER_0U_NON_COUNTED",
        limitations=["appearance conditional","no opportunity or opponent adjustment","normalized input required"])
