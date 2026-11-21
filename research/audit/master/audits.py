"""P1 audit modules. All READ-ONLY: they never modify a model or a historical row.

Canonical prediction row (dict / CSV column), extra keys allowed:
  pred_id, game_id, sport, market, side, player, team, opponent,
  model_prob, odds, book, odds_ts, pred_ts, kickoff_ts,
  close_odds, close_other_odds, result (W/L/P/V), projection, actual, line,
  model_version, rule_version, inputs (list of {name, value, ts, source})
Timestamps: ISO-8601 with offset, e.g. 2026-11-16T12:00:00-06:00.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Sequence

from . import stats
from .odds import implied_prob, clv, ev_per_unit

# ---------------------------------------------------------------- helpers

def ts(x):
    if x in (None, ""):
        return None
    if isinstance(x, datetime):
        return x
    return datetime.fromisoformat(str(x).replace("Z", "+00:00"))


def finding(code, severity, row=None, detail=""):
    return {"code": code, "severity": severity, "pred_id": (row or {}).get("pred_id"), "detail": detail}


SEV = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# ---------------------------------------------------------------- P1.2 leakage

POSTGAME_FIELDS = {"close_odds", "close_other_odds", "result", "actual", "final_score",
                   "closing_line", "box_score"}


def leakage_audit(rows: Sequence[dict]) -> list[dict]:
    """Rusty T2#1. Every input must be timestamped at/before pred_ts; pred_ts before kickoff."""
    out = []
    for r in rows:
        p, k = ts(r.get("pred_ts")), ts(r.get("kickoff_ts"))
        if p is None:
            out.append(finding("NO_PRED_TS", "CRITICAL", r, "prediction has no timestamp"))
            continue
        if k and p >= k:
            out.append(finding("PRED_AFTER_KICKOFF", "CRITICAL", r, f"{p} >= {k}"))
        o = ts(r.get("odds_ts"))
        if o is None:
            out.append(finding("NO_ODDS_TS", "HIGH", r, "odds price has no capture time"))
        elif o > p:
            out.append(finding("ODDS_AFTER_PRED", "CRITICAL", r, f"odds {o} > pred {p}"))
        for inp in r.get("inputs") or []:
            name = inp.get("name", "?")
            if name in POSTGAME_FIELDS:
                out.append(finding("POSTGAME_FIELD_AS_INPUT", "CRITICAL", r, name))
            it = ts(inp.get("ts"))
            if it is None:
                out.append(finding("INPUT_NO_TS", "HIGH", r, name))
            elif it > p:
                out.append(finding("FUTURE_INPUT", "CRITICAL", r, f"{name} @ {it} > {p}"))
    return out


def assert_no_leakage(rows):
    """Use inside tests / CI: raises if any CRITICAL leakage finding exists."""
    bad = [f for f in leakage_audit(rows) if f["severity"] == "CRITICAL"]
    if bad:
        raise AssertionError(f"{len(bad)} leakage violations, first: {bad[0]}")


def point_in_time(history: Sequence[dict], as_of, ts_key: str = "ts") -> list[dict]:
    """Filter helper for training/backtests: only rows known at as_of."""
    a = ts(as_of)
    return [h for h in history if ts(h[ts_key]) is not None and ts(h[ts_key]) <= a]

# ---------------------------------------------------------------- data quality (Rusty T1#2)

