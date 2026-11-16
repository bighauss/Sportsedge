"""RUN IT card EV (sizing, stars, disagreement guard) from the shared Monte Carlo.
Complements book_ev.py (ChatGPT, merged, tests): same sims, same DK screenshot prices.
Use games/<tag>_dk_screens.json (flat O/U + anytime-TD capture format).

  raw EV      = p_model * decimal - 1
  blended EV  = (0.30 p_model + 0.70 p_no_vig_market) * decimal - 1
Two-sided markets are de-vigged; one-sided markets (anytime TD) use the posted implied
probability (vig NOT removed), which makes blended EV conservative.
Guard: model/market probability ratio outside 0.67-1.5 or gap >0.12 means the hand-set inputs are suspect, not an edge; those plays are listed, not shown as bets.
Rules: drop overs above / unders below the projection; thin props max 3 stars;
Low confidence = -1 star and half size; quarter-Kelly on a 100u bankroll, min 0.25u,
max 1.5u; 3u per player/theme cap; NO per-game cap (Isaac, Nov 15).

python models/nfl_dfs/run_it_card.py [game.json] [dk_screens.json] [sims]
"""
import json, os, statistics, sys
import showdown_mc as mc

HERE = os.path.dirname(os.path.abspath(__file__))

def implied(o):
    return -o / (-o + 100) if o < 0 else 100 / (o + 100)

def dec(o): return 1 + (o / 100 if o > 0 else 100 / -o)

def stat_fn(market, p, team, rawrow, qb):
    s = rawrow[team][0].get(p, {})
    g = lambda k: s.get(k, 0)
    if market == "pass_yds": return g("py")
    if market == "pass_tds": return g("ptd")
    if market == "ints": return g("ints")
    if market == "rush_yds": return g("ry")
    if market == "rec_yds": return g("rcy")
    if market == "receptions": return g("rec")
    if market == "pass_rush_yds": return g("py") + g("ry")
    if market == "rush_rec_yds": return g("ry") + g("rcy")
    if market == "anytime_td": return g("rtd") + g("rctd")
    if market == "completions": return sum(v["rec"] for v in rawrow[team][0].values())
    raise KeyError(market)

def kelly_units(p, o):
    b = dec(o) - 1
    f = (b * p - (1 - p)) / b
    return max(0.0, f / 4 * 100)

