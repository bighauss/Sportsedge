"""SportsEdge NFL DFS - DraftKings Showdown Monte Carlo engine (v1).

Python standard library only. RESEARCH / PAPER: a DFS projection is never Model_P,
and contest EV is BLOCKED because no validated ownership feed exists.

Pipeline: game config (market lines, weather, injuries, roles)
  -> correlated play-level Monte Carlo of the whole game (both offenses, kickers, DSTs)
  -> DK scoring per sim -> player distributions
  -> enumerate every legal CPT+5 FLEX lineup (<= $50k, both teams)
  -> evaluate candidates on the SAME sims (mean, p90, p99, optimal-lineup rate).

Usage: python models/nfl_dfs/showdown_mc.py [config.json] [sims]
"""
import bisect, csv, itertools, json, math, os, random, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------- DK scoring ----------------
def dk_offense(py=0, ptd=0, ints=0, ry=0, rtd=0, rec=0, rcy=0, rctd=0, fum=0):
    p = py * 0.04 + ptd * 4 - ints + ry * 0.1 + rtd * 6 + rec + rcy * 0.1 + rctd * 6 - fum
    if py >= 300: p += 3
    if ry >= 100: p += 3
    if rcy >= 100: p += 3
    return p

def dk_dst(pa, sacks, ints, frec, tds, safeties=0):
    p = sacks + 2 * ints + 2 * frec + 6 * tds + 2 * safeties
    if pa == 0: p += 10
    elif pa <= 6: p += 7
    elif pa <= 13: p += 4
    elif pa <= 20: p += 1
    elif pa <= 27: p += 0
    elif pa <= 34: p -= 1
    else: p -= 4
    return p

# ---------------- random helpers ----------------
def poisson(rng, lam):
    if lam <= 0: return 0
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L: return k
        k += 1

def picker(weights):
    names = list(weights); tot = sum(weights.values()); cum, c = [], 0.0
    for n in names:
        c += weights[n] / tot; cum.append(c)
    return names, cum

def pick(rng, names, cum):
    return names[min(bisect.bisect_left(cum, rng.random()), len(names) - 1)]

# ---------------- one team's offense ----------------
def sim_team(rng, t, zg, zt, active):
    f_score = math.exp(0.22 * (0.55 * zg + 0.835 * zt) - 0.5 * 0.22 ** 2)
    f_vol = math.exp(0.08 * zg)
    stat = {}
    def S(n):
        return stat.setdefault(n, dict(py=0, ptd=0, ints=0, ry=0, rtd=0, rec=0, rcy=0, rctd=0, fum=0))
    tg = {n: w for n, w in t["targets"].items() if active.get(n, True)}
    tn, tc = picker(tg)
    att = max(15, int(round(rng.gauss(t["pass_att"] * f_vol, 4.0))))
    qb = t["qb"]
    for _ in range(att):
        r = pick(rng, tn, tc); prof = t["recv"].get(r, t["recv"]["_default"])
        if rng.random() < prof[0]:
            y = rng.gammavariate(1.35, prof[1] * math.sqrt(f_score) / 1.35)
            s = S(r); s["rec"] += 1; s["rcy"] += y; S(qb)["py"] += y
    # pass TDs
    tdw = {n: w for n, w in t["pass_td_w"].items() if active.get(n, True)}
    dn, dc = picker(tdw)
    for _ in range(poisson(rng, t["pass_td"] * f_score)):
        r = pick(rng, dn, dc); s = S(r); s["rctd"] += 1; S(qb)["ptd"] += 1
        if s["rec"] < s["rctd"]:
            s["rec"] += 1; y = rng.uniform(3, 25); s["rcy"] += y; S(qb)["py"] += y
    S(qb)["ints"] += poisson(rng, t["int_rate"] * att / max(f_score, 0.6) ** 0.5)
    # rushing
    rw = {n: w for n, w in t["rush"].items() if active.get(n, True)}
    rn, rc = picker(rw)
    ratt = max(10, int(round(rng.gauss(t["rush_att"] * f_vol, 3.5))))
    for _ in range(ratt):
        r = pick(rng, rn, rc); ypc = t["ypc"].get(r, 4.0)
        y = rng.gammavariate(1.1, ypc / 1.1) - (rng.random() < 0.12) * rng.uniform(0, 4)
        S(r)["ry"] += y
    rtw = {n: w for n, w in t["rush_td_w"].items() if active.get(n, True)}
    tn2, tc2 = picker(rtw)
    rush_td = poisson(rng, t["rush_td"] * f_score)
    for _ in range(rush_td):
        S(pick(rng, tn2, tc2))["rtd"] += 1
    for _ in range(poisson(rng, t["fum_lost"])):
        S(pick(rng, rn, rc))["fum"] += 1
    tds = sum(s["ptd"] for s in stat.values()) + rush_td
    fga = poisson(rng, t["fga"] * (1.15 - 0.15 * f_score))
    fgm, kpts = 0, 0
    for _ in range(fga):
        u = rng.random()
        dist_pts, mk = (5, t["fg50"]) if u < 0.17 else ((4, t["fg40"]) if u < 0.47 else (3, t["fg_short"]))
        if rng.random() < mk: fgm += 1; kpts += dist_pts
        else: kpts -= 1
    xp = sum(1 for _ in range(tds) if rng.random() < 0.95)
    kpts += xp
    pts = 6 * tds + xp + 3 * fgm
    return stat, kpts, pts, S(qb)["ints"], tds

