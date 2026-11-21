#!/usr/bin/env python3
"""CFB Over-bias backtest (RESEARCH ONLY, no model changes).

For each completed week W of a season, rebuild the frozen RUN IT model's projections using only
point-in-time inputs (CFBD advanced stats with endWeek = W-1, completed-game counts before W) and
compare against final scores and CFBD consensus lines for week W.

Leakage controls: SP+ is end-of-season in CFBD, so it is EXCLUDED (model runs its matchup-only
path, which it does when no ratings row exists). Talent/returning are preseason. Weather, injuries,
travel/rest are not reconstructed (they are small adjustments in the model).

Reports, per component (no tuning is done here):
  * bias: mean(model total - actual), mean(market total - actual), mean(model - market)
  * Over rate: model says Over vs actual Over rate
  * Brier / log loss for P(Over) and P(home covers): raw model, no-vig market, 30/70 blend
  * baseline decomposition: league-mean term (LG_PPG) vs realised league scoring
  * sensitivity: same metrics with the model's total re-centred on realised league scoring
    (diagnostic only; tells us how much of the bias the fixed baseline explains)
Props cannot be backtested: CFBD has no historical prop prices.
"""
import argparse, json, math, os, sys, urllib.parse, urllib.request
from pathlib import Path
from statistics import mean
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "models" / "cfb"))
import sportsedge_cfb_model as M  # frozen, unchanged
import cfb_run_it as R             # adapters (games_played, with_games, http)

CFBD = "https://api.collegefootballdata.com"

def get(path, key, **q):
    url = f"{CFBD}{path}?" + urllib.parse.urlencode(q)
    return json.loads(R.http_bytes(url, key))

def consensus(lines):
    """Prefer a book named consensus, else the first book with both spread and total."""
    ls = lines.get("lines") or []
    pick = [l for l in ls if str(l.get("provider", "")).lower() == "consensus"] or \
           [l for l in ls if l.get("spread") is not None and l.get("overUnder") is not None]
    return pick[0] if pick else None

def brier(ps, ys): return mean((p - y) ** 2 for p, y in zip(ps, ys))
def logloss(ps, ys):
    e = 1e-6; return mean(-(y * math.log(min(max(p, e), 1 - e)) + (1 - y) * math.log(min(max(1 - p, e), 1 - e))) for p, y in zip(ps, ys))

def week_rows(season, week, key, all_games):
    adv = get("/stats/season/advanced", key, year=season, excludeGarbageTime="true", startWeek=1, endWeek=week - 1)
    games = [g for g in all_games if g.get("week") == week and g.get("completed")
             and g.get("homePoints") is not None and g.get("awayPoints") is not None]
    lines = {l["id"]: l for l in get("/lines", key, year=season, week=week, seasonType="regular")}
    import datetime as dt
    first_ko = min((dt.datetime.fromisoformat(g["startDate"].replace("Z", "+00:00")) for g in games), default=None)
    if not first_ko: return []
    advg = R.with_games(adv, R.games_played(all_games, first_ko))
    ctx = {"adv": M.by(advg, "team"), "lm": M.league_means(advg), "talent": {}, "ret": {}, "ratings": {},
           "teams": {}, "venues": {}, "injuries": [], "weather": {}, "rest": {}, "cross": {}, "usage": []}
    prior = [x for x in all_games if x.get("completed") and x.get("homePoints") is not None
             and dt.datetime.fromisoformat(x["startDate"].replace("Z", "+00:00")) < first_ko]
    pit_ppg = mean((x["homePoints"] + x["awayPoints"]) / 2 for x in prior) if prior else None
    out = []
    for g in games:
        H, A = g["homeTeam"], g["awayTeam"]
        if H not in ctx["adv"] or A not in ctx["adv"] or not ctx["adv"][H].get("games") or not ctx["adv"][A].get("games"):
            continue
        if R.missing_adv(ctx["adv"][H]) or R.missing_adv(ctx["adv"][A]): continue
        L = consensus(lines.get(g["id"], {}))
        if not L: continue
        try:
            pj = M.run_game({**g, "week": week}, ctx)
            orig = M.LG_PPG
            try:
                M.LG_PPG = pit_ppg if pit_ppg else orig        # CANDIDATE (research only)
                cj = M.run_game({**g, "week": week}, ctx)
            finally:
                M.LG_PPG = orig
        except Exception: continue
        out.append({"week": week, "game": f"{A} @ {H}", "proj_total": pj["total"], "proj_margin": pj["margin"],
                    "pts_h": pj["pts_home"], "pts_a": pj["pts_away"], "cand_total": cj["total"], "cand_margin": cj["margin"], "pit_ppg": pit_ppg, "mkt_total": float(L["overUnder"]),
                    "mkt_spread": float(L["spread"]), "act_h": g["homePoints"], "act_a": g["awayPoints"]})
    return out

