"""Ablation of rest/travel/neutral/early residual adjustments and tail/side calibration.

Protocol (fixed before this read of 2026-27):
  TUNE 2020-22          feature coefficients, longshot map, favourite bump (frozen)
  VALIDATION 2023-25    scored with frozen tune coefficients
  CONFIRMATORY_REUSE 2026-27  one additional read of the already-used window; not a fresh holdout

Every named variant is scored on identical rows, including those that fail to beat FG1 or the
market. ESPN / DK historical odds are an auxiliary comparator only, not execution prices or CLV.
PAPER / 0u / NON_COUNTED.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from . import adjustments as A
from . import context as C
from . import espn_odds as O
from . import evaluate as E
from . import pricing as P
from . import sdv_loader as L

TUNE = (2020, 2021, 2022)
VAL = (2023, 2024, 2025)
REUSE = (2026, 2027)
ALL = tuple(range(2020, 2028))
VARIANT_ENGINES = tuple(f"FG2_{k}" for k in A.VARIANTS)


def split_label(s):
    if s in TUNE:
        return "TUNE"
    if s in VAL:
        return "VALIDATION"
    return "CONFIRMATORY_REUSE"


def venue_lookup_from_parquets(root, *, before_season):
    root = Path(root)
    lookup = {}
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return lookup
    # Conservative season-lag proxy; no current/future season metadata.
    for s in range(2019, before_season):
        p = root / f"mbb_schedule_{s}.parquet"
        if not p.exists():
            continue
        t = pq.read_table(p, columns=["venue_id", "venue_full_name", "venue_address_city", "venue_address_state"])
        for vid, name, city, st in zip(t["venue_id"].to_pylist(), t["venue_full_name"].to_pylist(),
                                       t["venue_address_city"].to_pylist(), t["venue_address_state"].to_pylist()):
            if vid is None:
                continue
            key = str(int(vid))
            if key not in lookup and (city or st):
                lookup[key] = {"city": city, "state": st, "name": name}
    return lookup


def team_home_venue_map(games):
    counts = defaultdict(lambda: defaultdict(int))
    for g in games:
        if g.get("site") == "HOME_VERIFIED" and g.get("home_venue_id"):
            counts[str(g["home"])][str(g["home_venue_id"])] += 1
    return {t: max(v, key=v.get) for t, v in counts.items()}


def load_context(games_dir, sched_root):
    by_season, coverage = {}, {}
    prior = []
    for s in ALL:
        p = Path(games_dir) / f"games_{s}.csv"
        if not p.exists():
            continue
        rows = L.read_csv(p)
        lookup = venue_lookup_from_parquets(sched_root, before_season=s)
        homes = team_home_venue_map(prior)
        for g in rows:
            # Do not let an undated source field override the prior-season map.
            g["away_venue_id"] = None
            g["away_home_venue_id"] = homes.get(str(g["away"]))
            if g.get("site") != "HOME_VERIFIED":
                g["home_venue_id"] = homes.get(str(g["home"]))
            g["travel_metadata_basis"] = "PRIOR_SEASON_PROXY_NOT_AUTHENTICATED_PIT"
            g["away_home_known"] = bool(g["away_home_venue_id"])
        C.attach_context(rows, venue_lookup=lookup)
        by_season[s] = {g["game_id"]: g for g in rows}
        coverage[str(s)] = {"venues":len(lookup),"team_homes":len(homes)}
        # Reload original rows so context overrides cannot seed later home maps.
        prior.extend(L.read_csv(p))
    last = list(coverage.values())[-1] if coverage else {"venues":0,"team_homes":0}
    return by_season, {**last,"by_season":coverage,
                       "basis":"PRIOR_SEASON_PROXY_NOT_AUTHENTICATED_PIT"}


CTX_FIELDS = ("rest_diff", "home_rest", "away_rest", "home_b2b", "away_b2b", "home_opener",
              "away_opener", "is_neutral", "is_unverified", "is_home_verified",
              "home_miles", "away_miles", "home_moved", "away_moved")


def join_context(data, ctx):
    n = 0
    for s, rows in data.items():
        idx = ctx.get(s, {})
        for r in rows:
            g = idx.get(r["game_id"])
            if not g:
                continue
            for k in CTX_FIELDS:
                if k in g:
                    r[k] = g[k]
            n += 1
    return n


def apply_variants(data, fits):
    for rows in data.values():
        for r in rows:
            f = r["f"].get("FG1")
            if not f:
                continue
            for name, fit in fits.items():
                r["f"][f"FG2_{name}"] = A.apply_fit(r, fit, f)
            if "ctx" in fits:
                r["f"]["FG2"] = r["f"]["FG2_ctx"]


def _ml_pairs(rows, eng, dists):
    out = []
    for r in rows:
        f = r["f"].get(eng)
        if not f or not dists:
            continue
        dist = dists["margin"][P.phase_of(r["n_home"], r["n_away"])]
        p, _ = P.ml_probs(dist, f["margin"])
        out.append((p, int(r["home_points"] > r["away_points"])))
    return out


def _over_pairs_own_line(rows, eng, dists):
    """P(over) at the model's own total (push-aware integer/half handled by line_probs)."""
    out = []
    for r in rows:
        f = r["f"].get(eng)
        if not f or not dists:
            continue
        dist = dists["total"][P.phase_of(r["n_home"], r["n_away"])]
        line = round(f["total"] * 2) / 2.0
        po, push, pu = P.line_probs(dist, f["total"], line)
        actual = r["home_points"] + r["away_points"]
        if abs(actual - line) < 1e-9:
            continue
        out.append((po / (1 - push) if push < 1 else 0.5, int(actual > line)))
    return out


