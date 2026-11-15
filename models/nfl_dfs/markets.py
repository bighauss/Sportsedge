"""SportsEdge NFL all-markets pricer from the SAME Monte Carlo as DFS (showdown_mc.run).

One sim -> game lines (ML, spread, total, team totals) and player props
(pass/rush/rec yards, receptions, pass TDs, anytime TD). DFS and betting
therefore share identical numbers. Output: fair probabilities + fair American odds.
Book-price EV comparison: next step (needs captured DK prop prices).
RESEARCH / PAPER until graded against closing lines.

python models/nfl_dfs/markets.py games/PIT_CIN_2026-11-15.json 20000
"""
import json, os, statistics, sys
import showdown_mc as mc

def american(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)

def implied(odds):
    return -odds / (-odds + 100) if odds < 0 else 100 / (odds + 100)

PROPS = {"pass_yds": lambda s: s["py"], "pass_tds": lambda s: s["ptd"], "rush_yds": lambda s: s["ry"],
         "rec_yds": lambda s: s["rcy"], "receptions": lambda s: s["rec"],
         "anytime_td": lambda s: s["rtd"] + s["rctd"]}

def price(cfg, n, seed=7):
    raw = []
    mc.run(cfg, n, seed=seed, raw=raw)
    away, home = list(cfg["teams"])
    A = [r[away][1] for r in raw]; H = [r[home][1] for r in raw]
    out = {"tag": cfg["tag"], "sims": n, "label": "RESEARCH / PAPER", "game": {}, "props": []}
    g = out["game"]
    g["proj"] = {away: round(statistics.fmean(A), 2), home: round(statistics.fmean(H), 2),
                 "total": round(statistics.fmean(a + h for a, h in zip(A, H)), 2),
                 "home_margin": round(statistics.fmean(h - a for a, h in zip(A, H)), 2)}
    pw = sum(h > a for a, h in zip(A, H)) / n; pt = sum(h == a for a, h in zip(A, H)) / n
    g["moneyline"] = {home: american(pw / (1 - pt)), away: american((1 - pw - pt) / (1 - pt))}
    sp = cfg["market"]["spread_home"]; tot = cfg["market"]["total"]
    g[f"{home} -{sp}"] = round(sum(h - a > sp for a, h in zip(A, H)) / n, 4)
    g[f"over {tot}"] = round(sum(a + h > tot for a, h in zip(A, H)) / n, 4)
    for tm, xs in ((away, A), (home, H)):
        med = statistics.median(xs) + 0.5
        g[f"{tm} team total fair"] = med
        g[f"{tm} over {med}"] = round(sum(x > med for x in xs) / n, 4)
    for p, meta in cfg["players"].items():
        if meta["pos"] in ("K", "DST"): continue
        tm = meta["team"]
        for mk, f in PROPS.items():
            vals = [f(r[tm][0][p]) if p in r[tm][0] else 0 for r in raw]
            if mk == "pass_yds" and meta["pos"] != "QB": continue
            if mk == "pass_tds" and meta["pos"] != "QB": continue
            if mk in ("rec_yds", "receptions") and meta["pos"] == "QB": continue
            if statistics.fmean(vals) < (0.25 if mk == "anytime_td" else 1.5): continue
            if mk == "anytime_td":
                pr = sum(v >= 1 for v in vals) / n
                out["props"].append(dict(player=p, team=tm, market="anytime_td", p_yes=round(pr, 4), fair=american(pr)))
            else:
                line = round(statistics.median(vals)) + 0.5
                pr = sum(v > line for v in vals) / n
                out["props"].append(dict(player=p, team=tm, market=mk, mean=round(statistics.fmean(vals), 2),
                                         fair_line=line, p_over=round(pr, 4)))
    return out

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "games", "PIT_CIN_2026-11-15.json")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
    cfg = json.load(open(path))
    out = price(cfg, n)
    od = os.path.join(here, "out"); os.makedirs(od, exist_ok=True)
    json.dump(out, open(os.path.join(od, f"{cfg['tag']}_markets.json"), "w"), indent=1)
    print(json.dumps(out["game"], indent=1))
    for x in sorted(out["props"], key=lambda r: (r["market"], r["team"])):
        print(x)

if __name__ == "__main__":
    main()
