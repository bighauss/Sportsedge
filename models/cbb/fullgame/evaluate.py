"""Chronological evaluation of full-game engines + pricing on identical rows. RESEARCH ONLY.

Residual distributions for season S are fitted on the SAME engine's walk-forward residuals from
seasons < S only. Market rows use cached ESPN closing quotes (DraftKings preferred, else ESPN BET),
an UNADMITTED research source: evaluation at the close means CLV is 0 by construction and ROI is a
diagnostic, not a bet record. PAPER / 0u, NON_COUNTED.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from statistics import mean, stdev

from . import pricing as P
from . import espn_odds as O

ENGINES = ("RAW", "REG", "NATIVE_RECON", "SA", "FG1")
OLD = {"margin": P.Dist(0.0, 12.5), "total": P.Dist(0.0, 17.0), "team": P.Dist(0.0, 17.0 / math.sqrt(2))}


def load(wf_dir, tags, seasons):
    """tags: {engine: tag}; merges forecasts from several walk-forward runs per game."""
    out = {}
    for s in seasons:
        merged = {}
        for eng, tag in tags.items():
            p = Path(wf_dir) / f"wf_{tag}_{s}.json"
            if not p.exists():
                continue
            for r in json.loads(p.read_text()):
                m = merged.setdefault(r["game_id"], {**{k: v for k, v in r.items() if k != "f"}, "f": {}})
                if eng in r["f"]:
                    m["f"][eng] = r["f"][eng]
        out[s] = list(merged.values())
    return out


def residual_rows(rows, eng):
    res = []
    for r in rows:
        f = r["f"].get(eng)
        if not f:
            continue
        res.append({"phase": P.phase_of(r["n_home"], r["n_away"]),
                    "margin": (r["home_points"] - r["away_points"]) - f["margin"],
                    "total": (r["home_points"] + r["away_points"]) - f["total"],
                    "team": r["home_points"] - f["home_points"]})
        res.append({"phase": res[-1]["phase"], "margin": None, "total": None,
                    "team": r["away_points"] - f["away_points"]})
    return res


def fit_dists(by_season, eng, season):
    rows = [x for s, rs in by_season.items() if s < season for x in residual_rows(rs, eng)]
    if not rows:
        return None
    return {t: P.fit_phase_dists([x for x in rows if x[t] is not None], t) for t in ("margin", "total", "team")}


def point_metrics(rows, eng):
    m = [(r["home_points"] - r["away_points"]) - r["f"][eng]["margin"] for r in rows]
    t = [(r["home_points"] + r["away_points"]) - r["f"][eng]["total"] for r in rows]
    tp = [r["home_points"] - r["f"][eng]["home_points"] for r in rows] + \
         [r["away_points"] - r["f"][eng]["away_points"] for r in rows]
    f = lambda e: {"mae": mean(abs(x) for x in e), "rmse": math.sqrt(mean(x * x for x in e)), "bias": mean(e)}
    return {"n": len(rows), "margin": f(m), "total": f(t), "team_points": f(tp)}


def _bin_ece(pairs, bins=10):
    agg = [[0, 0.0, 0.0] for _ in range(bins)]
    for p, y in pairs:
        b = min(bins - 1, int(p * bins))
        agg[b][0] += 1; agg[b][1] += p; agg[b][2] += y
    n = len(pairs)
    ece = sum(a[0] / n * abs(a[1] / a[0] - a[2] / a[0]) for a in agg if a[0])
    table = [{"bin": i / bins, "n": a[0], "mean_p": a[1] / a[0], "rate": a[2] / a[0]} for i, a in enumerate(agg) if a[0]]
    return ece, table


def prob_metrics(pairs):
    """pairs: (p, y) with y in {0,1}."""
    eps = 1e-12
    ece, table = _bin_ece(pairs)
    return {"n": len(pairs), "brier": mean((p - y) ** 2 for p, y in pairs),
            "log_loss": mean(-math.log(max(eps, p if y else 1 - p)) for p, y in pairs),
            "ece": ece, "mean_p": mean(p for p, _ in pairs), "rate": mean(y for _, y in pairs),
            "calibration": table}


def fit_ml_recal(by_season, eng, season, first=2022):
    """Moneyline tail recalibration from the same engine's chronological ML pairs, seasons [first, season)."""
    pairs = []
    for s, rs in by_season.items():
        if not first <= s < season:
            continue
        d = fit_dists({k: v for k, v in by_season.items() if k >= first}, eng, s)
        if d is None:
            continue
        for r in rs:
            f = r["f"].get(eng)
            if f:
                p, _ = P.ml_probs(d["margin"][P.phase_of(r["n_home"], r["n_away"])], f["margin"])
                pairs.append((p, int(r["home_points"] > r["away_points"])))
    return P.fit_logit_recal(pairs) if len(pairs) >= 1000 else None