def main():
    gpath = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "games", "PIT_CIN_2026-11-15.json")
    lpath = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "games", "PIT_CIN_2026-11-15_dk_screens.json")
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 20000
    cfg = json.load(open(gpath)); lines = json.load(open(lpath))
    raw = []; mc.run(cfg, n, seed=7, raw=raw)
    away, home = list(cfg["teams"])
    pts = {away: [r[away][1] for r in raw], home: [r[home][1] for r in raw]}
    plays = []; disagree = []

    def add(desc, kind, side, line, odds, p_model, p_nv, mean, thin=False, group="", game=False):
        if odds is None: return
        # projection filter
        if line is not None and mean is not None:
            if side == "Over" and line > mean + 1e-9: return
            if side == "Under" and line < mean - 1e-9: return
        ratio = p_model / max(p_nv, 1e-9)
        if ratio > 1.5 or ratio < 0.67 or abs(p_model - p_nv) > 0.12:
            disagree.append(dict(play=desc, price=odds, p_model=round(p_model, 3), p_market_nv=round(p_nv, 3)))
            return
        pb = 0.3 * p_model + 0.7 * p_nv
        d = dec(odds)
        raw_ev = p_model * d - 1; bl_ev = pb * d - 1
        if bl_ev <= 0: return
        gap = abs(p_model - p_nv)
        conf = "Low" if (thin or gap > 0.15) else ("High" if gap < 0.06 else "Medium")
        stars = 5 if bl_ev >= .08 else 4 if bl_ev >= .05 else 3 if bl_ev >= .03 else 2 if bl_ev >= .015 else 1
        if thin: stars = min(stars, 3)
        if conf == "Low": stars = max(1, stars - 1)
        u = kelly_units(pb, odds)
        if conf == "Low": u /= 2
        u = 0.0 if bl_ev <= 0 else min(1.5, max(0.25, round(u * 4) / 4))
        plays.append(dict(play=desc, kind=kind, price=odds, p_model=round(p_model, 4), p_market_nv=round(p_nv, 4),
                          raw_ev=round(raw_ev, 4), blended_ev=round(bl_ev, 4), stars=stars, conf=conf,
                          size_u=u, group=group, model_mean=None if mean is None else round(mean, 2), line=line))

    def devig(o, u):
        a, b = implied(o), implied(u); return a / (a + b)

    # ---- game lines
    A, H = pts[away], pts[home]
    mA, mH = statistics.fmean(A), statistics.fmean(H)
    g = lines["game"]
    pw_h = sum(h > a for a, h in zip(A, H)) / n; ties = sum(h == a for a, h in zip(A, H)) / n
    ph = pw_h / (1 - ties); pa = 1 - ph
    nv_h = devig(g["ml"][home], g["ml"][away])
    add(f"{home} ML", "Game", "ML", None, g["ml"][home], ph, nv_h, None, group="side")
    add(f"{away} ML", "Game", "ML", None, g["ml"][away], pa, 1 - nv_h, None, group="side")
    sp = g["spread_home"]  # home -sp
    pc = sum(h - a > sp for a, h in zip(A, H)) / n; pp = sum(h - a < sp for a, h in zip(A, H)) / n
    nvs = devig(g["spread_odds"][home], g["spread_odds"][away])
    add(f"{home} -{sp}", "Game", "Spread", None, g["spread_odds"][home], pc, nvs, None, group="side")
    add(f"{away} +{sp}", "Game", "Spread", None, g["spread_odds"][away], pp, 1 - nvs, None, group="side")
    tot = g["total"]
    po = sum(a + h > tot for a, h in zip(A, H)) / n; pu = sum(a + h < tot for a, h in zip(A, H)) / n
    nvt = devig(g["total_odds"][0], g["total_odds"][1])
    mt = mA + mH
    add(f"Over {tot}", "Game", "Over", tot, g["total_odds"][0], po, nvt, mt, group="total")
    add(f"Under {tot}", "Game", "Under", tot, g["total_odds"][1], pu, 1 - nvt, mt, group="total")
    for tm, xs in ((away, A), (home, H)):
        L = g["team_total"][tm]["line"]; ov, un = g["team_total"][tm]["odds"]
        po = sum(x > L for x in xs) / n; pu = sum(x < L for x in xs) / n
        nv = devig(ov, un); m = statistics.fmean(xs)
        add(f"{tm} Team Total Over {L}", "Game", "Over", L, ov, po, nv, m, group="total")
        add(f"{tm} Team Total Under {L}", "Game", "Under", L, un, pu, 1 - nv, m, group="total")
    for tm in (away, home):
        ov, un = g["team_tds"][tm]["odds"]; L = g["team_tds"][tm]["line"]
        tds = [sum(v["rtd"] + v["rctd"] for v in r[tm][0].values()) for r in raw]
        po = sum(x > L for x in tds) / n; pu = sum(x < L for x in tds) / n
        nv = devig(ov, un); m = statistics.fmean(tds)
        add(f"{tm} Team TDs Over {L}", "Game", "Over", L, ov, po, nv, m, group="total")
        add(f"{tm} Team TDs Under {L}", "Game", "Under", L, un, pu, 1 - nv, m, group="total")

    # ---- player O/U
    qb_of = {t: cfg["teams"][t]["qb"] for t in cfg["teams"]}
    cal = []
    for row in lines["props_ou"]:
        p, mk, L, ov, un = row
        tm = cfg["players"][p]["team"]
        vals = [stat_fn(mk, p, tm, r, qb_of[tm]) for r in raw]
        m = statistics.fmean(vals)
        po = sum(v > L for v in vals) / n; pu = sum(v < L for v in vals) / n
        nv = devig(ov, un)
        thin = mk in ("receptions", "rec_yds", "rush_rec_yds") and statistics.fmean([stat_fn("receptions", p, tm, r, None) for r in raw[:4000]]) < 2.0
        thin = thin or (mk in ("rush_yds",) and L < 20 and cfg["players"][p]["pos"] != "QB")
        cal.append(dict(player=p, market=mk, line=L, model_mean=round(m, 2)))
        grp = f"{p}"
        add(f"{p} Over {L} {mk}", "Prop", "Over", L, ov, po, nv, m, thin, grp)
        add(f"{p} Under {L} {mk}", "Prop", "Under", L, un, pu, 1 - nv, m, thin, grp)
    # ---- anytime TD (one-sided)
    for p, o in lines["anytime_td"].items():
        if p not in cfg["players"]: continue
        tm = cfg["players"][p]["team"]
        pr = sum(stat_fn("anytime_td", p, tm, r, None) >= 1 for r in raw) / n
        add(f"{p} Anytime TD", "Prop", "Yes", None, o, pr, implied(o), None, thin=cfg["players"][p]["pos"] in ("TE",) and implied(o) < .1, group=p)
    plays.sort(key=lambda x: -x["blended_ev"])
    # sizing: 3u per player/theme only (Isaac removed the 2u/game cap)
    used, per = 0.0, {}
    for x in plays:
        room = 3.0 - per.get(x["group"], 0.0)
        s = min(x["size_u"], max(0.0, room))
        if s < 0.25: s = 0.0
        x["size_u"] = s; used += s; per[x["group"]] = per.get(x["group"], 0.0) + s
    out = dict(tag=cfg["tag"], sims=n, captured=lines["captured"], proj={away: round(mA, 2), home: round(mH, 2), "total": round(mt, 2)},
               plays=plays, model_market_disagree=disagree, calibration=cal, not_modeled=lines["not_modeled"])
    od = os.path.join(HERE, "out"); os.makedirs(od, exist_ok=True)
    json.dump(out, open(os.path.join(od, f"{cfg['tag']}_ev.json"), "w"), indent=1)
    print("proj", out["proj"], "plays", len(plays), "sized total", round(used, 2))
    for x in plays[:40]:
        print(f"{x['play'][:44]:44s} {x['price']:+5d} pM {x['p_model']:.3f} nv {x['p_market_nv']:.3f} rawEV {x['raw_ev']*100:5.1f}% blEV {x['blended_ev']*100:4.1f}% {x['stars']}* {x['conf']:6s} {x['size_u']}u")

if __name__ == "__main__":
    main()
