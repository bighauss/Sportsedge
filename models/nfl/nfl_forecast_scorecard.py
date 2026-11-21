"""NFL forecast scorecard (research only, stdlib only).

Scores several forecasters on the SAME games at the SAME cutoff:
  * any prediction CSVs you supply (e.g. the existing ridge walk-forward output,
    an EPA challenger), and
  * a built-in walk-forward Elo baseline (FiveThirtyEight-style) that only uses
    results available before each game's forecast cutoff.

Metrics per model: margin MAE, total MAE, Brier score, log loss, a 10-bin
calibration table, and counts of scored / blocked / missing games. A game is
scored for comparison only if EVERY model has a prediction for it (common set),
so no model can look better by skipping hard rows.

Inputs
  --games    game_id,season,week,home_team,away_team,kickoff_utc,forecast_asof_utc
  --results  game_id,home_score,away_score,final_utc,result_available_utc
  --pred NAME=PATH (repeatable) CSV: game_id,pred_margin,pred_total,p_home_win
             (margin = home - away; blank cells allowed -> that metric skipped)
No odds are read. Sportsbook prices are not an input.
"""
import argparse, csv, json, math, sys
from datetime import datetime

def ts(s):
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timestamp must be offset-aware: %r" % s)
    return d

def read_csv(path, required):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        miss = [c for c in required if c not in (r.fieldnames or [])]
        if miss:
            raise ValueError("%s missing columns %s" % (path, miss))
        rows = list(r)
    ids = [x["game_id"] for x in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("%s has duplicate game_id" % path)
    return {x["game_id"]: x for x in rows}

def fnum(v):
    v = (v or "").strip()
    return float(v) if v else None

# ---------------- Elo baseline ----------------
def elo_baseline(games, results, k=20.0, hfa=48.0, revert=1/3, pts_per_elo=25.0):
    """Walk-forward Elo. For each game, only results available at its forecast
    cutoff are applied. Season start reverts ratings 1/3 toward 1505."""
    order = sorted(games.values(), key=lambda g: ts(g["kickoff_utc"]))
    done = sorted(((ts(r["result_available_utc"]), gid) for gid, r in results.items()
                   if gid in games), key=lambda x: x[0])
    rating, season_of, applied, out, i = {}, {}, set(), {}, 0
    def get(t, season):
        if t not in rating:
            rating[t] = 1505.0; season_of[t] = season
        elif season_of[t] != season:
            rating[t] = rating[t] + (1505.0 - rating[t]) * revert; season_of[t] = season
        return rating[t]
    def apply(gid):
        g, r = games[gid], results[gid]
        s = g["season"]
        h, a = get(g["home_team"], s), get(g["away_team"], s)
        diff = h + hfa - a
        exp = 1 / (1 + 10 ** (-diff / 400))
        m = float(r["home_score"]) - float(r["away_score"])
        res = 1.0 if m > 0 else 0.0 if m < 0 else 0.5
        mult = math.log(abs(m) + 1) * 2.2 / ((diff if m > 0 else -diff) * 0.001 + 2.2)
        delta = k * mult * (res - exp)
        rating[g["home_team"]] = h + delta
        rating[g["away_team"]] = a - delta
    for g in order:
        cut = ts(g["forecast_asof_utc"])
        while i < len(done) and done[i][0] <= cut:
            gid = done[i][1]; i += 1
            if gid not in applied and ts(games[gid]["kickoff_utc"]) < cut:
                apply(gid); applied.add(gid)
        s = g["season"]
        diff = get(g["home_team"], s) + hfa - get(g["away_team"], s)
        out[g["game_id"]] = {"pred_margin": diff / pts_per_elo, "pred_total": None,
                             "p_home_win": 1 / (1 + 10 ** (-diff / 400))}
    return out

# ---------------- metrics ----------------
def score(preds, results, ids):
    mm, tm, br, ll, cal = [], [], [], [], [[0, 0.0, 0.0] for _ in range(10)]
    for gid in ids:
        p, r = preds[gid], results[gid]
        hs, as_ = float(r["home_score"]), float(r["away_score"])
        if p["pred_margin"] is not None: mm.append(abs(p["pred_margin"] - (hs - as_)))
        if p["pred_total"] is not None: tm.append(abs(p["pred_total"] - (hs + as_)))
        q = p["p_home_win"]
        if q is not None and hs != as_:
            y = 1.0 if hs > as_ else 0.0
            q = min(max(q, 1e-6), 1 - 1e-6)
            br.append((q - y) ** 2)
            ll.append(-(y * math.log(q) + (1 - y) * math.log(1 - q)))
            b = cal[min(int(q * 10), 9)]; b[0] += 1; b[1] += q; b[2] += y
    avg = lambda v: round(sum(v) / len(v), 4) if v else None
    return {"margin_mae": avg(mm), "n_margin": len(mm), "total_mae": avg(tm), "n_total": len(tm),
            "brier": avg(br), "log_loss": avg(ll), "n_prob": len(br),
            "calibration": [{"bin": "%d-%d%%" % (i * 10, i * 10 + 10), "n": b[0],
                             "mean_pred": round(b[1] / b[0], 3) if b[0] else None,
                             "hit_rate": round(b[2] / b[0], 3) if b[0] else None}
                            for i, b in enumerate(cal)]}

def week_bootstrap(preds_a, preds_b, results, games, ids, metric="brier", n=2000, seed=7):
    """Paired bootstrap by week (games in the same week resampled together)."""
    import random
    rnd = random.Random(seed)
    weeks = {}
    for gid in ids:
        weeks.setdefault((games[gid]["season"], games[gid]["week"]), []).append(gid)
    keys = list(weeks)
    def m(p, sel):
        return score(p, results, sel)[metric]
    diffs = []
    for _ in range(n):
        sel = [g for k in (rnd.choice(keys) for _ in keys) for g in weeks[k]]
        a, b = m(preds_a, sel), m(preds_b, sel)
        if a is not None and b is not None: diffs.append(a - b)
    if not diffs: return None
    diffs.sort()
    return {"metric": metric, "mean_diff": round(sum(diffs) / len(diffs), 4),
            "ci95": [round(diffs[int(.025 * len(diffs))], 4), round(diffs[int(.975 * len(diffs)) - 1], 4)],
            "weeks": len(keys)}

def run(games_p, results_p, pred_specs, baseline="elo"):
    games = read_csv(games_p, ["game_id", "season", "week", "home_team", "away_team",
                               "kickoff_utc", "forecast_asof_utc"])
    for g in games.values():
        if not ts(g["forecast_asof_utc"]) < ts(g["kickoff_utc"]):
            raise ValueError("forecast_asof_utc must precede kickoff for %s" % g["game_id"])
    results = read_csv(results_p, ["game_id", "home_score", "away_score", "final_utc",
                                   "result_available_utc"])
    models = {"elo_baseline": elo_baseline(games, results)}
    for spec in pred_specs:
        name, path = spec.split("=", 1)
        rows = read_csv(path, ["game_id", "pred_margin", "pred_total", "p_home_win"])
        models[name] = {gid: {k: fnum(r[k]) for k in ("pred_margin", "pred_total", "p_home_win")}
                        for gid, r in rows.items() if gid in games}
    graded = [gid for gid in games if gid in results]
    common = [gid for gid in graded if all(gid in m for m in models.values())]
    report = {"research_only": True, "uses_odds": False, "games": len(games),
              "graded": len(graded), "common_scored": len(common), "models": {}}
    for name, m in models.items():
        s = score(m, results, common)
        s["missing_or_blocked"] = len([g for g in graded if g not in m])
        report["models"][name] = s
    report["vs_baseline"] = {name: week_bootstrap(m, models["elo_baseline"], results, games, common)
                             for name, m in models.items() if name != "elo_baseline"}
    report["adoption_rule"] = ("Adopt a challenger only if its pre-chosen metric beats the baseline on "
                               "untouched games with a 95% CI entirely below 0; otherwise keep the simpler model.")
    return report

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--games", required=True); ap.add_argument("--results", required=True)
    ap.add_argument("--pred", action="append", default=[]); ap.add_argument("--out")
    a = ap.parse_args(argv)
    rep = run(a.games, a.results, a.pred)
    txt = json.dumps(rep, indent=2)
    if a.out:
        with open(a.out, "x") as f: f.write(txt)
    print(txt)

if __name__ == "__main__":
    main()