def postprocess_ml(mrows, longshot=None, fav_bump=None):
    """Adjust moneyline model probabilities only; leave quotes and outcomes untouched."""
    out = []
    for m in mrows:
        if not m:
            continue
        if m["market"] != "moneyline" or (not longshot and not fav_bump):
            out.append(m)
            continue
        m = dict(m)
        p0, p1 = m["p"]
        push = m["push"]
        # convert to no-push home win, adjust, restore
        if push >= 1:
            out.append(m)
            continue
        ph = p0 / (1 - push)
        if longshot:
            ph = A.apply_longshot(ph, longshot)
        if fav_bump:
            ph = A.apply_fav_bump(ph, fav_bump)
        m["p"] = (ph * (1 - push), (1 - ph) * (1 - push))
        out.append(m)
    return out


def metrics_block(mrows):
    return {"summary": E.summarize_market(mrows), "bias": E.bias_report(mrows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", required=True)
    ap.add_argument("--sched", required=True)
    ap.add_argument("--wf", required=True)
    ap.add_argument("--odds", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = E.load(a.wf, {"FG1": "fg1t"}, list(ALL))
    ctx, census = load_context(a.games, a.sched)
    joined = join_context(data, ctx)

    tune_rows = [r for s in TUNE for r in data[s] if "FG1" in r["f"]]
    fits = {}
    fit_report = {}
    for name, feat in A.VARIANTS.items():
        fm = A.fit_variant(tune_rows, feat, "margin", lam=1.0)
        ft = A.fit_variant(tune_rows, feat, "total", lam=1.0)
        fits[name] = {"margin": fm, "total": ft}
        fit_report[name] = {
            "margin": None if not fm else {"names": fm["names"], "coef": fm["coef"], "n": fm["n"]},
            "total": None if not ft else {"names": ft["names"], "coef": ft["coef"], "n": ft["n"]},
        }
    apply_variants(data, fits)
    recal = E.add_recalibrated(data, "FG2", new="FG2C")

    # Residual SDs / dists on strictly earlier seasons, per engine, for ML pairs on TUNE
    # and for market scoring later.
    engines = ("FG1", "FG2", "FG2C") + VARIANT_ENGINES
    dists = {s: {e: E.fit_dists(data, e, s) for e in engines} for s in ALL}

    tune_ml = []
    for s in TUNE:
        if dists[s].get("FG2"):
            tune_ml.extend(_ml_pairs([r for r in data[s] if "FG2" in r["f"]], "FG2", dists[s]["FG2"]))
    longshot = A.fit_longshot(tune_ml, edges=(0.05, 0.08, 0.12))
    fav_bump = A.fit_fav_bump(tune_ml)
    tune_over = []
    for s in TUNE:
        if dists[s].get("FG2"):
            tune_over.extend(_over_pairs_own_line([r for r in data[s] if "FG2" in r["f"]], "FG2", dists[s]["FG2"]))
    over_shift = A.fit_over_shift(tune_over)

    # Point metrics on identical FG1 rows
    point = {}
    ident_counts = {}
    point_engines = ("FG1",) + VARIANT_ENGINES + ("FG2", "FG2C")
    for s in ALL:
        rows = [r for r in data[s] if "FG1" in r["f"] and "FG2" in r["f"]]
        ident_counts[s] = len(rows)
        point[s] = {"split": split_label(s)}
        for e in point_engines:
            have = [r for r in rows if e in r["f"]]
            if have:
                point[s][e] = E.point_metrics(have, e)

    # Odds (auxiliary comparator)
    quotes, census_odds = {}, {}
    for s in range(2023, 2028):
        q, c = O.load_dir(a.odds, [r["game_id"] for r in data[s]])
        quotes.update(q)
        census_odds[s] = c

    market = {}
    bias = {}
    point_bias = {}
    for s in range(2023, 2028):
        rows = [r for r in data[s] if "FG1" in r["f"] and "FG2" in r["f"] and r["game_id"] in quotes]
        market[s] = {"split": split_label(s)}
        bias[s] = {}
        point_bias[s] = {}
        for e in ("FG1", "FG1C", "FG2", "FG2C") + VARIANT_ENGINES:
            if e == "FG1C":
                # FG1C may already be absent; add it if we can
                continue
            d = dists[s].get(e)
            if not d:
                continue
            mr = [m for m in E.market_rows(rows, quotes, e, d, "NEW") if m]
            market[s][e] = E.summarize_market(mr)
            bias[s][e] = E.bias_report(mr)
            point_bias[s][e] = E.point_bias(rows, e, quotes)
        # FG1C from existing chronological helper if present on rows; otherwise add now
        if any("FG1C" in r["f"] for r in data[s]):
            pass
        # Pricing-only variants on FG2C
        d2 = dists[s].get("FG2C") or dists[s].get("FG2")
        e2 = "FG2C" if dists[s].get("FG2C") else "FG2"
        if d2:
            base = [m for m in E.market_rows(rows, quotes, e2, d2, "NEW") if m]
            for tag, ls, fb in (("FG2C_longshot", longshot, None),
                                ("FG2C_favbump", None, fav_bump),
                                ("FG2C_longshot_favbump", longshot, fav_bump)):
                adj = postprocess_ml(base, longshot=ls, fav_bump=fb)
                market[s][tag] = E.summarize_market(adj)
                bias[s][tag] = E.bias_report(adj)

    # Add FG1C point + market by computing it here (same protocol as run_eval)
    E.add_recalibrated(data, "FG1", new="FG1C")
    for s in ALL:
        rows = [r for r in data[s] if "FG1" in r["f"] and "FG2" in r["f"] and "FG1C" in r["f"]]
        if rows:
            point[s]["FG1C"] = E.point_metrics(rows, "FG1C")
    dists_fg1c = {s: E.fit_dists(data, "FG1C", s) for s in range(2023, 2028)}
    for s in range(2023, 2028):
        rows = [r for r in data[s] if "FG1C" in r["f"] and "FG2" in r["f"] and r["game_id"] in quotes]
        d = dists_fg1c[s]
        if not d:
            continue
        mr = [m for m in E.market_rows(rows, quotes, "FG1C", d, "NEW") if m]
        market[s]["FG1C"] = E.summarize_market(mr)
        bias[s]["FG1C"] = E.bias_report(mr)
        point_bias[s]["FG1C"] = E.point_bias(rows, "FG1C", quotes)

    rep = {
        "status": "RESEARCH_ONLY_PAPER_0U_NON_COUNTED",
        "protocol": {
            "tune": list(TUNE), "validation": list(VAL),
            "confirmatory_reuse": list(REUSE),
            "reuse_note": "2026-27 was already used for the first confirmatory read of FG1/FG1C; this is a second read of the same window and is not a fresh holdout.",
            "odds": "ESPN core-API historical odds (DK / ESPN BET) are an auxiliary comparator only, not execution prices or CLV evidence.",
        },
        "context_census": census, "joined_rows": joined, "ident_counts": ident_counts,
        "fits_tune_2020_2022": fit_report,
        "longshot_tune": longshot, "fav_bump_tune": fav_bump, "over_shift_own_line_tune": over_shift,
        "fg2c_recal_seasons": {str(s): True for s in recal},
        "gaps": {
            "player_availability": "No legitimate point-in-time public injury/availability source is shipped with this challenger. The production gate already blocks a missing injuries role. Documented as a gap; not filled with a leaky proxy.",
            "returning_minutes": "Player box scores exist on the box for some seasons, but there is no dated preseason roster or transfer snapshot that would let returning minutes be computed without using current-season appearances (leakage). Early-season ratings continue to use the previous-season carry prior only.",
            "travel_proxy": "Travel miles use city/state labels from sportsdataverse schedules and region centroids (same-city 0, same-state 120, else haversine of centroids). Not surveyed road distance.",
        },
        "point": point, "market": market, "bias": bias, "point_bias": point_bias,
        "odds_census": census_odds, "tune_ml_pairs": len(tune_ml), "tune_over_pairs": len(tune_over),
    }
    (out_dir / "improve_summary.json").write_text(json.dumps(rep, indent=2))
    (out_dir / "improve_tables.md").write_text(render(rep))
    print("wrote", out_dir, "tune_rows", len(tune_rows), "joined", joined)
    return 0


def _brier(block, market):
    if not block:
        return None
    mk = block.get(market) or (block.get("summary") or {}).get(market) if "summary" in block else block.get(market)
    # summarize_market returns {spread:{model:{brier}, market:{brier}, rows}, ...}
    if not mk:
        return None
    return {"n": mk.get("rows") or (mk.get("model") or {}).get("n"),
            "model": (mk.get("model") or {}).get("brier"),
            "market": (mk.get("market") or {}).get("brier")}


def render(rep):
    L = []
    L.append("# Full-game improvement ablations (PAPER / 0u, NON_COUNTED)\n")
    L.append("Tune 2020-22 (frozen). Validation 2023-25. 2026-27 is a CONFIRMATORY REUSE of an already-used window, not a fresh holdout.\n")
    L.append("ESPN historical odds are an auxiliary comparator only, not execution prices or CLV.\n")
    L.append("## Gaps\n")
    for k, v in rep["gaps"].items():
        L.append(f"- **{k}:** {v}")
    L.append("\n## Tune-window coefficients (2020-22)\n")
    for name, fit in rep["fits_tune_2020_2022"].items():
        L.append(f"### {name}")
        for tgt in ("margin", "total"):
            b = fit[tgt]
            if not b:
                L.append(f"- {tgt}: fit failed")
                continue
            coefs = ", ".join(f"{n}={c:.4f}" for n, c in zip(b["names"], b["coef"]))
            L.append(f"- {tgt} (n={b['n']}): {coefs}")
    ls, fb, ov = rep["longshot_tune"], rep["fav_bump_tune"], rep["over_shift_own_line_tune"]
    L.append(f"\n- favourite bump delta={fb['delta']:.4f} (n={fb['n']})")
    L.append(f"- over-shift at model's own total delta={ov['delta']:.4f} (n={ov['n']})")
    L.append(f"- longshot primary={ls.get('primary')} edges={json.dumps(ls.get('edges'))}")
    L.append("\n## Point metrics on identical FG1 rows (actual − forecast)\n")
    L.append("| season | split | engine | n | margin MAE | margin RMSE | margin bias | total MAE | total RMSE | total bias |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for s in ALL:
        blk = rep["point"].get(s, {})
        split = blk.get("split", "")
        for e, m in blk.items():
            if e == "split" or not isinstance(m, dict) or "margin" not in m:
                continue
            L.append(
                f"| {s} | {split} | {e} | {m['n']} | "
                f"{m['margin']['mae']:.3f} | {m['margin']['rmse']:.3f} | {m['margin']['bias']:.3f} | "
                f"{m['total']['mae']:.3f} | {m['total']['rmse']:.3f} | {m['total']['bias']:.3f} |"
            )
    L.append("\n## Market Brier (auxiliary ESPN close quotes) vs market Brier\n")
    L.append("| season | split | engine | market | n | model Brier | market Brier | delta (model−market) |")
    L.append("|---|---|---|---|---:|---:|---:|---:|")
    for s in range(2023, 2028):
        blk = rep["market"].get(s, {})
        split = blk.get("split", "")
        for e, sm in blk.items():
            if e == "split" or not isinstance(sm, dict):
                continue
            for mk in ("spread", "total", "moneyline"):
                sub = sm.get(mk) or {}
                model = (sub.get("model") or {}).get("brier")
                market = (sub.get("market") or {}).get("brier")
                n = sub.get("rows")
                if model is None or market is None:
                    continue
                L.append(f"| {s} | {split} | {e} | {mk} | {n} | {model:.4f} | {market:.4f} | {model-market:+.4f} |")
    L.append("\n## Side bias (model p − realised rate) at market lines (auxiliary)\n")
    L.append("| season | split | engine | side | n | model p | rate | bias | SE |")
    L.append("|---|---|---|---|---:|---:|---:|---:|---:|")
    for s in range(2023, 2028):
        split = split_label(s)
        for e, b in (rep["bias"].get(s) or {}).items():
            if not isinstance(b, dict):
                continue
            if "moneyline" in b:
                x = b["moneyline"]
                L.append(f"| {s} | {split} | {e} | ML favourite | {x['n']} | {x['fav_mean_p_model']:.4f} | {x['fav_rate']:.4f} | {x['fav_bias_p_minus_rate']:+.4f} | {x['se']:.4f} |")
            if "total" in b:
                x = b["total"]
                L.append(f"| {s} | {split} | {e} | over | {x['n']} | {x['over_mean_p_model']:.4f} | {x['over_rate']:.4f} | {x['over_bias_p_minus_rate']:+.4f} | {x['se']:.4f} |")
            if "spread" in b:
                x = b["spread"]
                L.append(f"| {s} | {split} | {e} | spread favourite | {x['n']} | {x['fav_mean_p_model']:.4f} | {x['fav_rate']:.4f} | {x['fav_bias_p_minus_rate']:+.4f} | {x['se']:.4f} |")
    L.append("\n## Notes\n")
    L.append("- FG1 already contains opponent-adjusted offensive and defensive efficiency and a recency-weighted preseason carry. FG2_* add frozen residual adjustments on top of FG1.")
    L.append("- FG2C is chronological linear de-bias of FG2 (seasons < S), the same protocol as FG1C.")
    L.append("- Longshot and favourite-bump maps are fit on 2020-22 model probability vs outcome only, then frozen.")
    L.append("- Variants that do not improve a metric are kept in the tables; nothing is cherry-picked.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
