"""Append-only CBBD paper-card ledger, exact-ID grading and chronological evaluation.

The ledger is a private JSONL hash chain. Frozen cards are appended whole
(every PASS / no-quote row kept) and NEVER rewritten; finals and closing
quotes are separate later entries keyed by exact CBBD game ID. Any edit to an
earlier line breaks the chain and every read fails closed.

Finals are verified with ``cbbd_frozen_final_join.verify_provider_originals``
(original CBBD /games bytes + manifest) and ``_final_verified``; identity and
clocks reuse ``point_in_time_score_walkforward._parse_final``. The chronological
score walk-forward reuses ``point_in_time_score_walkforward.audit``.

Forecast accuracy and paper returns are reported SEPARATELY. Everything is
PAPER / 0u; no metric here is predictive validation or verified +EV/CLV.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from statistics import mean, stdev

from cbbd_native_score_model import Pass, canonical_id, decimal_odds, no_vig, stamp, utc
from cbbd_paper_card import (CARD_SCHEMA, CARD_STATUS, MARKETS, card_digest,
                             canonical_bytes, normalise_quote, sha)
from cbbd_frozen_final_join import _final_verified, verify_provider_originals, _load
from cbbd_prospective_capture import safe_path
from point_in_time_score_walkforward import (Blocked, _paired_ci, _parse_final,
                                             audit as walkforward_audit)
from cbb_pricing import OWNER_BLEND_WEIGHTS

LEDGER_SCHEMA = "sportsedge-cbbd-paper-ledger-v1"
GENESIS = "0" * 64
KINDS = ("CARD_FROZEN", "FINAL_ATTACHED", "CLOSE_QUOTE")


class LedgerError(ValueError):
    pass


# ---------------------------------------------------------------- chain

def _entry_hash(entry):
    return sha(canonical_bytes({k: v for k, v in entry.items() if k != "entry_sha256"}))


def parse_ledger(raw):
    """Verify the full hash chain; any tamper/reorder/truncation-in-middle fails."""
    entries, prev = [], GENESIS
    for i, line in enumerate(raw.decode("utf-8").splitlines()):
        try:
            e = json.loads(line)
        except ValueError as exc:
            raise LedgerError("LEDGER_LINE_NOT_JSON") from exc
        if not isinstance(e, dict) or e.get("schema") != LEDGER_SCHEMA or e.get("seq") != i or \
                e.get("prev_entry_sha256") != prev or e.get("kind") not in KINDS or \
                e.get("entry_sha256") != _entry_hash(e):
            raise LedgerError("LEDGER_CHAIN_BROKEN_AT:" + str(i))
        prev = e["entry_sha256"]
        entries.append(e)
    return entries


def _make_entry(entries, kind, payload, recorded_utc):
    e = {"schema": LEDGER_SCHEMA, "seq": len(entries), "kind": kind,
         "recorded_utc": recorded_utc,
         "prev_entry_sha256": entries[-1]["entry_sha256"] if entries else GENESIS,
         "payload": payload, "official_counted": 0, "approved_stake_u": 0}
    e["entry_sha256"] = _entry_hash(e)
    return e


def _open_ledger(path):
    target = safe_path(path)
    fd = os.open(str(target), os.O_RDWR | os.O_CREAT | os.O_APPEND |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    if os.fstat(fd).st_mode & 0o077:
        os.close(fd)
        raise LedgerError("LEDGER_FILE_MODE_MUST_BE_0600")
    return fd


def _read_fd(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    while True:
        b = os.read(fd, 1 << 20)
        if not b:
            break
        chunks.append(b)
    return b"".join(chunks)


def append(path, build, *, clock=None):
    """Lock, re-verify the whole chain, then append new entries only."""
    now = stamp((clock or (lambda: datetime.now(timezone.utc)))())
    fd = _open_ledger(path)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        entries = parse_ledger(_read_fd(fd))
        payloads, report = build(entries, now)
        new = []
        for kind, payload in payloads:
            new.append(_make_entry(entries + new, kind, payload, now))
        data = b"".join(json.dumps(e, sort_keys=True, allow_nan=False).encode() + b"\n"
                        for e in new)
        if data:
            os.write(fd, data)
            os.fsync(fd)
        return {**report, "appended": len(new), "official_counted": 0, "approved_stake_u": 0}
    finally:
        os.close(fd)


def read(path):
    raw = safe_path(path).read_bytes()
    return parse_ledger(raw)


# ---------------------------------------------------------------- views

def _card_rows(entries):
    """Every frozen row in ledger order (duplicates are kept, never collapsed)."""
    return [(e["payload"], r) for e in entries if e["kind"] == "CARD_FROZEN"
            for r in e["payload"]["rows"]]


def _cards(entries):
    """Exact game_id -> (card, row) for IDs that occur exactly once on the ledger."""
    rows = _card_rows(entries)
    count = Counter(r["game_id"] for _, r in rows)
    return {r["game_id"]: (c, r) for c, r in rows if count[r["game_id"]] == 1}


def _done(entries, kind):
    out = defaultdict(dict)
    for e in entries:
        if e["kind"] == kind:
            p = e["payload"]
            out[p["game_id"]][p.get("market")] = p
    return out


# ---------------------------------------------------------------- cards

def card_entries(card):
    def build(entries, now):
        if not isinstance(card, dict) or card.get("schema") != CARD_SCHEMA or \
                card.get("status") != CARD_STATUS or card.get("official_counted") != 0 or \
                card.get("approved_stake_u") != 0:
            raise LedgerError("CARD_UNRECOGNIZED_OR_NON_PAPER")
        if card.get("card_sha256") != card_digest(card):
            raise LedgerError("CARD_SELF_HASH_MISMATCH_TAMPERED")
        if any(e["payload"].get("card_sha256") == card["card_sha256"]
               for e in entries if e["kind"] == "CARD_FROZEN"):
            raise LedgerError("CARD_ALREADY_FROZEN")
        if utc(now, "now") < utc(card["built_utc"], "built"):
            raise LedgerError("LEDGER_CLOCK_BEFORE_CARD_BUILD")
        seen = {r["game_id"] for _, r in _card_rows(entries)}
        ids = [r["game_id"] for r in card["rows"]]
        if any(g in seen for g in ids):
            raise LedgerError("GAME_ALREADY_FROZEN_IN_EARLIER_CARD")
        return [("CARD_FROZEN", card)], {"state": "CARD_FROZEN", "rows": len(ids)}
    return build


# ---------------------------------------------------------------- closes

def close_entries(quote_rows):
    """Closing quotes: captured after the card freeze and strictly before tip."""
    def build(entries, now):
        games, done = _cards(entries), _done(entries, "CLOSE_QUOTE")
        out, census = [], Counter()
        for row in quote_rows:
            try:
                q = normalise_quote(row, "OPERATOR_CLOSE")
            except Pass as exc:
                census["rejected:" + str(exc)] += 1
                continue
            hit = games.get(q["game_id"])
            if hit is None:
                census["rejected:GAME_NOT_ON_LEDGER_CARD"] += 1
                continue
            card, r = hit
            cap = utc(q["captured_utc"], "close")
            if not utc(card["freeze_utc"], "f") <= cap < utc(r["tipoff_utc"], "t") or \
                    cap > utc(now, "now"):
                census["rejected:CLOSE_NOT_BETWEEN_FREEZE_AND_TIP"] += 1
                continue
            if q["market"] in done[q["game_id"]] or any(
                    p["game_id"] == q["game_id"] and p["market"] == q["market"] for _, p in out):
                census["rejected:CLOSE_ALREADY_RECORDED"] += 1
                continue
            out.append(("CLOSE_QUOTE", {"game_id": q["game_id"], "market": q["market"],
                                        "quote": q, "card_sha256": card["card_sha256"]}))
            census["recorded"] += 1
        return out, {"state": "CLOSES_PROCESSED", "census": dict(census)}
    return build


# ---------------------------------------------------------------- grading

def _outcome(market, line, margin, total):
    if market == "moneyline":
        return "home" if margin > 0 else "away"
    v = margin + line if market == "spread" else total - line
    if v == 0:
        return "push"
    if market == "spread":
        return "home" if v > 0 else "away"
    return "over" if v > 0 else "under"


def grade_market(m, final):
    margin = final["home_score"] - final["away_score"]
    total = final["home_score"] + final["away_score"]
    g = {"market": m["market"], "card_status": m["status"], "pass_reason": m.get("pass_reason"),
         "outcome": None, "paper_selection": None, "paper_result": None,
         "hypothetical_flat_1u_return": None, "label": "PAPER", "stake_u": 0}
    if m["status"] != "PRICED_PAPER":
        g["paper_result"] = "NO_QUOTE" if m.get("pass_reason") == "MISSING_QUOTE" else "PASS"
        return g
    q = m["quote"]
    g["outcome"] = _outcome(m["market"], q["line"], margin, total)
    ev = m["paper_ev_per_1u_at_price"]
    side = max(m["sides"], key=lambda s: (ev[s], s))
    if ev[side] <= 0:
        g["paper_result"] = "NO_POSITIVE_PAPER_EV_SELECTION"
        return g
    price = q["price_a"] if side == m["sides"][0] else q["price_b"]
    g["paper_selection"] = side
    if g["outcome"] == "push":
        g["paper_result"], g["hypothetical_flat_1u_return"] = "P", 0.0
    elif g["outcome"] == side:
        g["paper_result"], g["hypothetical_flat_1u_return"] = "W", decimal_odds(price) - 1
    else:
        g["paper_result"], g["hypothetical_flat_1u_return"] = "L", -1.0
    return g


def final_entries(finals, provider_raw, provider_manifest):
    """Attach verified finals by EXACT game ID; never edits a card row."""
    original_sha = verify_provider_originals(finals, provider_raw, provider_manifest)

    def build(entries, now):
        games, graded = _cards(entries), _done(entries, "FINAL_ATTACHED")
        by_id = defaultdict(list)
        for row in finals.get("rows", []):
            gid = canonical_id(row.get("game_id")) if isinstance(row, dict) else None
            if gid is not None:
                by_id[gid].append(row)
        out, census = [], Counter()
        census["blocked:DUPLICATE_OR_NONUNIQUE_CARD_GAME_ID"] = sum(
            1 for _, r in _card_rows(entries) if r["game_id"] not in games)
        for gid, (card, r) in sorted(games.items()):
            if gid in graded:
                census["already_graded"] += 1
                continue
            matched = by_id.get(gid, [])
            if not matched:
                census["pending_no_final"] += 1
                continue
            if len(matched) > 1:
                census["blocked:DUPLICATE_FINAL_ALL_COPIES"] += 1
                continue
            f, why = _final_verified(matched[0], finals["source_sha256"],
                                     finals["local_observed_utc"])
            if f is None:
                census["blocked:" + why] += 1
                continue
            try:
                if not r["season"].isdecimal():
                    raise Blocked("CARD_SEASON_INVALID")
                p = {"id": gid, "season": int(r["season"]), "home": r["home_team_id"],
                     "away": r["away_team_id"], "tip": utc(r["tipoff_utc"], "tip")}
                _parse_final(f, p)
                if utc(card["freeze_utc"], "f") >= p["tip"]:
                    raise Blocked("CARD_FREEZE_NOT_BEFORE_TIP")
            except (Blocked, Pass, KeyError, TypeError, ValueError) as exc:
                census["blocked:" + str(exc)] += 1
                continue
            out.append(("FINAL_ATTACHED", {
                "game_id": gid, "market": None, "card_sha256": card["card_sha256"],
                "final": f, "final_report_source_sha256": finals["source_sha256"],
                "provider_raw_sha256": original_sha,
                "card_row_status": r["status"], "card_pass_reason": r["pass_reason"],
                "grades": [grade_market(m, f) for m in r["markets"]]}))
            census["attached"] += 1
        return out, {"state": "FINALS_PROCESSED", "census": dict(sorted(census.items()))}
    return build


# ---------------------------------------------------------------- evaluation

def _ll(p, y):
    p = min(1 - 1e-12, max(1e-12, p))
    return -math.log(p if y else 1 - p)


def _pair_summary(pairs, metric):
    if not pairs:
        return {"n": 0, "metric": metric, "model": None, "market": None,
                "market_minus_model": None, "ci95": None}
    d = [b - a for a, b in pairs]
    return {"n": len(pairs), "metric": metric, "model": mean(a for a, _ in pairs),
            "market": mean(b for _, b in pairs), "market_minus_model": mean(d),
            "ci95": _paired_ci(d)}


def _mean_ci(values):
    if not values:
        return {"n": 0, "mean": None, "ci95": None}
    return {"n": len(values), "mean": mean(values), "ci95": _paired_ci(values)}


def _wilson(k, n):
    if n == 0:
        return None
    z, ph = 1.96, k / n
    c = (ph + z * z / (2 * n)) / (1 + z * z / n)
    r = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [c - r, c + r]


def _calibration(points):
    bins = defaultdict(list)
    for p, y in points:
        bins[min(9, int(p * 10))].append((p, y))
    return [{"bin": f"{b/10:.1f}-{(b+1)/10:.1f}", "n": len(v),
             "mean_model_p": mean(p for p, _ in v), "observed_rate": mean(y for _, y in v),
             "observed_wilson95": _wilson(sum(y for _, y in v), len(v))}
            for b, v in sorted(bins.items())]


def _walkforward_rows(graded, family):
    rows = []
    for card, r, fin in graded:
        p = r["projection"]
        rc = card["ratings_receipt"] or {}
        src = {"sha256": str(rc.get("sha256", "")).removeprefix("sha256:"),
               "captured_utc": rc.get("observed_utc")}
        pred = {"status": "PAPER_NON_COUNTED_UNCALIBRATED", "official": False, "stake_u": 0,
                "game_id": r["game_id"], "season": int(r["season"]),
                "home_team_id": r["home_team_id"], "away_team_id": r["away_team_id"],
                "freeze_utc": card["freeze_utc"], "tipoff_utc": r["tipoff_utc"],
                "model_sha256": card["model_code_sha256"],
                "source_clock_consistent_not_authenticated": {"home": src, "away": src, "league": src},
                "home_points": p["home_points"], "away_points": p["away_points"],
                "margin_home": p["home_points"] - p["away_points"],
                "total": p["home_points"] + p["away_points"]}
        m = next((x for x in r["markets"] if x["market"] == family and
                  x["status"] == "PRICED_PAPER"), None)
        quote = None
        if m is not None:
            q = m["quote"]
            quote = {"game_id": r["game_id"], "season": int(r["season"]), "period": "FG",
                     "book": q["book"], "captured_utc": q["captured_utc"],
                     "sha256": sha(canonical_bytes(q))}
            if family == "spread":
                quote.update(home_spread=q["line"], home_price=q["price_a"], away_price=q["price_b"])
            elif family == "total":
                quote.update(total_line=q["line"], over_price=q["price_a"], under_price=q["price_b"])
            else:
                quote.update(home_ml=q["price_a"], away_ml=q["price_b"])
        rows.append({"prediction": pred, "final": fin["final"], "quote": quote})
    return rows


# Percent-on-model form of the single canonical grid in cbb_pricing.OWNER_BLEND_WEIGHTS
# (100/0, 87.5/12.5, ... 0/100). Not a second definition.
BLEND_GRID = tuple(100 * w for w in OWNER_BLEND_WEIGHTS)

def nine_weight_comparison(pairs):
    """Paired frozen probabilities only. No weight selection or refitting.
    Each tuple is (unconditional model side A, push, conditional no-vig A, outcome).
    Conditional Brier/log loss excludes actual pushes for ALL weights equally.
    """
    result = []
    for weight in BLEND_GRID:
        values = []
        for pm, push, pk, y in pairs:
            if not all(type(x) in (int, float) and math.isfinite(x) for x in (pm, push, pk)):
                raise LedgerError("BLEND_GRID_NONFINITE")
            if not (0 <= push < 1 and 0 <= pm <= 1 - push + 1e-12 and 0 <= pk <= 1
                    and type(y) is int and y in (0, 1)):
                raise LedgerError("BLEND_GRID_INVALID")
            p = (weight / 100) * min(1.0, pm / (1 - push)) + (1 - weight / 100) * pk
            values.append(((p-y)**2, _ll(p, y)))
        result.append({"weight_model_pct": weight, "n": len(values),
                       "brier": mean(v[0] for v in values) if values else None,
                       "logloss": mean(v[1] for v in values) if values else None})
    return result


def evaluate(entries, *, min_prior=30, max_quote_age_hours=24):
    finals = _done(entries, "FINAL_ATTACHED")
    closes = _done(entries, "CLOSE_QUOTE")
    order = sorted(_card_rows(entries), key=lambda cr: (cr[0]["freeze_utc"], cr[1]["tipoff_utc"],
                                                   cr[1]["game_id"]))
    census, pass_reasons, results = Counter(), Counter(), Counter()
    acc = defaultdict(list)
    calib = defaultdict(list)
    blend_pairs = defaultdict(list)
    returns = defaultdict(list)
    clv = defaultdict(list)
    graded_projected, residuals, by_date = [], [], defaultdict(Counter)
    for card, r in order:
        census["card_rows"] += 1
        fin = finals.get(r["game_id"], {}).get(None)
        if fin is not None and fin["card_sha256"] != card["card_sha256"]:
            fin = None  # a final attaches to exactly one frozen card row
        if r["status"] == "PASS":
            pass_reasons[r["pass_reason"].split(":")[0]] += 1
        if fin is None:
            census["pending_final"] += 1
            continue
        census["graded_rows"] += 1
        f = fin["final"]
        margin, total = f["home_score"] - f["away_score"], f["home_score"] + f["away_score"]
        for g in fin["grades"]:
            results[(g["market"], g["paper_result"])] += 1
        if r["status"] != "PROJECTED":
            continue
        p = r["projection"]
        graded_projected.append((card, r, fin))
        residuals.append({"game_id": r["game_id"], "final_captured_utc": f["captured_utc"],
                          "margin_residual": margin - p["margin"],
                          "total_residual": total - p["total"]})
        acc["margin_abs_error_model"].append(abs(margin - p["margin"]))
        acc["total_abs_error_model"].append(abs(total - p["total"]))
        day = card["freeze_utc"][:10]
        for m, g in zip(r["markets"], fin["grades"]):
            if m["status"] != "PRICED_PAPER":
                continue
            a, b = m["sides"]
            q = m["quote"]
            if m["market"] == "spread":
                acc["spread_mae_pairs"].append((abs(margin - p["margin"]), abs(margin + q["line"])))
            if m["market"] == "total":
                acc["total_mae_pairs"].append((abs(total - p["total"]), abs(total - q["line"])))
            if g["outcome"] != "push":
                y = int(g["outcome"] == a)
                denom = 1 - m["model_prob"]["push"]
                pm = m["model_prob"][a] / denom if denom > 0 else 0.5
                pk = m["market_novig_prob"][a]
                acc[m["market"] + "_brier"].append(((pm - y) ** 2, (pk - y) ** 2))
                acc[m["market"] + "_logloss"].append((_ll(pm, y), _ll(pk, y)))
                calib[m["market"]].append((pm, y))
                if denom > 0:
                    blend_pairs[m["market"]].append((m["model_prob"][a], m["model_prob"]["push"], pk, y))
                by_date[day][m["market"] + "_n"] += 1
            if g["hypothetical_flat_1u_return"] is not None:
                returns[m["market"]].append(g["hypothetical_flat_1u_return"])
                side = g["paper_selection"]
                c = closes.get(r["game_id"], {}).get(m["market"])
                if c is None:
                    census["clv_no_close:" + m["market"]] += 1
                elif c["quote"]["line"] != q["line"]:
                    census["clv_line_moved_not_comparable:" + m["market"]] += 1
                else:
                    cq = c["quote"]
                    ca, cb, _ = no_vig(cq["price_a"], cq["price_b"])
                    close_p = ca if side == a else cb
                    open_p = m["market_novig_prob"][side]
                    clv[m["market"]].append(close_p - open_p)
    wf = {fam: walkforward_audit(_walkforward_rows(graded_projected, fam), min_prior=min_prior,
                                 max_quote_age_hours=max_quote_age_hours)
          for fam in MARKETS} if graded_projected else None
    strip = ("rows",)
    return {
        "status": "CBBD_PAPER_LEDGER_EVALUATION_PAPER_0U_NOT_VALIDATION",
        "official_counted": 0, "approved_stake_u": 0,
        "census": dict(sorted(census.items())),
        "card_pass_reasons": dict(sorted(pass_reasons.items())),
        "forecast_accuracy": {
            "model_margin_mae": _mean_ci(acc["margin_abs_error_model"]),
            "model_total_mae": _mean_ci(acc["total_abs_error_model"]),
            "spread_mae_vs_same_time_market": _pair_summary(acc["spread_mae_pairs"], "MAE_POINTS"),
            "total_mae_vs_same_time_market": _pair_summary(acc["total_mae_pairs"], "MAE_POINTS"),
            **{f"{mk}_{k}": _pair_summary(acc[f"{mk}_{k}"], k.upper())
               for mk in MARKETS for k in ("brier", "logloss")},
            "calibration_side_a": {mk: _calibration(calib[mk]) for mk in MARKETS},
            "per_freeze_date_counts": {d: dict(c) for d, c in sorted(by_date.items())},
        },
        "nine_weight_same_book_comparison": {
            "label": "FIXED_GRID_DESCRIPTIVE_ONLY_NOT_EXTERNAL_CONSENSUS_OR_WEIGHT_SELECTION",
            "conditional_on_no_push": True,
            "families": {mk: nine_weight_comparison(blend_pairs[mk]) for mk in MARKETS},
        },
        "paper_returns_separate_from_accuracy": {
            "result_counts": {f"{k[0]}:{k[1]}": v for k, v in sorted(results.items())},
            "hypothetical_flat_1u_return_per_selection": {mk: _mean_ci(returns[mk]) for mk in MARKETS},
            "clv_novig_prob_close_minus_open": {mk: _mean_ci(clv[mk]) for mk in MARKETS},
        },
        "walkforward_reuse_point_in_time_score_walkforward": None if wf is None else {
            fam: {k: v for k, v in rep.items() if k not in strip} for fam, rep in wf.items()},
        "prospective_residuals": residuals,
        "warnings": [
            "PAPER_0U_NOT_PREDICTIVE_VALIDATION; CI ONLY WHEN n>=30 (NORMAL APPROX)",
            "RETURNS_ARE_HYPOTHETICAL_FLAT_1U_PAPER_NOT_WAGERS",
            "CLV_ONLY_SAME_LINE_CLOSE_CAPTURED_BEFORE_TIP; LOCAL CLOCKS NOT PROVIDER ATTESTED",
            "QUOTES_AND_FINALS_NOT_INDEPENDENTLY_AUTHENTICATED",
        ],
    }


# ---------------------------------------------------------------- CLI

def _private_report(path, obj):
    from cbbd_prospective_capture import _private_directory, _private_create
    out = safe_path(path)
    if out.exists():
        raise FileExistsError("CREATE_ONLY_REPORT_EXISTS")
    _private_directory(out.parent)
    _private_create(out, (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append-card"); a.add_argument("ledger"); a.add_argument("card")
    f = sub.add_parser("attach-finals"); f.add_argument("ledger"); f.add_argument("finals")
    f.add_argument("--provider-raw", required=True); f.add_argument("--provider-manifest", required=True)
    c = sub.add_parser("append-close"); c.add_argument("ledger"); c.add_argument("quotes_json")
    e = sub.add_parser("evaluate"); e.add_argument("ledger"); e.add_argument("--report", required=True)
    e.add_argument("--residuals-out")
    args = p.parse_args(argv)
    try:
        if args.cmd == "append-card":
            card, _ = _load(args.card)
            out = append(args.ledger, card_entries(card))
        elif args.cmd == "attach-finals":
            fin, _ = _load(args.finals)
            out = append(args.ledger, final_entries(fin, safe_path(args.provider_raw),
                                                    safe_path(args.provider_manifest)))
        elif args.cmd == "append-close":
            rows, _ = _load(args.quotes_json)
            if not isinstance(rows, list):
                raise LedgerError("CLOSE_QUOTES_NOT_LIST")
            out = append(args.ledger, close_entries(rows))
        else:
            rep = evaluate(read(args.ledger))
            _private_report(args.report, rep)
            if args.residuals_out:
                _private_report(args.residuals_out, rep["prospective_residuals"])
            out = {"state": "EVALUATED", "census": rep["census"],
                   "official_counted": 0, "approved_stake_u": 0}
    except (LedgerError, Pass, Blocked) as exc:
        print("CBBD_LEDGER_BLOCKED:" + str(exc)[:160])
        return 2
    except (ValueError, OSError) as exc:
        print("CBBD_LEDGER_BLOCKED:" + type(exc).__name__)
        return 2
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