def run(cfg, n_sims, seed=7):
    rng = random.Random(seed)
    teams = cfg["teams"]; names = list(teams)
    out = {p: [] for p in cfg["players"]}
    game = []
    for _ in range(n_sims):
        zg = rng.gauss(0, 1)
        active = {p: (rng.random() < v["p_active"]) for p, v in cfg["players"].items()}
        res = {}
        for tm in names:
            res[tm] = sim_team(rng, teams[tm], zg, rng.gauss(0, 1), active)
        for tm in names:
            opp = [x for x in names if x != tm][0]
            stat, kpts, pts, _, _ = res[tm]
            ostat, okp, opts, oints, otds = res[opp]
            d = teams[tm]["dst"]
            dst_td = poisson(rng, d["td"])
            dsts = dk_dst(opts, poisson(rng, d["sacks"]), oints, poisson(rng, d["frec"]), dst_td)
            for p, v in cfg["players"].items():
                if v["team"] != tm: continue
                if not active[p]: out[p].append(0.0); continue
                if v["pos"] == "K": out[p].append(kpts)
                elif v["pos"] == "DST": out[p].append(dsts)
                else:
                    s = stat.get(p)
                    out[p].append(dk_offense(**s) if s else 0.0)
        game.append((res[names[0]][2], res[names[1]][2]))
    return out, game

def q(xs, p):
    s = sorted(xs); return s[min(len(s) - 1, int(p * len(s)))]

def load_salaries(path):
    rows = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["Name"], {})[r["Roster Position"]] = int(r["Salary"])
            rows[r["Name"]]["team"] = r["TeamAbbrev"]; rows[r["Name"]]["status"] = r["Status"]
            rows[r["Name"]]["pos"] = r["Position"]
    return rows

def optimize(sims, sal, pool, n_keep=4000, cap=50000):
    S = len(next(iter(sims.values())))
    mean = {p: statistics.fmean(sims[p]) for p in pool}
    sd = {p: statistics.pstdev(sims[p]) for p in pool}
    cands = []
    for flex in itertools.combinations(pool, 5):
        fs = sum(sal[p]["FLEX"] for p in flex)
        if fs > cap: continue
        fm = sum(mean[p] for p in flex); fc = sum(mean[p] + sd[p] for p in flex)
        for c in pool:
            if c in flex: continue
            tot = fs + sal[c]["CPT"]
            if tot > cap or tot < cap - 4000: continue
            teams = {sal[x]["team"] for x in flex + (c,)}
            if len(teams) < 2: continue
            cands.append((1.5 * mean[c] + fm, 1.5 * (mean[c] + sd[c]) + fc, c, flex, tot))
    by_mean = sorted(cands, key=lambda x: -x[0])[:n_keep]
    by_ceil = sorted(cands, key=lambda x: -x[1])[:n_keep]
    uniq = {(x[2], x[3]): x for x in by_mean + by_ceil}
    lineups = list(uniq.values())
    best = [-1e9] * S; best_i = [0] * S; stats = []
    for i, (m, _, c, flex, tot) in enumerate(lineups):
        cols = [sims[c]] + [sims[p] for p in flex]
        sc = [1.5 * a + b + d + e + g + h for a, b, d, e, g, h in zip(*cols)]
        for s in range(S):
            if sc[s] > best[s]: best[s] = sc[s]; best_i[s] = i
        srt = sorted(sc)
        stats.append(dict(cpt=c, flex=list(flex), salary=tot, mean=round(statistics.fmean(sc), 2),
                          p90=round(srt[int(.9 * S)], 2), p99=round(srt[int(.99 * S)], 2)))
    for i, st in enumerate(stats): st["opt_rate"] = 0.0
    for s in range(S): stats[best_i[s]]["opt_rate"] += 1 / S
    cpt_rate, flex_rate = {}, {}
    for s in range(S):
        st = stats[best_i[s]]
        cpt_rate[st["cpt"]] = cpt_rate.get(st["cpt"], 0) + 1 / S
        for p in st["flex"]: flex_rate[p] = flex_rate.get(p, 0) + 1 / S
    return stats, cpt_rate, flex_rate, len(cands)

