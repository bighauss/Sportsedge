"""P8 — daily RUN IT audit gates + candidate output contract + post-game grading.

Sequence: fresh-data check → (engine projections, external) → candidate edges →
P1 gates (leakage, largest-edge, calibration, data quality) → candidate list with
audit trail + blocked list → append-only ledger for grading.

The production engine is never imported or modified (rule 4).
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from typing import Sequence

from . import audits, stats
from .odds import implied_prob, ev_per_unit, prob_to_american, no_vig

REQUIRED_OUTPUT = ("model_prob", "fair_odds", "edge", "ev_per_unit", "best_price", "best_book",
                   "uncertainty", "price_ts", "audit_status", "reason_codes", "correlation_flags",
                   "input_timestamps")


def freshness(rows: Sequence[dict], now=None, max_age_min: float = 30) -> list[dict]:
    now = audits.ts(now) or datetime.now(timezone.utc)
    out = []
    for r in rows:
        o = audits.ts(r.get("odds_ts"))
        if o is None or (now - o).total_seconds() / 60 > max_age_min:
            out.append(audits.finding("STALE_DATA", "HIGH", r, f"odds_ts={r.get('odds_ts')}"))
        if o is not None and o > now:
            out.append(audits.finding("FUTURE_PRICE_CAPTURE", "CRITICAL", r))
        k = audits.ts(r.get("kickoff_ts"))
        if k is None:
            out.append(audits.finding("KICKOFF_NOT_VERIFIED", "CRITICAL", r))
        elif k <= now:
            out.append(audits.finding("LIVE_OR_CLOSED", "CRITICAL", r))
    return out


def stars(ev: float, uncertainty: float) -> int:
    """1-5 star rating from EV per unit, discounted by uncertainty (prob SD)."""
    adj = ev - uncertainty
    return max(1, min(5, 1 + int(adj / 0.02))) if adj > 0 else 1


def run_gates(candidates: Sequence[dict], calib_history: Sequence[dict] = (), now=None,
              max_edge: float = 0.10, min_ev: float = 0.0, max_age_min: float = 30,
              calib_min_n: int = 30) -> dict:
    """Return {candidates, blocked, summary}. Every candidate keeps an audit trail."""
    leak = {}
    for f in audits.leakage_audit(candidates):
        leak.setdefault(f["pred_id"], []).append(f)
    fresh = {}
    for f in freshness(candidates, now, max_age_min):
        fresh.setdefault(f["pred_id"], []).append(f)
    dq = {}
    for f in audits.data_quality(candidates)["issues"]:
        if f["pred_id"]:
            dq.setdefault(f["pred_id"], []).append(f)
    # calibration of past out-of-sample predictions in same probability bucket
    calib = {}
    if calib_history:
        graded = [h for h in calib_history if h.get("result") in ("W", "L")]
        for row in stats.calibration_table([float(h["model_prob"]) for h in graded],
                                           [int(h["result"] == "W") for h in graded], min_n=calib_min_n):
            calib[row["bucket"]] = row
    out, blocked = [], []
    for c in candidates:
        # This research helper cannot authenticate provider originals, independently
        # certify calibration, or authorize betting. It must NEVER self-certify PASS.
        codes, sev = ["RESEARCH_ONLY_NO_INDEPENDENT_ATTESTATION"], ["HIGH"]
        if not c.get("inputs"):
            codes.append("MISSING_INPUT_LINEAGE"); sev.append("HIGH")
        if not calib_history:
            codes.append("CALIB_NO_HISTORY"); sev.append("HIGH")
        for f in leak.get(c.get("pred_id"), []) + fresh.get(c.get("pred_id"), []) + dq.get(c.get("pred_id"), []):
            codes.append(f["code"]); sev.append(f["severity"])
        prices = c.get("prices") or {c.get("book", "book"): c["odds"]}
        mp, pp = float(c["model_prob"]), float(c.get("p_push") or 0)
        best_book = max(prices, key=lambda b: ev_per_unit(mp, float(prices[b]), pp))
        best = float(prices[best_book])
        ev = ev_per_unit(mp, best, pp)
        edge = mp - implied_prob(best)
        if edge > max_edge:
            codes.append("LARGE_EDGE_REVIEW"); sev.append("MEDIUM")
        if ev <= min_ev:
            codes.append("NO_POSITIVE_EV"); sev.append("HIGH")
        lo = int(mp * 20) / 20
        b = calib.get(f"{lo:.0%}-{lo + .05:.0%}")
        if b:
            if b["verdict"] == "OVERCONFIDENT":
                codes.append("BUCKET_OVERCONFIDENT"); sev.append("MEDIUM")
            elif b["verdict"] == "SMALL_SAMPLE":
                codes.append("CALIB_SMALL_SAMPLE"); sev.append("LOW")
        elif calib_history:
            codes.append("CALIB_NO_HISTORY"); sev.append("LOW")
        if c.get("correlated_with"):
            codes.append("CORRELATED")
        unc = float(c.get("prob_sd") or (b and (b["ci_hi"] - b["ci_lo"]) / 4) or 0.03)
        status = ("BLOCKED" if "CRITICAL" in sev or "NO_POSITIVE_EV" in codes
                  else "FLAGGED")
        other = c.get("other_side_odds")
        rec = {**c, "model_prob": mp, "fair_odds": round(prob_to_american(mp)),
               "market_no_vig": no_vig([best, float(other)])[0] if other not in (None, "") else None,
               "edge": edge, "ev_per_unit": ev, "best_price": best, "best_book": best_book,
               "uncertainty": unc, "stars": stars(ev, unc), "price_ts": c.get("odds_ts"),
               "audit_status": status, "reason_codes": sorted(set(codes)),
               "correlation_flags": c.get("correlated_with") or [],
               "input_timestamps": {i["name"]: i.get("ts") for i in c.get("inputs") or []},
               "release_ready": False, "official_counted": 0, "approved_stake_u": 0}
        (blocked if status == "BLOCKED" else out).append(rec)
    out.sort(key=lambda r: -r["ev_per_unit"])
    blocked.sort(key=lambda r: -r["ev_per_unit"])
    return {"candidates": out, "blocked": blocked,
            "summary": {"in": len(candidates), "passed": sum(r["audit_status"] == "PASSED" for r in out),
                        "flagged": sum(r["audit_status"] == "FLAGGED" for r in out),
                        "blocked": len(blocked)}}


def card_view(result: dict) -> list[dict]:
    """Owner-facing card rows: price, win %, EV, stars, flames — ranked by EV, no status labels."""
    rows = []
    for i, r in enumerate(result["candidates"]):
        rows.append({"rank": i + 1, "pick": f"{r.get('market')} {r.get('side')}".strip(),
                     "player": r.get("player"), "price": r["best_price"], "book": r["best_book"],
                     "win_pct": round(100 * r["model_prob"], 1), "ev_pct": round(100 * r["ev_per_unit"], 1),
                     "stars": r["stars"], "flame": r["stars"] >= 4,
                     "audit_status": r["audit_status"], "reason_codes": r["reason_codes"],
                     "release_ready": False, "approved_stake_u": 0})
    return rows


# ------------------------------------------------------------ append-only ledger / tracker (Rusty T1#7)

LEDGER_FIELDS = ["pred_id", "logged_ts", "game_id", "sport", "market", "side", "player", "book",
                 "line", "odds", "model_prob", "pred_ts", "kickoff_ts", "rule_version",
                 "model_version", "audit_status", "row_hash", "result", "net_units"]


def row_hash(r: dict) -> str:
    core = {k: r.get(k) for k in ("pred_id", "market", "side", "line", "odds", "model_prob", "pred_ts", "rule_version")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:16]


def ledger_append(path: str, rows: Sequence[dict]) -> int:
    """Preflight all new rows before append. Never backdate an after-kickoff log.

    Local research CSVs are not immutable, independently authenticated receipts.
    """
    try:
        with open(path, newline="") as f:
            existing = {r["pred_id"] for r in csv.DictReader(f)}
    except FileNotFoundError:
        existing = set()
    now_dt = datetime.now(timezone.utc)
    prepared, seen = [], set()
    for r in rows:
        identity = r.get("pred_id")
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise ValueError("missing or duplicated prediction identity")
        seen.add(identity)
        if identity in existing:
            continue
        try:
            k, p = audits.ts(r.get("kickoff_ts")), audits.ts(r.get("pred_ts"))
            if (k is None or p is None or k.utcoffset() is None or p.utcoffset() is None
                    or p > now_dt or p >= k or now_dt >= k):
                raise ValueError("missing, naive or post-kickoff timestamps")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"refusing unverifiable or late selection {identity}") from exc
        prepared.append({**r, "logged_ts": now_dt.isoformat(), "row_hash": row_hash(r)})
    if not prepared:
        return 0
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, LEDGER_FIELDS, extrasaction="ignore")
        if f.tell() == 0:
            writer.writeheader()
        writer.writerows(prepared)
    return len(prepared)


def grade(ledger_rows: Sequence[dict], results: dict[str, dict]) -> list[dict]:
    """results: {pred_id: {result}}. Only fills grading fields; hashes verified."""
    out = []
    for r in ledger_rows:
        g = dict(r)
        if r.get("row_hash") and r["row_hash"] != row_hash(r):
            g["grade_flag"] = "HASH_MISMATCH_ROW_EDITED"
        res = results.get(r["pred_id"])
        if res:
            g["result"] = res["result"]
            g["net_units"] = stats.bet_profit({"result": res["result"], "odds": r["odds"]})
        out.append(g)
    return out


def postgame_report(graded: Sequence[dict], rules: Sequence[dict] = ()) -> dict:
    """Mandatory post-game: every prediction graded incl. blocked; calibration, ROI, DD."""
    g = [r for r in graded if r.get("result") in ("W", "L", "P", "V")]
    wl = [r for r in g if r["result"] in ("W", "L")]
    rep = {"graded": len(g), "ungraded": len(graded) - len(g)}
    for status in ("PASSED", "FLAGGED", "BLOCKED", None):
        sub = [r for r in g if status is None or r.get("audit_status") == status]
        if sub:
            p = stats.performance(sub); p.pop("curve")
            rep[f"performance_{status or 'ALL'}"] = p
    if wl:
        pr = [float(r["model_prob"]) for r in wl]
        oc = [int(r["result"] == "W") for r in wl]
        rep.update(brier=stats.brier(pr, oc), log_loss=stats.log_loss(pr, oc), ece=stats.ece(pr, oc),
                   calibration=stats.calibration_table(pr, oc))
    if rules:
        rep["versions"] = audits.backtest_audit(g, rules)
    rep["bias"] = audits.bias_breakdown(g, dims=("market", "side", "edge_bucket"))
    return rep
