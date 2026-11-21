#!/usr/bin/env python3
"""CBB home-court backtest (RESEARCH ONLY, no model changes).

Day-by-day walk-forward over the season: fit the frozen CBBD-native model's context with finals
before each day, project that day's games, and compare against final margins and CBBD lines.

Candidates (computed here only, never written to the model):
  C1  HCA = intercept of OLS(residual ~ predicted margin) over prior non-neutral finals.
      Early-season "buy games" put the stronger team at home, so the frozen model's mean residual
      absorbs rating compression into HCA. The intercept separates the two.
  C2  C1 plus the slope: margin = a + (1 + b) * predicted neutral margin.
Leakage caveat: CBBD adjusted ratings are a current snapshot, not point-in-time, which flatters every
column equally (the market column has no leakage). Use relative comparisons only.
"""
import argparse, datetime as dt, json, math, os, sys, urllib.parse
from pathlib import Path
from statistics import mean
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "models" / "cbb"))
import cbbd_native_score_model as M   # frozen, unchanged
import cbb_run_it as R

API = "https://api.collegebasketballdata.com"

def get(path, key, **q):
    return R._get(f"{API}{path}?" + urllib.parse.urlencode(q), key)

def ols(xs, ys):
    n = len(xs); mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    return my - b * mx, b

def cdf(z): return (1 + math.erf(z / math.sqrt(2))) / 2
def brier(ps, ys): return mean((p - y) ** 2 for p, y in zip(ps, ys))
def ll(ps, ys):
    e = 1e-6; return mean(-(y * math.log(min(max(p, e), 1 - e)) + (1 - y) * math.log(min(max(1 - p, e), 1 - e))) for p, y in zip(ps, ys))

def pick_line(entry):
    ls = entry.get("lines") or []
    ok = [l for l in ls if l.get("spread") is not None]
    return ok[0] if ok else None

def walk(ratings_body, games, boxes, lines, season, days):
    finals = [g for g in games if g.get("status") == "final" and g.get("startTimeTbd") is False
              and type(g.get("neutralSite")) is bool]
    prior_all, _ = R.prior_games(finals, boxes, "2100-01-01T00:00:00Z", season)
    for r in prior_all:   # research approximation: final known ~3h after tip
        r["final_captured_utc"] = R.utcz(R.parse_z(r["tipoff_utc"]) + dt.timedelta(hours=3))
    line_by = {str(l.get("gameId")): pick_line(l) for l in lines}
    rows = []
    for day in days:
        freeze = dt.datetime.combine(day, dt.time(12, 0), dt.timezone.utc)
        try:
            ctx = M.fit_context(ratings_body, prior_all, season=season, freeze_utc=R.utcz(freeze))
        except M.Pass:
            continue
        if ctx["hca"]["value"] is None or ctx["sd"]["margin"] is None: continue
        xs, ys = [], []
        for g in M.eligible_prior_games(prior_all, season=season, freeze=freeze)[0]:
            if g["neutral"] is not False or g["home"] not in ctx["ratings"] or g["away"] not in ctx["ratings"]: continue
            eh, ea = M._effs(ctx, g["home"], g["away"]); pred = (eh - ea) * g["possessions"] / 100
            xs.append(pred); ys.append((g["home_points"] - g["away_points"]) - pred)
        a, b = ols(xs, ys)
        for g in finals:
            tip = R.parse_z(g["startDate"])
            if tip.date() != day or tip <= freeze: continue
            L = line_by.get(str(g["id"]))
            if not L: continue
            try:
                p = M.project(ctx, str(g["homeTeamId"]), str(g["awayTeamId"]), neutral=g["neutralSite"])
            except M.Pass:
                continue
            hca = p["hca_applied"]; neutral_pred = p["margin"] - hca
            home = not g["neutralSite"]
            rows.append({"day": str(day), "frozen": p["margin"], "c1": neutral_pred + (a if home else 0.0),
                         "c2": (1 + b) * neutral_pred + (a if home else 0.0), "sd": p["sd_margin"],
                         "spread": float(L["spread"]), "act": g["homePoints"] - g["awayPoints"],
                         "home_ml": L.get("homeMoneyline"), "away_ml": L.get("awayMoneyline"),
                         "neutral": g["neutralSite"], "hca_frozen": hca, "hca_c1": a, "slope": b})
    return rows

