"""Root-cause diagnosis of the Nov 24, 2026 RUN IT card's inflated paper EV. RESEARCH ONLY.

Inputs: the committed card markdown (outputs/cbb/card_2026-11-24_*.md), the walk-forward forecasts for
season 2027 (FG1 + chronological recalibration -> FG1C, strictly prior dates), fitted phase
distributions (seasons < 2027), the public ESPN schedule (finals, for outcomes) and cached ESPN/DK
closing odds. The card's own price is re-priced; nothing is re-captured.

Card projection recovery: the card prices with constant SDs (margin 12.5, total 17, normal), so the
card's projected home margin is recovered exactly from its moneyline probability
(margin = 12.5 * Phi^-1(p_home)) and its total from the total row (line + 17 * Phi^-1(p_over)).
"""
from __future__ import annotations
import json
import math
import re
import unicodedata
from statistics import NormalDist, mean, median

from . import evaluate as E
from . import pricing as P
from . import espn_odds as O

N = NormalDist()


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", "and").replace("state", "st").replace("saint", "st")
    return re.sub(r"[^a-z0-9]", "", s)


def parse_card(path):
    L = open(path).read().split("\n")
    i = next(k for k, l in enumerate(L) if l.startswith("## Priced markets"))
    rows = []
    for l in L[i + 4:]:
        if not l.startswith("| "):
            break
        c = [x.strip() for x in l.strip("|").split("|")]
        rows.append(dict(game=c[1], tip=c[2], market=c[3], side=c[4], line=float(c[5]) if c[5] else None,
                         price=int(c[6]), p_model=float(c[7]), p_novig=float(c[8]), ev=float(c[9].rstrip("%")) / 100))
    excluded = {}
    for l in L:
        m = re.match(r"- (.+) spread ([-+]?[\d.]+): model-best (\w+), paper EV ([-+]?[\d.]+)%", l)
        if m:
            excluded[m.group(1)] = float(m.group(2))
    return rows, excluded


def card_projection(rows):
    g = {}
    for r in rows:
        d = g.setdefault(r["game"], {})
        p = min(1 - 1e-9, max(1e-9, r["p_model"]))
        if r["market"] == "moneyline":
            ph = p if r["side"] == "home" else 1 - p
            d["card_margin"] = 12.5 * N.inv_cdf(ph)
        elif r["market"] == "total":
            d["card_total"] = r["line"] + (17 * N.inv_cdf(p) if r["side"] == "over" else -17 * N.inv_cdf(p))
            d["market_total"] = r["line"]
        elif r["market"] == "spread":
            home_line = r["line"] if r["side"] == "home" else -r["line"]
            d["market_margin"] = -home_line
            d.setdefault("card_margin_from_spread", (-home_line + 12.5 * N.inv_cdf(p)) if r["side"] == "home"
                         else (-home_line - 12.5 * N.inv_cdf(p)))
    return g


def run(card_path, wf_dir, odds_dir, sched_parquet, blend_weights):
    import pandas as pd  # research-only
    rows, excluded = parse_card(card_path)
    data = E.load(wf_dir, {"FG1": "fg1t"}, list(range(2020, 2028)))
    E.add_recalibrated(data, "FG1")
    dists = E.fit_dists({k: v for k, v in data.items() if k >= 2022}, "FG1C", 2027)
    s = pd.read_parquet(sched_parquet)
    s = s[s.date.astype(str).between("2026-11-24T11:00Z", "2026-11-25T11:00Z")]
    loc = {}
    for r in s.itertuples():
        loc[(norm(r.away_location), norm(r.home_location))] = str(r.game_id)
    wf = {r["game_id"]: r for r in data[2027]}
    games = card_projection(rows)
    for g, sp in excluded.items():
        games.setdefault(g, {})["market_margin"] = -sp
    q, _ = O.load_dir(odds_dir, list(loc.values()))
    out, unmatched = [], []
    for g, d in games.items():
        away, home = [x.strip() for x in g.split(" @ ")]
        gid = loc.get((norm(away), norm(home))); flip = 1
        if gid is None and (norm(home), norm(away)) in loc:   # neutral-site games listed the other way round
            gid, flip = loc[(norm(home), norm(away))], -1
        r = wf.get(gid)
        if not gid or not r or "FG1C" not in r["f"]:
            unmatched.append({"game": g, "reason": "NO_ESPN_MATCH" if not gid else "NO_D1_FORECAST"})
            continue
        f = r["f"]["FG1C"]
        d.update(game=g, game_id=gid, espn_orientation_flipped=flip == -1,
                 actual_margin=flip * (r["home_points"] - r["away_points"]),
                 actual_total=r["home_points"] + r["away_points"], fg1c_margin=flip * f["margin"], fg1c_total=f["total"],
                 n_min=min(r["n_home"], r["n_away"]), site=r["site"],
                 close_margin=-flip * q[gid]["spread_home"] if gid in q and q[gid]["spread_home"] is not None else None,
                 close_total=q[gid]["total"] if gid in q else None)
        out.append(d)
    # re-price every card row with the challenger (independent) and the validation-selected blend
    reprice = []
    for r in rows:
        d = next((x for x in out if x["game"] == r["game"]), None)
        if d is None:
            continue
        ph = P.phase_of(d["n_min"], d["n_min"])
        if r["market"] == "moneyline":
            pa, pb = P.ml_probs(dists["margin"][ph], d["fg1c_margin"]); push = 0.0
            p_side = pa if r["side"] == "home" else pb
        elif r["market"] == "spread":
            hl = r["line"] if r["side"] == "home" else -r["line"]
            a, push, b = P.line_probs(dists["margin"][ph], d["fg1c_margin"], -hl)
            p_side = a if r["side"] == "home" else b
        else:
            a, push, b = P.line_probs(dists["total"][ph], d["fg1c_total"], r["line"])
            p_side = a if r["side"] == "over" else b
        ev_ind = P.ev(p_side, push, r["price"])
        w = blend_weights[{"moneyline": "moneyline", "spread": "spread", "total": "total"}[r["market"]]]
        pc = p_side / (1 - push) if push < 1 else p_side
        z = w * _logit(pc) + (1 - w) * _logit(r["p_novig"])
        p_bl = (1 / (1 + math.exp(-z))) * (1 - push)
        reprice.append({**r, "p_fg1c": p_side, "ev_fg1c_independent": ev_ind, "p_blend": p_bl,
                        "ev_blend": P.ev(p_bl, push, r["price"]), "blend_weight_model": w,
                        "audit": P.ev_audit({"ev": r["ev"], "price": r["price"], "p_model": r["p_model"], "p_novig": r["p_novig"]})})
    return out, unmatched, reprice


