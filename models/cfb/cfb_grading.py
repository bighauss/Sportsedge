"""Grade frozen CFB PAPER cards and evaluate them chronologically. PAPER / 0u.

``grade`` appends one GAME_GRADED ledger entry per (frozen card, game) using
an official CFBD final matched by the exact CFBD game ID and both exact team
IDs. CFBD ``homePoints`` / ``awayPoints`` are final scores including
overtime. Frozen cards are re-hashed and never edited; PASS, HOLD, NO_QUOTE,
loss and push rows are all kept. A conflicting later final refuses instead of
overwriting.

``evaluate`` reads the ledger in kickoff order and compares the frozen RUN IT
model, the ratings-only SP+ baseline and the same-time market only on
untouched games (kickoff after model registration, card registered in the
ledger before kickoff, every input captured before kickoff). Accuracy
(MAE, Brier, log-loss, calibration, CLV) is reported separately from
hypothetical flat-stake paper returns. None of it is a validation certificate.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import median
import sys

from models.cfb import cfb_baselines as baselines
from models.cfb import cfb_capture_store as store
from models.cfb import cfb_ledger as ledger
from models.cfb import cfb_paper_card as card_mod
from models.cfb.cfb_capture_store import CaptureRefused, utc, stamp

PAPER = {"official_counted": 0, "approved_stake_u": 0}
MIN_SAMPLE_FOR_ANY_CLAIM = 300


class GradeRefused(ValueError):
    pass


# ------------------------------------------------------------------ helpers
def load_frozen_cards(entries, cards_dir):
    d = store.private_dir(cards_dir)
    cards = {}
    for e in entries:
        if e["type"] != "CARD_FROZEN":
            continue
        body = store.read_private(d / e["card_file"])
        if sha256(body).hexdigest() != e["card_sha256"]:
            raise GradeRefused("FROZEN_CARD_MODIFIED_AFTER_REGISTRATION")
        cards[e["card_sha256"]] = (e, store.strict_json(body))
    return cards


def parse_finals(raw, receipt):
    if not isinstance(receipt, dict) or receipt.get("sha256") != "sha256:" + sha256(raw).hexdigest():
        raise GradeRefused("FINALS_SHA_MISMATCH")
    if not isinstance(receipt.get("provider"), str) or not receipt["provider"].strip():
        raise GradeRefused("FINALS_PROVIDER_REQUIRED")
    captured = utc(receipt.get("captured_utc"), "finals_captured")
    rows = store.strict_json(raw)
    if not isinstance(rows, list):
        raise GradeRefused("FINALS_SCHEMA")
    out = {}
    for r in rows:
        gid = r.get("id") if isinstance(r, dict) else None
        if type(gid) is not int or gid in out:
            raise GradeRefused("FINALS_GAME_ID_INVALID_OR_DUPLICATE")
        out[gid] = r
    return out, captured


def side_results(q, margin, total):
    if q["market"] == "ML":
        a = "WIN" if margin > 0 else "LOSS"
        return a, ("LOSS" if a == "WIN" else "WIN")
    x = margin + q["line"] if q["market"] == "SPREAD" else total - q["line"]
    if x == 0:
        return "PUSH", "PUSH"
    return ("WIN", "LOSS") if x > 0 else ("LOSS", "WIN")


def _closing(q, closing_quotes, frozen, kickoff):
    best = None
    for c in closing_quotes:
        if (c["cfbd_game_id"], c["book"], c["market"]) != (q["cfbd_game_id"], q["book"], q["market"]):
            continue
        t = utc(c["captured_utc"])
        if not frozen < t < kickoff:
            continue
        if best is None or t > utc(best["captured_utc"]):
            best = c
    if best is None:
        return None
    na, nb, _ = card_mod.novig(best["price_a"], best["price_b"])
    return {"line": best["line"], "price_a": best["price_a"], "price_b": best["price_b"],
            "novig_a": round(na, 6), "novig_b": round(nb, 6), "captured_utc": best["captured_utc"],
            "source_sha256": best["source_sha256"]}


# ------------------------------------------------------------------ grading
def grade(ledger_path, cards_dir, finals_raw: bytes, finals_receipt: dict, *, closing_quotes=(), now=None):
    entries = ledger.verify(ledger_path)
    cards = load_frozen_cards(entries, cards_dir)
    finals, finals_captured = parse_finals(finals_raw, finals_receipt)
    done = {(e["card_sha256"], e["cfbd_game_id"]): e for e in entries if e["type"] == "GAME_GRADED"}
    pending = []
    for csha, (reg, card) in cards.items():
        frozen = utc(card["frozen_utc"])
        for g in card["games"]:
            gid = g["cfbd_game_id"]
            f = finals.get(gid)
            if f is None or f.get("completed") is not True:
                continue
            hp, ap = f.get("homePoints"), f.get("awayPoints")
            if type(hp) is not int or type(ap) is not int or hp < 0 or ap < 0:
                raise GradeRefused("FINAL_SCORE_INVALID")
            if f.get("homeId") != g["home_team_id"] or f.get("awayId") != g["away_team_id"]:
                raise GradeRefused("FINAL_TEAM_ID_MISMATCH_BORROWED_OR_SWAPPED")
            kickoff = utc(g["kickoff_utc"])
            if finals_captured <= kickoff:
                raise GradeRefused("FINAL_CAPTURED_BEFORE_KICKOFF")
            prior = done.get((csha, gid))
            if prior is not None:
                if (prior["home_points"], prior["away_points"]) != (hp, ap):
                    raise GradeRefused("FINAL_CONFLICT_REQUIRES_REVIEW")
                continue
            margin, total = hp - ap, hp + ap
            qrows = []
            for q in g["quotes"]:
                ra, rb = side_results(q, margin, total)
                qrows.append({"quote_id": q["quote_id"], "book": q["book"], "market": q["market"],
                              "line": q["line"], "result_a": ra, "result_b": rb,
                              "closing": _closing(q, closing_quotes, frozen, kickoff)})
            pending.append({
                "type": "GAME_GRADED", "card_sha256": csha, "cfbd_game_id": gid,
                "kickoff_utc": g["kickoff_utc"], "card_status": g["status"],
                "card_reasons": g["reasons"], "market_status": g["market_status"],
                "home_points": hp, "away_points": ap, "margin_home": margin, "total": total,
                "final_includes_overtime": True,
                "final_provider": finals_receipt["provider"], "final_source_sha256": finals_receipt["sha256"],
                "final_captured_utc": stamp(finals_captured),
                "card_registered_before_kickoff": utc(reg["appended_utc"]) < kickoff,
                "quotes": qrows})
    written = [ledger.append(ledger_path, p, now=now) for p in pending]
    return {"graded": len(written), "already_graded_or_pending": len(done), **PAPER}


# ------------------------------------------------------------------ evaluation
def _mean_ci(xs):
    n = len(xs)
    if n == 0:
        return {"n": 0, "mean": None, "ci95": None}
    m = sum(xs) / n
    if n < 2:
        return {"n": n, "mean": round(m, 6), "ci95": None}
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    h = 1.96 * sd / math.sqrt(n)
    return {"n": n, "mean": round(m, 6), "ci95": [round(m - h, 6), round(m + h, 6)]}


def _wilson(k, n):
    if n == 0:
        return None
    p, z = k / n, 1.96
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(c - h, 6), round(c + h, 6)]


def _ll(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _calibration(pairs, bins=10):
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(p, y) for p, y in pairs if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if sel:
            out.append({"bin": [lo, hi], "n": len(sel), "mean_pred": round(sum(p for p, _ in sel) / len(sel), 4),
                        "observed": round(sum(y for _, y in sel) / len(sel), 4)})
    return out


def _source_after_kickoff(card_game, card, kickoff):
    clocks = []
    for lin in (card_game.get("lineage") or {}).values():
        clocks.append(lin["captured_utc"])
    for r in (card.get("source_receipts") or {}).values():
        if r:
            clocks.append(r["captured_utc"])
    return any(utc(store_z(c)) >= kickoff for c in clocks)


def store_z(value):
    return value if value.endswith("Z") else value.replace("+00:00", "Z")


def evaluate(ledger_path, cards_dir, *, holdout_start_utc=None):
    entries = ledger.verify(ledger_path)
    cards = load_frozen_cards(entries, cards_dir)
    fid, rid = baselines.FROZEN_RUNIT["model_id"], baselines.RATINGS_ONLY_SP["model_id"]
    start = max(utc(baselines.HOLDOUT_START_UTC), utc(baselines.FROZEN_RUNIT["registered_utc"]),
                utc(baselines.RATINGS_ONLY_SP["registered_utc"]))
    if holdout_start_utc is not None:
        start = max(start, utc(holdout_start_utc))
    excluded, seen, rows = {}, set(), []
    graded = sorted((e for e in entries if e["type"] == "GAME_GRADED"),
                    key=lambda e: (e["kickoff_utc"], e["cfbd_game_id"], e["seq"]))
    for e in graded:
        reg, card = cards[e["card_sha256"]]
        g = next(x for x in card["games"] if x["cfbd_game_id"] == e["cfbd_game_id"])
        kickoff = utc(g["kickoff_utc"])
        reason = None
        if e["cfbd_game_id"] in seen:
            reason = "LATER_CARD_FOR_SAME_GAME_FIRST_REGISTERED_CARD_ONLY"
        elif kickoff < start:
            reason = "PRE_REGISTRATION_NOT_UNTOUCHED_HOLDOUT"
        elif not e["card_registered_before_kickoff"] or utc(card["frozen_utc"]) >= kickoff:
            reason = "CARD_NOT_FROZEN_AND_REGISTERED_BEFORE_KICKOFF"
        elif _source_after_kickoff(g, card, kickoff):
            reason = "INPUT_CAPTURED_AFTER_KICKOFF_NOT_PREGAME_EVIDENCE"
        seen.add(e["cfbd_game_id"])
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        rows.append((e, g))
    acc = {"margin_abs_error": {fid: [], rid: [], "market": []},
           "total_abs_error": {fid: [], rid: [], "market": []}}
    common = {"margin": {fid: [], rid: [], "market": []}, "total": {fid: [], rid: [], "market": []},
              "ml_brier": {fid: [], rid: [], "market": []}, "ml_logloss": {fid: [], rid: [], "market": []}}
    paired = {"margin_mae_frozen_minus_market": [], "margin_mae_ratings_minus_market": [],
              "margin_mae_frozen_minus_ratings": []}
    cover = {fid: [], rid: [], "market": []}
    calib = {fid: [], rid: [], "market": []}
    clv = {fid: [], rid: []}
    returns = {fid: [], rid: []}
    status_counts, weeks = {}, {}
    for e, g in rows:
        status_counts[e["card_status"]] = status_counts.get(e["card_status"], 0) + 1
        if e["market_status"] == "NO_QUOTE":
            status_counts["NO_QUOTE"] = status_counts.get("NO_QUOTE", 0) + 1
        week = weeks.setdefault(str(e["kickoff_utc"][:10]), {"games": 0})
        week["games"] += 1
        margin, total, y = e["margin_home"], e["total"], 1 if e["margin_home"] > 0 else 0
        fc = {m: g["forecasts"][m] for m in (fid, rid)}
        spreads = [q["line"] for q in g["quotes"] if q["market"] == "SPREAD"]
        totals = [q["line"] for q in g["quotes"] if q["market"] == "TOTAL"]
        mls = [q["market_novig_a"] for q in g["quotes"] if q["market"] == "ML"]
        mkt = {"margin": -median(spreads) if spreads else None, "total": median(totals) if totals else None,
               "p_home": sum(mls) / len(mls) if mls else None}
        for m in (fid, rid):
            if fc[m]["status"] == "PROJECTED":
                acc["margin_abs_error"][m].append(abs(fc[m]["margin_home"] - margin))
                acc["total_abs_error"][m].append(abs(fc[m]["total"] - total))
        if mkt["margin"] is not None:
            acc["margin_abs_error"]["market"].append(abs(mkt["margin"] - margin))
        if mkt["total"] is not None:
            acc["total_abs_error"]["market"].append(abs(mkt["total"] - total))
        both = all(fc[m]["status"] == "PROJECTED" for m in (fid, rid))
        if both and mkt["margin"] is not None and mkt["total"] is not None and mkt["p_home"] is not None:
            ef, er, em = (abs(fc[fid]["margin_home"] - margin), abs(fc[rid]["margin_home"] - margin),
                          abs(mkt["margin"] - margin))
            for k, v in ((fid, ef), (rid, er), ("market", em)):
                common["margin"][k].append(v)
            for k, v in ((fid, fc[fid]["total"]), (rid, fc[rid]["total"]), ("market", mkt["total"])):
                common["total"][k].append(abs(v - total))
            for k, p in ((fid, fc[fid]["p_home_win"]), (rid, fc[rid]["p_home_win"]), ("market", mkt["p_home"])):
                common["ml_brier"][k].append((p - y) ** 2)
                common["ml_logloss"][k].append(_ll(p, y))
                calib[k].append((p, y))
            paired["margin_mae_frozen_minus_market"].append(ef - em)
            paired["margin_mae_ratings_minus_market"].append(er - em)
            paired["margin_mae_frozen_minus_ratings"].append(ef - er)
        results = {r["quote_id"]: r for r in e["quotes"]}
        for q in g["quotes"]:
            r = results[q["quote_id"]]
            if q["market"] != "ML" and r["result_a"] != "PUSH":
                ya = 1 if r["result_a"] == "WIN" else 0
                cover["market"].append((q["market_novig_a"] - ya) ** 2)
                for m in (fid, rid):
                    mm = q["models"][m]
                    if mm["status"] == "PRICED":
                        cover[m].append((mm["p_model_a"] - ya) ** 2)
            for m in (fid, rid):
                mm = q["models"][m]
                lean = mm.get("paper_lean_unvalidated") if mm["status"] == "PRICED" else None
                if lean is None:
                    continue
                a = lean == q["side_a"]
                res = r["result_a"] if a else r["result_b"]
                price = q["price_a"] if a else q["price_b"]
                units = {"WIN": card_mod.decimal_odds(price) - 1, "LOSS": -1.0, "PUSH": 0.0}[res]
                returns[m].append((res, units))
                c = r.get("closing")
                if c is not None and c["line"] == q["line"]:
                    p_close = c["novig_a"] if a else c["novig_b"]
                    clv[m].append(p_close * card_mod.decimal_odds(price) - 1)
    def mae(d):
        return {k: _mean_ci(v) for k, v in d.items()}
    def ret(m):
        xs = returns[m]
        w = sum(1 for r, _ in xs if r == "WIN")
        l = sum(1 for r, _ in xs if r == "LOSS")
        u = [x for _, x in xs]
        return {"bets": len(xs), "wins": w, "losses": l, "pushes": len(xs) - w - l,
                "win_rate_ci95_ex_push": _wilson(w, w + l), "units": round(sum(u), 4),
                "roi_per_bet": _mean_ci(u), "label": "HYPOTHETICAL_1U_FLAT_PAPER_NOT_COUNTED"}
    n = len(rows)
    report = {
        "schema": "sportsedge-cfb-paper-evaluation-v1",
        "holdout_start_utc": stamp(start), "games_evaluated": n, "excluded": excluded,
        "status_counts": status_counts, "by_kickoff_date": weeks,
        "accuracy": {
            "own_coverage": {"margin_mae": mae(acc["margin_abs_error"]), "total_mae": mae(acc["total_abs_error"])},
            "common_set": {"margin_mae": mae(common["margin"]), "total_mae": mae(common["total"]),
                           "ml_brier": mae(common["ml_brier"]), "ml_logloss": mae(common["ml_logloss"])},
            "paired_margin_mae_differences": {k: _mean_ci(v) for k, v in paired.items()},
            "spread_total_cover_brier_ex_push": mae(cover),
            "ml_calibration": {k: _calibration(v) for k, v in calib.items()},
            "clv_ev_vs_closing_novig_same_line": {k: _mean_ci(v) for k, v in clv.items()},
        },
        "returns_separate_from_accuracy": {m: ret(m) for m in (fid, rid)},
        "sample_warning": (n < MIN_SAMPLE_FOR_ANY_CLAIM),
        "interpretation": ("Descriptive PAPER evaluation only. Not a validation certificate; no edge is "
                           "verified; intervals are normal/Wilson approximations without multiple-testing "
                           "correction."),
        "validation_certified": False, **PAPER,
    }
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade")
    g.add_argument("--ledger", required=True)
    g.add_argument("--cards-dir", required=True)
    g.add_argument("--finals", required=True, help="CFBD /games JSON captured after the games")
    g.add_argument("--finals-provider", default="collegefootballdata.com")
    g.add_argument("--closing-quotes", action="append", default=[])
    ev = sub.add_parser("evaluate")
    ev.add_argument("--ledger", required=True)
    ev.add_argument("--cards-dir", required=True)
    ev.add_argument("--holdout-start-utc")
    a = p.parse_args(argv)
    try:
        if a.cmd == "grade":
            raw = store.read_private(Path(a.finals))
            receipt = {"provider": a.finals_provider, "sha256": "sha256:" + sha256(raw).hexdigest(),
                       "captured_utc": stamp(store.now_utc())}
            closing = []
            for c in a.closing_quotes:
                closing += card_mod.load_operator_quotes(store.read_private(Path(c)), name=Path(c).stem)
            out = grade(a.ledger, a.cards_dir, raw, receipt, closing_quotes=closing)
        else:
            out = evaluate(a.ledger, a.cards_dir, holdout_start_utc=a.holdout_start_utc)
    except (GradeRefused, CaptureRefused, ledger.LedgerRefused, card_mod.QuoteRefused, OSError) as exc:
        print("CFB_GRADING_BLOCKED " + (str(exc) if not isinstance(exc, OSError) else "OS_ERROR"), file=sys.stderr)
        return 2
    print(json.dumps(out, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