def report(rows):
    cols = ("frozen", "c1", "c2")
    sp = [r for r in rows if r["act"] + r["spread"] != 0]
    y = [1 if r["act"] + r["spread"] > 0 else 0 for r in sp]
    ml = [r for r in rows if r["home_ml"] and r["away_ml"]]
    yml = [1 if r["act"] > 0 else 0 for r in ml]
    pmk = [M.no_vig(int(r["home_ml"]), int(r["away_ml"]))[0] for r in ml]
    md = ["# CBB home-court backtest — RESEARCH ONLY (no model changes)", "",
          f"Games: {len(rows)} · days {rows[0]['day']}–{rows[-1]['day']} · non-neutral {sum(not r['neutral'] for r in rows)}",
          f"Fitted HCA, last day: frozen {rows[-1]['hca_frozen']:.2f} · C1 intercept {rows[-1]['hca_c1']:.2f} · C2 slope {rows[-1]['slope']:+.3f}",
          "Ratings are a current snapshot (leakage flatters all model columns equally; market has none).", "",
          "| Metric | Frozen | C1 (intercept HCA) | C2 (intercept + slope) | Market |", "|---|---|---|---|---|"]
    def row(name, f, mkt):
        md.append(f"| {name} | " + " | ".join(f(c) for c in cols) + f" | {mkt} |")
    row("mean margin error (home)", lambda c: f"{mean(r[c] - r['act'] for r in rows):+.2f}", f"{mean(-r['spread'] - r['act'] for r in rows):+.2f}")
    row("MAE margin", lambda c: f"{mean(abs(r[c] - r['act']) for r in rows):.2f}", f"{mean(abs(-r['spread'] - r['act']) for r in rows):.2f}")
    row("picks home ATS rate", lambda c: f"{mean(1 if r[c] + r['spread'] > 0 else 0 for r in sp):.3f}", f"actual home cover {mean(y):.3f}")
    row("Brier home cover", lambda c: f"{brier([cdf((r[c] + r['spread']) / r['sd']) for r in sp], y):.4f}", "0.2500")
    row("log loss home cover", lambda c: f"{ll([cdf((r[c] + r['spread']) / r['sd']) for r in sp], y):.4f}", "0.6931")
    if ml:
        row("Brier home ML", lambda c: f"{brier([cdf(r[c] / r['sd']) for r in ml], yml):.4f}", f"{brier(pmk, yml):.4f}")
        row("log loss home ML", lambda c: f"{ll([cdf(r[c] / r['sd']) for r in ml], yml):.4f}", f"{ll(pmk, yml):.4f}")
    md += ["", "Lower is better for errors, Brier and log loss. A candidate must beat the market column out of sample before any promotion."]
    return "\n".join(md) + "\n"

def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--season", type=int, default=2027); a.add_argument("--start", default="2026-11-10")
    a.add_argument("--end", default="2026-11-20"); a.add_argument("--out", required=True); a.add_argument("--fixture")
    x = a.parse_args(argv)
    if x.fixture:
        rows = json.load(open(x.fixture))
    else:
        key = os.environ.get("CBBD_API_KEY")
        if not key: print("BLOCKED CBBD_API_KEY_ABSENT", file=sys.stderr); return 2
        ratings = get("/ratings/adjusted", key, season=x.season)
        games = json.loads(get("/games", key, season=x.season, startDateRange="2026-11-01T00:00:00Z", endDateRange=f"{x.end}T23:59:59Z"))
        boxes = json.loads(get("/games/teams", key, season=x.season, startDateRange="2026-11-01T00:00:00Z", endDateRange=f"{x.end}T23:59:59Z"))
        lines = json.loads(get("/lines", key, season=x.season, startDateRange="2026-11-01T00:00:00Z", endDateRange=f"{x.end}T23:59:59Z"))
        d0, d1 = dt.date.fromisoformat(x.start), dt.date.fromisoformat(x.end)
        days = [d0 + dt.timedelta(days=i) for i in range((d1 - d0).days + 1)]
        rows = walk(ratings, games, boxes, lines, x.season, days)
    if not rows: print("BLOCKED NO_ROWS", file=sys.stderr); return 2
    md = report(rows)
    Path(x.out).mkdir(parents=True, exist_ok=True)
    (Path(x.out) / "hca.md").write_text(md); (Path(x.out) / "rows.json").write_text(json.dumps(rows))
    print(md); return 0

if __name__ == "__main__":
    raise SystemExit(main())