def metrics(rows, shift=0.0):
    P = lambda mean_, line, sd: M.pgt(mean_, line, sd)
    tot = [r for r in rows if r["act_h"] + r["act_a"] != r["mkt_total"]]
    y_over = [1 if r["act_h"] + r["act_a"] > r["mkt_total"] else 0 for r in tot]
    p_model = [P(r["proj_total"] + shift, r["mkt_total"], M.SD_TOTAL) for r in tot]
    p_mkt = [0.5] * len(tot)
    p_blend = [0.3 * a + 0.7 * b for a, b in zip(p_model, p_mkt)]
    sp = [r for r in rows if (r["act_h"] - r["act_a"]) != -r["mkt_spread"]]
    y_cov = [1 if (r["act_h"] - r["act_a"]) > -r["mkt_spread"] else 0 for r in sp]
    p_cov = [P(r["proj_margin"], -r["mkt_spread"], M.SD_MARGIN) for r in sp]
    return {
        "n_total": len(tot), "n_spread": len(sp),
        "bias_model_total_vs_actual": mean(r["proj_total"] + shift - r["act_h"] - r["act_a"] for r in rows),
        "bias_market_total_vs_actual": mean(r["mkt_total"] - r["act_h"] - r["act_a"] for r in rows),
        "model_minus_market_total": mean(r["proj_total"] + shift - r["mkt_total"] for r in rows),
        "model_says_over_rate": mean(1 if p > 0.5 else 0 for p in p_model),
        "actual_over_rate": mean(y_over),
        "brier_over": {"model": brier(p_model, y_over), "market": brier(p_mkt, y_over), "blend": brier(p_blend, y_over)},
        "logloss_over": {"model": logloss(p_model, y_over), "market": logloss(p_mkt, y_over), "blend": logloss(p_blend, y_over)},
        "brier_cover": {"model": brier(p_cov, y_cov), "market": brier([0.5] * len(y_cov), y_cov),
                        "blend": brier([0.3 * p + 0.35 for p in p_cov], y_cov)},
        "mae_total": {"model": mean(abs(r["proj_total"] + shift - r["act_h"] - r["act_a"]) for r in rows),
                      "market": mean(abs(r["mkt_total"] - r["act_h"] - r["act_a"]) for r in rows)},
        "mae_margin": {"model": mean(abs(r["proj_margin"] - (r["act_h"] - r["act_a"])) for r in rows),
                       "market": mean(abs(-r["mkt_spread"] - (r["act_h"] - r["act_a"])) for r in rows)},
    }

def candidate_rows(rows):
    return [dict(r, proj_total=r["cand_total"], proj_margin=r["cand_margin"]) for r in rows if "cand_total" in r]

