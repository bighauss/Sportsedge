"""Research smoke: load sportsdataverse 2027 and run AdjustedFit (PAPER/0u)."""
from collections import Counter
from datetime import date
from fullgame.sdv_loader import load_season
from fullgame.ratings import AdjustedFit, usable

def main(root="/tmp/sdv_data", season=2027, min_games=5, cutoff="2026-11-25"):
    games = load_season(root, season)
    n = Counter(t for g in games for t in (g["home"], g["away"]))
    d1 = {t for t, c in n.items() if c >= min_games}
    games = load_season(root, season, d1_set=d1)
    usable_games = [g for g in games if usable(g)]
    fit = AdjustedFit(lam=4, half_life=40, hca_lam=400)
    fit.fit(usable_games, date.fromisoformat(cutoff))
    return {
        "games_loaded": len(games),
        "usable": len(usable_games),
        "teams": len(fit.o),
        "hca": round(fit.h, 2),
        "league_ortg": round(fit.mu, 1),
        "league_pace": round(fit.pi, 1),
    }

if __name__ == "__main__":
    print(main())