def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "games", "PIT_CIN_2026-11-15.json")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
    cfg = json.load(open(cfg_path))
    sal = load_salaries(os.path.join(HERE, cfg["salary_file"]))
    sims, game = run(cfg, n)
    proj = []
    for p, xs in sims.items():
        s = sal[p]
        proj.append(dict(player=p, team=s["team"], pos=s["pos"], flex_sal=s["FLEX"], cpt_sal=s["CPT"],
                         status=s["status"], p_active=cfg["players"][p]["p_active"],
                         mean=round(statistics.fmean(xs), 2), median=round(q(xs, .5), 2),
                         sd=round(statistics.pstdev(xs), 2), p10=round(q(xs, .1), 2),
                         p90=round(q(xs, .9), 2), p99=round(q(xs, .99), 2),
                         value=round(statistics.fmean(xs) / s["FLEX"] * 1000, 2)))
    proj.sort(key=lambda r: -r["mean"])
    pool = [r["player"] for r in proj if r["mean"] >= cfg.get("pool_min_mean", 1.5)]
    stats, cpt_rate, flex_rate, n_legal = optimize(sims, sal, pool)
    for r in proj:
        r["cpt_opt_rate"] = round(cpt_rate.get(r["player"], 0), 4)
        r["flex_opt_rate"] = round(flex_rate.get(r["player"], 0), 4)
    a = [g[0] for g in game]; b = [g[1] for g in game]; names = list(cfg["teams"])
    summary = dict(sims=n, legal_lineups=n_legal, evaluated=len(stats),
                   team_mean={names[0]: round(statistics.fmean(a), 2), names[1]: round(statistics.fmean(b), 2)},
                   total_mean=round(statistics.fmean([x + y for x, y in game]), 2),
                   p_win={names[1]: round(sum(y > x for x, y in game) / n, 3)},
                   p_cover_home_minus=round(sum(y - x > cfg["market"]["spread_home"] for x, y in game) / n, 3),
                   p_over=round(sum(x + y > cfg["market"]["total"] for x, y in game) / n, 3),
                   contest_ev="BLOCKED: no validated ownership feed (DFS lane rule)",
                   label="RESEARCH / PAPER - not Model_P, unvalidated")
    od = os.path.join(HERE, "out")
    os.makedirs(od, exist_ok=True)
    tag = cfg["tag"]
    with open(os.path.join(od, f"{tag}_projections.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(proj[0])); w.writeheader(); w.writerows(proj)
    top_mean = sorted(stats, key=lambda x: -x["mean"])[:20]
    top_opt = sorted(stats, key=lambda x: (-x["opt_rate"], -x["p99"]))[:20]
    json.dump(dict(summary=summary, top_by_mean=top_mean, top_by_opt_rate=top_opt),
              open(os.path.join(od, f"{tag}_lineups.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))
    for r in proj[:24]:
        print(f"{r['player']:22s} {r['team']} {r['pos']:3s} {r['flex_sal']:>6} mean {r['mean']:5.1f} p90 {r['p90']:5.1f} "
              f"cpt% {r['cpt_opt_rate']*100:4.1f} flex% {r['flex_opt_rate']*100:4.1f}")
    print("TOP MEAN", json.dumps(top_mean[0]))
    print("TOP OPT ", json.dumps(top_opt[:3]))

if __name__ == "__main__":
    main()