def market_rows(rows, quotes, eng, dists, pricing, ml_recal=None):
    """Yield priced market rows for a game set. pricing: 'OLD' (normal 12.5/17 constants, the RUN IT
    config) or 'NEW' (chronologically fitted phase t-distributions with location)."""
    out = []
    for r in rows:
        q, f = quotes.get(r["game_id"]), r["f"].get(eng)
        if not q or not f:
            continue
        ph = P.phase_of(r["n_home"], r["n_away"])
        D = OLD if pricing == "OLD" else {k: dists[k][ph] for k in ("margin", "total", "team")}
        margin, total = r["home_points"] - r["away_points"], r["home_points"] + r["away_points"]
        if q["spread_home"] is not None and q["spread_price_home"] and q["spread_price_away"]:
            L = q["spread_home"]
            a, push, b = P.line_probs(D["margin"], f["margin"], -L)
            y = None if margin + L == 0 else int(margin + L > 0)
            out.append(_mk(r, "spread", L, (q["spread_price_home"], q["spread_price_away"]), a, push, b, y,
                           f["margin"], -L, D["margin"].sd, ("home", "away")))
        if q["total"] is not None and q["over_price"] and q["under_price"]:
            T = q["total"]
            a, push, b = P.line_probs(D["total"], f["total"], T)
            y = None if total == T else int(total > T)
            out.append(_mk(r, "total", T, (q["over_price"], q["under_price"]), a, push, b, y,
                           f["total"], T, D["total"].sd, ("over", "under")))
        if q["ml_home"] and q["ml_away"]:
            if pricing == "OLD":
                a = 0.5 * math.erfc(-(f["margin"]) / (12.5 * math.sqrt(2))); b = 1 - a
            else:
                a, b = P.ml_probs(D["margin"], f["margin"])
                if ml_recal:
                    a = P.apply_logit_recal(a, ml_recal); b = 1 - a
            mk_margin = -q["spread_home"] if q["spread_home"] is not None else None
            out.append(_mk(r, "moneyline", None, (q["ml_home"], q["ml_away"]), a, 0.0, b, int(margin > 0),
                           f["margin"], mk_margin, D["margin"].sd, ("home", "away")))
    return out


def _mk(r, market, line, prices, a, push, b, y, mm, km, sd, sides):
    try:
        na, nb, over = P.no_vig(*prices)
    except ValueError:
        return None
    eva, evb = P.ev(a, push, prices[0]), P.ev(b, push, prices[1])
    best = 0 if eva >= evb else 1
    return {"game_id": r["game_id"], "season": r["season"], "date": r["date"], "market": market, "line": line,
            "prices": prices, "p": (a, b), "push": push, "novig": (na, nb), "overround": over, "y": y,
            "ev": (eva, evb), "best": best, "best_side": sides[best], "model_mean": mm, "market_mean": km,
            "sd": sd, "n_min": min(r["n_home"], r["n_away"])}