def data_quality(rows: Sequence[dict], required=("game_id", "market", "side", "model_prob", "odds"),
                 id_fields=("player", "team")) -> dict:
    """Report every issue; NEVER silently deletes. Returns cleaned copy + corrections log."""
    issues, corrections, cleaned = [], [], []
    seen = Counter((r.get("game_id"), r.get("market"), r.get("side"), r.get("player"), r.get("book"))
                   for r in rows)
    name_variants: dict[str, set] = {}
    for r in rows:
        c = dict(r)
        for f in required:
            if c.get(f) in (None, ""):
                issues.append(finding("MISSING_" + f.upper(), "HIGH", r))
        key = (r.get("game_id"), r.get("market"), r.get("side"), r.get("player"), r.get("book"))
        if seen[key] > 1:
            issues.append(finding("DUPLICATE", "MEDIUM", r, str(key)))
        for f in id_fields:
            v = c.get(f)
            if isinstance(v, str) and v != v.strip():
                corrections.append({"pred_id": r.get("pred_id"), "field": f, "from": v, "to": v.strip()})
                c[f] = v.strip()
            if isinstance(c.get(f), str):
                name_variants.setdefault(c[f].lower().replace(".", "").replace(" ", ""), set()).add(c[f])
        try:
            mp = float(c.get("model_prob"))
            if not 0 < mp < 1:
                issues.append(finding("PROB_OUT_OF_RANGE", "CRITICAL", r, str(mp)))
            elif mp > 0.9 or mp < 0.02:
                issues.append(finding("EXTREME_PROB", "MEDIUM", r, str(mp)))
        except (TypeError, ValueError):
            issues.append(finding("PROB_NOT_NUMERIC", "HIGH", r))
        try:
            o = float(c.get("odds"))
            if -100 < o < 100:
                issues.append(finding("BAD_ODDS", "HIGH", r, str(o)))
        except (TypeError, ValueError):
            pass
        k = c.get("kickoff_ts")
        try:
            if k and not (2000 <= ts(k).year <= 2100):
                issues.append(finding("BAD_DATE", "HIGH", r, str(k)))
        except ValueError:
            issues.append(finding("UNPARSEABLE_DATE", "HIGH", r, str(k)))
        cleaned.append(c)
    for norm, variants in name_variants.items():
        if len(variants) > 1:
            issues.append(finding("INCONSISTENT_ID", "MEDIUM", None, f"{sorted(variants)}"))
    return {"n_rows_in": len(rows), "n_rows_out": len(cleaned), "issues": issues,
            "corrections": corrections, "cleaned": cleaned}

# ---------------------------------------------------------------- P1.1 largest-edge stress test

def edge_of(r) -> float:
    return float(r["model_prob"]) - implied_prob(float(r["odds"]))