def report(rows):
    league_pts = mean((r["act_h"] + r["act_a"]) / 2 for r in rows)
    base = metrics(rows)
    shift = -base["bias_model_total_vs_actual"]
    md = ["# CFB Over-bias backtest — RESEARCH ONLY (no model changes)", "",
          f"Games: {len(rows)} · weeks {min(r['week'] for r in rows)}–{max(r['week'] for r in rows)} · "
          f"SP+ excluded (not point-in-time) · market p for totals/spreads = 0.5 (consensus lines are near -110)", "",
          f"Model LG_PPG baseline 28.0 vs realised points/team in these games {league_pts:.1f}", "",
          "| Metric | Frozen model | Diagnostic: total re-centred |", "|---|---|---|"]
    rec = metrics(rows, shift)
    for k in ("bias_model_total_vs_actual", "bias_market_total_vs_actual", "model_minus_market_total",
              "model_says_over_rate", "actual_over_rate"):
        md.append(f"| {k} | {base[k]:+.3f} | {rec[k]:+.3f} |")
    for k in ("brier_over", "logloss_over", "brier_cover", "mae_total", "mae_margin"):
        md.append(f"| {k} | " + ", ".join(f"{a} {v:.4f}" for a, v in base[k].items()) + " | " +
                  ", ".join(f"{a} {v:.4f}" for a, v in rec[k].items()) + " |")
    cr = candidate_rows(rows)
    if cr:
        c = metrics(cr)
        md += ["", "## Candidate C1: league baseline = point-in-time realised points/team (fixed 28 removed)", "",
               "| Metric | Frozen | Candidate C1 | Market |", "|---|---|---|---|",
               f"| total bias vs actual | {base['bias_model_total_vs_actual']:+.2f} | {c['bias_model_total_vs_actual']:+.2f} | {base['bias_market_total_vs_actual']:+.2f} |",
               f"| says Over rate (actual {base['actual_over_rate']:.3f}) | {base['model_says_over_rate']:.3f} | {c['model_says_over_rate']:.3f} | — |",
               f"| Brier Over | {base['brier_over']['model']:.4f} | {c['brier_over']['model']:.4f} | {base['brier_over']['market']:.4f} |",
               f"| Brier Over, 30/70 blend | {base['brier_over']['blend']:.4f} | {c['brier_over']['blend']:.4f} | — |",
               f"| log loss Over | {base['logloss_over']['model']:.4f} | {c['logloss_over']['model']:.4f} | {base['logloss_over']['market']:.4f} |",
               f"| MAE total | {base['mae_total']['model']:.2f} | {c['mae_total']['model']:.2f} | {base['mae_total']['market']:.2f} |",
               f"| Brier cover | {base['brier_cover']['model']:.4f} | {c['brier_cover']['model']:.4f} | {base['brier_cover']['market']:.4f} |"]
        js_c = c
    else:
        js_c = None
    md += ["", f"Re-centring shift applied in the diagnostic column: {shift:+.2f} total points (NOT applied to the model).",
           "Lower Brier / log loss is better; the market column is the same-time baseline to beat."]
    return "\n".join(md) + "\n", {"frozen": base, "recentred": rec, "candidate_c1": js_c, "shift": shift, "n": len(rows)}

def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--season", type=int, default=2026); a.add_argument("--start-week", type=int, default=4)
    a.add_argument("--end-week", type=int, default=12); a.add_argument("--out", required=True)
    a.add_argument("--fixture", help="offline rows JSON (tests)")
    x = a.parse_args(argv)
    if x.fixture:
        rows = json.load(open(x.fixture))
    else:
        key = os.environ.get("CFBD_API_KEY")
        if not key: print("BLOCKED CFBD_API_KEY_ABSENT", file=sys.stderr); return 2
        all_games = get("/games", key, year=x.season, seasonType="regular", classification="fbs")
        rows = []
        for w in range(x.start_week, x.end_week + 1):
            rows += week_rows(x.season, w, key, all_games)
    if not rows: print("BLOCKED NO_ROWS", file=sys.stderr); return 2
    md, js = report(rows)
    Path(x.out).mkdir(parents=True, exist_ok=True)
    (Path(x.out) / "bias.md").write_text(md); (Path(x.out) / "bias.json").write_text(json.dumps(js, indent=1))
    (Path(x.out) / "rows.json").write_text(json.dumps(rows))
    print(md); return 0

if __name__ == "__main__":
    raise SystemExit(main())