def summarize_market(mrows, threshold=0.30):
    mrows = [m for m in mrows if m]
    out = {}
    for mk in ("spread", "total", "moneyline", "all"):
        rs = [m for m in mrows if mk == "all" or m["market"] == mk]
        if not rs:
            continue
        best_ev = [m["ev"][m["best"]] for m in rs]
        # probability metrics on the side-A outcome, conditional on no push
        pairs = [(m["p"][0] / (1 - m["push"]), m["y"]) for m in rs if m["y"] is not None]
        mpairs = [(m["novig"][0], m["y"]) for m in rs if m["y"] is not None]
        bets = [m for m in rs if m["ev"][m["best"]] > 0 and m["y"] is not None]
        pnl = [(P.decimal_odds(m["prices"][m["best"]]) - 1) if (m["y"] == (1 - m["best"])) else -1.0 for m in bets]
        # pushes on bet rows refund: they were excluded above by y is None
        out[mk] = {"rows": len(rs), "ev_gt_30": sum(e > threshold for e in best_ev),
                   "ev_gt_10": sum(e > 0.10 for e in best_ev), "mean_best_ev": mean(best_ev),
                   "model": prob_metrics(pairs) if pairs else None, "market": prob_metrics(mpairs) if mpairs else None,
                   "flat_bets": len(bets), "flat_roi": mean(pnl) if pnl else None}
    return out


def bias_report(mrows):
    """Favourite/underdog and over/under bias of the MODEL probability (side-A conditional on no push)."""
    out = {}
    for mk in ("spread", "moneyline"):
        rs = [m for m in mrows if m and m["market"] == mk and m["y"] is not None]
        fav = []
        for m in rs:
            fav_side = 0 if m["novig"][0] >= m["novig"][1] else 1
            p = m["p"][fav_side] / (1 - m["push"])
            yy = m["y"] if fav_side == 0 else 1 - m["y"]
            fav.append((p, yy, m["novig"][fav_side]))
        if fav:
            d = [p - y for p, y, _ in fav]
            out[mk] = {"n": len(fav), "fav_mean_p_model": mean(p for p, _, _ in fav),
                       "fav_mean_p_novig": mean(k for _, _, k in fav), "fav_rate": mean(y for _, y, _ in fav),
                       "fav_bias_p_minus_rate": mean(d), "se": stdev(d) / math.sqrt(len(d))}
    rs = [m for m in mrows if m and m["market"] == "total" and m["y"] is not None]
    if rs:
        d = [m["p"][0] / (1 - m["push"]) - m["y"] for m in rs]
        out["total"] = {"n": len(rs), "over_mean_p_model": mean(m["p"][0] / (1 - m["push"]) for m in rs),
                        "over_rate": mean(m["y"] for m in rs), "over_bias_p_minus_rate": mean(d),
                        "se": stdev(d) / math.sqrt(len(d))}
    return out


def point_bias(rows, eng, quotes):
    """Mean residual oriented to the MARKET favourite (margin) and overall total residual, with SEs."""
    fav, tot = [], []
    for r in rows:
        f, q = r["f"].get(eng), quotes.get(r["game_id"])
        if not f:
            continue
        tot.append((r["home_points"] + r["away_points"]) - f["total"])
        if q and q["spread_home"]:
            s = 1 if q["spread_home"] < 0 else -1
            fav.append(s * ((r["home_points"] - r["away_points"]) - f["margin"]))
    g = lambda v: {"n": len(v), "mean": mean(v), "se": stdev(v) / math.sqrt(len(v))} if len(v) > 1 else None
    return {"favourite_margin_residual": g(fav), "total_residual": g(tot)}


# ---------------------------------------------------------------- chronological linear de-biasing
EARLY_N = 5


def _ols(x, y):
    mx, my = mean(x), mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx if sxx else 1.0
    return my - b * mx, b