def largest_edge_stress(rows: Sequence[dict], top: int = 20, stale_minutes: float = 60,
                        max_edge: float = 0.10, max_ratio: float = 1.5) -> dict:
    """PlusEVAnalytics + Rusty 'Largest Edges Auditor'. Diagnose only; proposes, never fixes."""
    pregame = [r for r in rows if r.get("pred_ts") and r.get("odds") not in (None, "")]
    ranked = sorted(pregame, key=edge_of, reverse=True)[:top]
    leak = {f["pred_id"]: f for f in leakage_audit(ranked)}
    items, codes = [], Counter()
    for r in ranked:
        mp, ip = float(r["model_prob"]), implied_prob(float(r["odds"]))
        flags = []
        if r.get("pred_id") in leak:
            flags.append("LEAKAGE:" + leak[r["pred_id"]]["code"])
        if mp - ip > max_edge:
            flags.append("EDGE_GT_%d%%" % round(max_edge * 100))
        if ip > 0 and mp / ip > max_ratio:
            flags.append("PROB_RATIO_GT_%.1f" % max_ratio)
        o, p = ts(r.get("odds_ts")), ts(r.get("pred_ts"))
        if o and p and (p - o).total_seconds() / 60 > stale_minutes:
            flags.append("STALE_ODDS")
        if not r.get("inputs"):
            flags.append("NO_INPUT_LINEAGE")
        missing = [i["name"] for i in r.get("inputs") or [] if i.get("value") in (None, "")]
        if missing:
            flags.append("MISSING_INPUTS:" + ",".join(missing))
        if r.get("player") and not r.get("player_id"):
            flags.append("UNMAPPED_PLAYER_ID")
        drivers = sorted((i for i in r.get("inputs") or [] if isinstance(i.get("contribution"), (int, float))),
                         key=lambda i: -abs(i["contribution"]))[:3]
        codes.update(f.split(":")[0] for f in flags)
        items.append({"pred_id": r.get("pred_id"), "market": r.get("market"), "side": r.get("side"),
                      "model_prob": mp, "odds": r["odds"], "implied": ip, "edge": mp - ip,
                      "drivers": [d["name"] for d in drivers], "result": r.get("result"),
                      "flags": flags,
                      "status": "BLOCKED" if any(f.startswith("LEAKAGE") for f in flags)
                      else "FLAGGED" if flags else "PLAUSIBLE"})
    graded = [i for i in items if i["result"] in ("W", "L")]
    exp = sum(i["model_prob"] for i in graded)
    act = sum(i["result"] == "W" for i in graded)
    patterns = [f"{c} in {n}/{len(items)}" for c, n in codes.most_common() if n >= max(2, len(items) // 4)]
    by_mkt = Counter(i["market"] for i in items)
    if items and by_mkt.most_common(1)[0][1] / len(items) >= .5:
        patterns.append(f"CONCENTRATED_MARKET {by_mkt.most_common(1)[0]}")
    return {"top": items, "expected_wins": exp, "actual_wins": act, "n_graded": len(graded),
            "overconfidence_signal": (exp - act) if graded else None, "patterns": patterns,
            "converged": all(i["status"] == "PLAUSIBLE" for i in items),
            "note": "A win does not validate a projection. Fixes go to proposals, then unseen-data test."}

# ---------------------------------------------------------------- P1.6 bias hunter / improvement analyst

def bias_breakdown(rows: Sequence[dict], dims=("player", "team", "opponent", "market", "side", "edge_bucket",
                                               "proj_bucket", "month"), min_n: int = 30) -> dict:
    """Rusty T1#6/T2#5. Mean error (projection-actual) and prob residual by group, with 95% CI."""
    enriched = []
    for r in rows:
        e = dict(r)
        if r.get("odds") not in (None, "") and r.get("model_prob") not in (None, ""):
            e["edge_bucket"] = f"{int(edge_of(r) * 100 // 2 * 2)}-{int(edge_of(r) * 100 // 2 * 2) + 2}%"
        if r.get("projection") not in (None, "") and r.get("line") not in (None, ""):
            d = float(r["projection"]) - float(r["line"])
            e["proj_bucket"] = f"{'+' if d >= 0 else ''}{round(d)}"
        if r.get("kickoff_ts"):
            e["month"] = str(r["kickoff_ts"])[:7]
        enriched.append(e)
    out = {}
    for dim in dims:
        res = []
        for g, rs in stats.group_by(enriched, dim).items():
            if g is None:
                continue
            errs = [float(x["projection"]) - float(x["actual"]) for x in rs
                    if x.get("projection") not in (None, "") and x.get("actual") not in (None, "")]
            pr = [(float(x["model_prob"]), x["result"] == "W") for x in rs if x.get("result") in ("W", "L")]
            row = {"group": g, "n": len(rs)}
            if errs:
                m = sum(errs) / len(errs)
                sd = (sum((v - m) ** 2 for v in errs) / max(1, len(errs) - 1)) ** .5
                se = sd / len(errs) ** .5 if len(errs) > 1 else float("inf")
                row.update(mean_error=m, ci=(m - 1.96 * se, m + 1.96 * se),
                           direction="OVER_PROJECTS" if m - 1.96 * se > 0 else
                           "UNDER_PROJECTS" if m + 1.96 * se < 0 else "NO_SIGNAL")
            if pr:
                resid = sum(p for p, _ in pr) / len(pr) - sum(w for _, w in pr) / len(pr)
                row.update(prob_residual=resid, n_graded=len(pr))
            row["repeatable"] = len(rs) >= min_n and row.get("direction") not in (None, "NO_SIGNAL")
            res.append(row)
        out[dim] = sorted(res, key=lambda x: -x["n"])
    return out


def market_disagreement(rows: Sequence[dict], edges=(0, .02, .04, .06, .08, .10, .15, 1)) -> list[dict]:
    """Rusty standalone: do bigger model-vs-market gaps do worse? ROI at original odds."""
    out = []
    for lo, hi in zip(edges, edges[1:]):
        rs = [r for r in rows if r.get("result") in ("W", "L", "P") and lo <= abs(edge_of(r)) < hi]
        if not rs:
            continue
        perf = stats.performance(rs)
        out.append({"gap": f"{lo:.0%}-{hi:.0%}", "n": len(rs),
                    "pred_win": sum(float(r["model_prob"]) for r in rs) / len(rs),
                    "actual_win": perf["win_rate"], "roi": perf["roi"],
                    "small_sample": len(rs) < 50})
    return out

# ---------------------------------------------------------------- P1.4 CLV

def clv_report(rows: Sequence[dict]) -> dict:
    vals = []
    for r in rows:
        if r.get("close_odds") in (None, ""):
            continue
        try:
            c = clv(float(r["odds"]), float(r["close_odds"]),
                    float(r["close_other_odds"]) if r.get("close_other_odds") not in (None, "") else None)
        except ValueError:
            continue
        vals.append({**c, "pred_id": r.get("pred_id"), "result": r.get("result")})
    if not vals:
        return {"n": 0, "coverage": 0.0}
    n = len(vals)
    mean = sum(v["clv_prob"] for v in vals) / n
    perf = stats.performance([r for r in rows if r.get("result")])
    warn = None
    if perf["roi"] and perf["roi"] > 0 and mean < 0:
        warn = "WINNING_WITH_NEGATIVE_CLV — likely variance, not edge"
    return {"n": n, "coverage": n / len(rows), "mean_clv_prob": mean,
            "beat_close_rate": sum(v["beat_close"] for v in vals) / n,
            "mean_clv_ev": sum(v["clv_ev"] for v in vals) / n, "warning": warn}

# ---------------------------------------------------------------- P1.5 backtest auditor + version tracker

def backtest_audit(rows: Sequence[dict], rules: Sequence[dict]) -> dict:
    """Rusty T2#2 + T2#7. rules: [{rule_version, active_ts}] — when each rule went live.

    A selection is PROSPECTIVE only if its rule_version was active before pred_ts AND
    pred_ts < kickoff. Everything else is RETROSPECTIVE and reported separately.
    """
    active = {r["rule_version"]: ts(r["active_ts"]) for r in rules}
    pro, retro, issues = [], [], []
    for r in rows:
        a, p, k = active.get(r.get("rule_version")), ts(r.get("pred_ts")), ts(r.get("kickoff_ts"))
        ok = a is not None and p is not None and a <= p and (k is None or p < k)
        (pro if ok else retro).append(r)
        if a is None:
            issues.append(finding("UNKNOWN_RULE_VERSION", "HIGH", r, str(r.get("rule_version"))))
        if r.get("result") in (None, "") and k and p and p < k:
            issues.append(finding("UNGRADED", "MEDIUM", r))
        if r.get("odds_ts") in (None, ""):
            issues.append(finding("ODDS_AVAILABILITY_UNVERIFIED", "HIGH", r))
    by_ver = {v: stats.performance(rs) for v, rs in stats.group_by(pro, "rule_version").items()}
    for v in by_ver.values():
        v.pop("curve", None)
    p_all, r_all = stats.performance(pro), stats.performance(retro)
    p_all.pop("curve"); r_all.pop("curve")
    return {"prospective": p_all, "retrospective": r_all, "by_version": by_ver, "issues": issues,
            "reproducible_ids": [r.get("pred_id") for r in pro if r.get("odds_ts")]}


def append_only_check(old: Sequence[dict], new: Sequence[dict],
                      frozen=("model_prob", "odds", "pred_ts", "side", "market", "rule_version")) -> list[dict]:
    """'Never overwrite historical predictions': diff two snapshots of the ledger."""
    nmap = {r["pred_id"]: r for r in new}
    out = []
    for r in old:
        n = nmap.get(r["pred_id"])
        if n is None:
            out.append(finding("ROW_REMOVED", "CRITICAL", r, "historical pick deleted"))
            continue
        for f in frozen:
            if str(r.get(f)) != str(n.get(f)):
                out.append(finding("ROW_REWRITTEN", "CRITICAL", r, f"{f}: {r.get(f)} -> {n.get(f)}"))
    return out

# ---------------------------------------------------------------- P4 EV inspector (Rusty T2#4)

def ev_inspector(rows: Sequence[dict], benchmark_book: str | None = None, commission: float = 0.0,
                 stale_minutes: float = 60) -> dict:
    """Realised execution: best-price vs benchmark book, stale lines, commissions."""
    best, bench, killed = [], [], []
    for r in rows:
        prices = r.get("prices") or {r.get("book", "book"): r["odds"]}
        mp, pp = float(r["model_prob"]), float(r.get("p_push") or 0)
        bp = max(prices.values(), key=lambda o: ev_per_unit(mp, float(o), pp))
        ev_best = ev_per_unit(mp, float(bp), pp, commission)
        best.append(ev_best)
        if benchmark_book and benchmark_book in prices:
            ev_b = ev_per_unit(mp, float(prices[benchmark_book]), pp, commission)
            bench.append(ev_b)
            if ev_best > 0 >= ev_b:
                killed.append({"pred_id": r.get("pred_id"), "why": "EDGE_ONLY_AT_BEST_BOOK"})
        o, p = ts(r.get("odds_ts")), ts(r.get("pred_ts"))
        if o and p and (p - o).total_seconds() / 60 > stale_minutes and ev_best > 0:
            killed.append({"pred_id": r.get("pred_id"), "why": "STALE_LINE"})
        if r.get("unavailable"):
            killed.append({"pred_id": r.get("pred_id"), "why": "LINE_UNAVAILABLE"})
    avg = lambda xs: sum(xs) / len(xs) if xs else None
    return {"mean_ev_best_price": avg(best), "mean_ev_benchmark": avg(bench),
            "edges_that_disappear": killed}


def sort_findings(fs):
    return sorted(fs, key=lambda f: SEV.get(f["severity"], 9))
