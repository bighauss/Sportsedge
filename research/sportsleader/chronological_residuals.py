"""Research residual admission. Metadata does not authenticate upstream provenance."""
import math

def select(records, target_season):
    if type(target_season) is not int:
        raise ValueError("invalid target season")
    seen=set()
    pairs=[]
    for r in records:
        season,train_end=r["season"],r["train_end_season"]
        if type(season) is not int or type(train_end) is not int or train_end>=season:
            raise ValueError("not out of sample")
        if season>=target_season:
            continue
        game=r["game_id"]
        if not isinstance(game,str) or not game or game in seen:
            raise ValueError("invalid or duplicate game")
        seen.add(game)
        pair=(r["home_residual"],r["away_residual"])
        if not all(math.isfinite(x) for x in pair):
            raise ValueError("invalid residual")
        pairs.append(pair)
    if len(pairs)<100:
        raise ValueError("insufficient prior residuals")
    return pairs