def _logit(p):
    p = min(1 - 1e-9, max(1e-9, p)); return math.log(p / (1 - p))


def summarize(out, reprice):
    def st(v):
        v = [x for x in v if x is not None]
        return {"n": len(v), "mean": mean(v), "median": median(v), "mean_abs": mean(abs(x) for x in v)} if v else None
    mm = [d for d in out if "card_margin" in d and d.get("market_margin") is not None]
    res = {
        "games_matched": len(out),
        "card_minus_market_margin": st([d["card_margin"] - d["market_margin"] for d in mm]),
        "fg1c_minus_market_margin": st([d["fg1c_margin"] - d["market_margin"] for d in mm]),
        "card_margin_error_vs_actual": st([d["actual_margin"] - d["card_margin"] for d in mm]),
        "fg1c_margin_error_vs_actual": st([d["actual_margin"] - d["fg1c_margin"] for d in mm]),
        "market_margin_error_vs_actual": st([d["actual_margin"] - d["market_margin"] for d in mm]),
        "card_total_error_vs_actual": st([d["actual_total"] - d["card_total"] for d in out if "card_total" in d]),
        "fg1c_total_error_vs_actual": st([d["actual_total"] - d["fg1c_total"] for d in out if "card_total" in d]),
        "market_total_error_vs_actual": st([d["actual_total"] - d["market_total"] for d in out if "card_total" in d]),
    }
    if mm:
        x = [d["market_margin"] for d in mm]; y = [d["card_margin"] for d in mm]
        a, b = E._ols(x, y)
        res["card_margin_on_market_margin_ols"] = {"intercept": a, "slope": b, "n": len(mm)}
        big = [d for d in mm if abs(d["market_margin"]) >= 15]
        res["big_favourites_abs_market_ge_15"] = {
            "n": len(big), "card_margin_mean": mean(abs(d["card_margin"]) for d in big) if big else None,
            "market_margin_mean": mean(abs(d["market_margin"]) for d in big) if big else None,
            "actual_margin_mean_fav_oriented": mean(d["actual_margin"] * (1 if d["market_margin"] > 0 else -1) for d in big) if big else None,
            "fg1c_margin_mean": mean(abs(d["fg1c_margin"]) for d in big) if big else None}
    res["rows_repriced"] = len(reprice)
    res["ev_gt_30_card"] = sum(r["ev"] > 0.30 for r in reprice)
    res["ev_gt_30_fg1c_independent"] = sum(r["ev_fg1c_independent"] > 0.30 for r in reprice)
    res["ev_gt_30_blend_selected"] = sum(r["ev_blend"] > 0.30 for r in reprice)
    res["ev_gt_10_card"] = sum(r["ev"] > 0.10 for r in reprice)
    res["ev_gt_10_fg1c_independent"] = sum(r["ev_fg1c_independent"] > 0.10 for r in reprice)
    res["ev_gt_10_blend_selected"] = sum(r["ev_blend"] > 0.10 for r in reprice)
    return res