def fit_recalibration(rows, eng, min_rows=300):
    """actual = a + b * forecast for margin and total, separately for early (< EARLY_N games) and later
    rows. Fitted ONLY on the rows passed in (callers pass strictly-earlier seasons)."""
    out = {}
    for grp in ("early", "late"):
        rs = [r for r in rows if eng in r["f"] and (min(r["n_home"], r["n_away"]) < EARLY_N) == (grp == "early")]
        if len(rs) < min_rows:
            return None
        out[grp] = {"margin": _ols([r["f"][eng]["margin"] for r in rs], [r["home_points"] - r["away_points"] for r in rs]),
                    "total": _ols([r["f"][eng]["total"] for r in rs], [r["home_points"] + r["away_points"] for r in rs]),
                    "n": len(rs)}
    return out


def apply_recalibration(f, coef, n_min):
    c = coef["early" if n_min < EARLY_N else "late"]
    m = c["margin"][0] + c["margin"][1] * f["margin"]
    t = c["total"][0] + c["total"][1] * f["total"]
    return {"home_points": (t + m) / 2, "away_points": (t - m) / 2, "margin": m, "total": t,
            "possessions": f.get("possessions")}


def add_recalibrated(by_season, eng, new=None, min_prior_seasons=2, min_rows=300):
    """Adds engine ``eng + 'C'`` to rows of season S using coefficients fitted on seasons < S only."""
    new = new or eng + "C"
    coefs = {}
    for s in sorted(by_season):
        prior = [r for p, rs in by_season.items() if p < s for r in rs]
        if len({p for p in by_season if p < s}) < min_prior_seasons:
            continue
        c = fit_recalibration(prior, eng, min_rows)
        if c is None:
            continue
        coefs[s] = c
        for r in by_season[s]:
            if eng in r["f"]:
                r["f"][new] = apply_recalibration(r["f"][eng], c, min(r["n_home"], r["n_away"]))
    return coefs


BANDS = ((100, 149), (150, 299), (300, 499), (500, 999), (1000, 100000))


def ml_dog_bands(mrows):
    """Underdog-side calibration by American price band: model p, no-vig p and realised win rate."""
    out = []
    for lo, hi in BANDS:
        rs = []
        for m in mrows:
            if not m or m["market"] != "moneyline":
                continue
            dog = 0 if m["novig"][0] < m["novig"][1] else 1
            pr = m["prices"][dog]
            if lo <= pr <= hi:
                rs.append((m["p"][dog], m["novig"][dog], m["y"] if dog == 0 else 1 - m["y"], m["ev"][dog]))
        if rs:
            out.append({"band": f"+{lo}..+{hi}", "n": len(rs), "mean_p_model": mean(r[0] for r in rs),
                        "mean_p_novig": mean(r[1] for r in rs), "win_rate": mean(r[2] for r in rs),
                        "se": math.sqrt(max(1e-12, mean(r[2] for r in rs) * (1 - mean(r[2] for r in rs)) / len(rs))),
                        "ev_gt_30": sum(r[3] > 0.30 for r in rs)})
    return out


def blended_ev_counts(mrows, w, threshold=0.30):
    """EV of the logit blend (model weight ``w``) at the quoted prices; flag counts only (no caps)."""
    n = gt = 0
    for m in mrows:
        if not m:
            continue
        pm = [m["p"][i] / (1 - m["push"]) for i in (0, 1)]
        z = w * _lg(pm[0]) + (1 - w) * _lg(m["novig"][0])
        pa = 1 / (1 + math.exp(-z))
        pb = 1 - pa
        evs = (P.ev(pa * (1 - m["push"]), m["push"], m["prices"][0]), P.ev(pb * (1 - m["push"]), m["push"], m["prices"][1]))
        n += 1; gt += max(evs) > threshold
    return {"rows": n, "ev_gt_30": gt}


def _lg(p):
    p = min(1 - 1e-9, max(1e-9, p)); return math.log(p / (1 - p))
