"""Daily CFB PAPER card: freeze forecasts + quotes BEFORE kickoff. PAPER / 0u only.

For each game on the capture week the card stores either both baseline
forecasts (frozen RUN IT and ratings-only SP+) or explicit PASS / HOLD
reasons, the model versions and pinned hashes, the normalized input hashes,
and every eligible full two-sided quote (book, line, both prices,
captured_utc, source hash). Each quote carries the no-vig market probability
and, per model, model probability and EV at the actual price.

Quotes come from an operator CSV / JSON file or from an Odds API v4 archive
written by ``sportsedge.odds.free_odds_aggregator_intake`` (sport CFB) plus an
exact operator crosswalk of provider event IDs to CFBD game IDs.
``sportsedge/odds/daily_main_odds.py`` is an NFL-only pilot and is NOT used.

The card is written once (O_EXCL), hashed, and registered in the
append-only ledger. EV here is computed from UNVALIDATED models: it is not an
edge claim, not a recommendation, and every row is PAPER with
official_counted=0 and approved_stake_u=0.
"""
from __future__ import annotations

import argparse
import csv
from datetime import timezone
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import sys

from models.cfb import cfb_baselines as baselines
from models.cfb import cfb_capture_store as store
from models.cfb import cfb_ledger as ledger
from models.cfb import cfb_pregame_assembler as assembler
from models.cfb.cfb_capture_store import CaptureRefused, utc, stamp

CARD_SCHEMA = "sportsedge-cfb-paper-card-v1"
QUOTE_SCHEMA = "sportsedge-cfb-operator-quotes-v1"
CROSSWALK_SCHEMA = "sportsedge-cfb-odds-event-crosswalk-v1"
MARKETS = ("ML", "SPREAD", "TOTAL")
SIDES = {"ML": ("HOME", "AWAY"), "SPREAD": ("HOME", "AWAY"), "TOTAL": ("OVER", "UNDER")}
PAPER = {"state": "PAPER", "stake_u": 0, "official_counted": 0, "approved_stake_u": 0,
         "predictive_validation": False, "edge_verified": False}


class QuoteRefused(ValueError):
    pass


# ------------------------------------------------------------------ odds math
def american(price):
    if isinstance(price, bool) or not isinstance(price, int) or abs(price) < 100 or abs(price) > 100000:
        raise QuoteRefused("AMERICAN_PRICE_INVALID")
    return price


def decimal_odds(price):
    american(price)
    return 1 + (price / 100 if price > 0 else 100 / -price)


def novig(price_a, price_b):
    ia, ib = 1 / decimal_odds(price_a), 1 / decimal_odds(price_b)
    return ia / (ia + ib), ib / (ia + ib), ia + ib - 1  # p_a, p_b, overround


# ------------------------------------------------------------------ quote intake
def _quote(row, *, source, source_sha256):
    gid = row.get("cfbd_game_id")
    if isinstance(gid, str) and gid.isdecimal():
        gid = int(gid)
    if type(gid) is not int or gid <= 0:
        raise QuoteRefused("QUOTE_GAME_ID_INVALID")
    market = row.get("market")
    if market not in MARKETS:
        raise QuoteRefused("QUOTE_MARKET_OUT_OF_SCOPE")
    book = row.get("book")
    if not isinstance(book, str) or not book.strip():
        raise QuoteRefused("QUOTE_BOOK_REQUIRED")
    a_key, b_key = ("over_price", "under_price") if market == "TOTAL" else ("home_price", "away_price")
    pa, pb = _int(row.get(a_key)), _int(row.get(b_key))
    if pa is None or pb is None:
        raise QuoteRefused("QUOTE_NOT_TWO_SIDED")
    american(pa), american(pb)
    line = row.get("line")
    if market == "ML":
        if line not in (None, ""):
            raise QuoteRefused("ML_QUOTE_HAS_LINE")
        line = None
    else:
        line = _float(line)
        if line is None or abs(line) > 200 or (market == "TOTAL" and line <= 0):
            raise QuoteRefused("QUOTE_LINE_INVALID")
    captured = utc(row.get("captured_utc"), "quote_captured_utc")
    q = {"cfbd_game_id": gid, "book": book.strip(), "market": market, "line": line,
         "price_a": pa, "price_b": pb, "side_a": SIDES[market][0], "side_b": SIDES[market][1],
         "captured_utc": stamp(captured), "source": source, "source_sha256": source_sha256,
         "provider_last_update_utc": row.get("provider_last_update_utc")}
    q["quote_id"] = sha256(store_canon(q)).hexdigest()[:24]
    return q


def store_canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("+-").isdecimal():
        return int(v.strip())
    return None


def _float(v):
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def load_operator_quotes(raw: bytes, *, name="operator_quotes"):
    """CSV with a header row, or JSON {schema, rows}. Bad rows refuse the whole file."""
    digest = "sha256:" + sha256(raw).hexdigest()
    text = raw.decode("utf-8-sig")
    if text.lstrip().startswith("{"):
        doc = store.strict_json(raw)
        if not isinstance(doc, dict) or doc.get("schema") != QUOTE_SCHEMA or not isinstance(doc.get("rows"), list):
            raise QuoteRefused("OPERATOR_QUOTE_SCHEMA")
        rows = doc["rows"]
    else:
        rows = list(csv.DictReader(io.StringIO(text, newline="")))
    return [_quote(r, source="operator:" + name, source_sha256=digest) for r in rows]


def load_odds_api_archive(raw: bytes, summary: dict, crosswalk: dict):
    """Odds API v4 CFB archive -> two-sided quotes, joined only via the exact crosswalk."""
    digest = "sha256:" + sha256(raw).hexdigest()
    if (not isinstance(summary, dict) or summary.get("sport") != "CFB"
            or summary.get("original_raw_sha256") != digest):
        raise QuoteRefused("ODDS_ARCHIVE_SCOPE_OR_SHA_MISMATCH")
    if not isinstance(crosswalk, dict) or crosswalk.get("schema") != CROSSWALK_SCHEMA:
        raise QuoteRefused("CROSSWALK_SCHEMA")
    xw = {}
    for r in crosswalk.get("rows", []):
        eid = r.get("odds_event_id")
        if eid in xw or type(r.get("cfbd_game_id")) is not int:
            raise QuoteRefused("CROSSWALK_DUPLICATE_OR_INVALID")
        xw[eid] = r
    if len({r["cfbd_game_id"] for r in xw.values()}) != len(xw):
        raise QuoteRefused("CROSSWALK_GAME_MAPPED_TWICE")
    captured = summary.get("captured_utc")
    captured = stamp(utc(captured.replace("+00:00", "Z"))) if isinstance(captured, str) else None
    if captured is None:
        raise QuoteRefused("ODDS_ARCHIVE_CAPTURE_CLOCK_MISSING")
    events = store.strict_json(raw)
    events = [events] if isinstance(events, dict) else events
    out = []
    for ev in events:
        if ev.get("sport_key") != "americanfootball_ncaaf":
            raise QuoteRefused("ODDS_SPORT_KEY_NOT_CFB")
        x = xw.get(ev.get("id"))
        if x is None:
            continue
        if ev.get("home_team") != x.get("home_team_odds_name") or ev.get("away_team") != x.get("away_team_odds_name"):
            raise QuoteRefused("CROSSWALK_TEAM_NAME_MISMATCH")
        H, A = ev["home_team"], ev["away_team"]
        for book in ev.get("bookmakers", []):
            for m in book.get("markets", []):
                oc = {o.get("name"): o for o in m.get("outcomes", [])}
                row = {"cfbd_game_id": x["cfbd_game_id"], "book": book.get("key"), "captured_utc": captured,
                       "provider_last_update_utc": m.get("last_update") or book.get("last_update")}
                if m.get("key") == "h2h" and H in oc and A in oc:
                    row.update(market="ML", home_price=oc[H].get("price"), away_price=oc[A].get("price"))
                elif m.get("key") == "spreads" and H in oc and A in oc:
                    hp, ap = _float(oc[H].get("point")), _float(oc[A].get("point"))
                    if hp is None or ap is None or hp != -ap:
                        continue
                    row.update(market="SPREAD", line=hp, home_price=oc[H].get("price"), away_price=oc[A].get("price"))
                elif m.get("key") == "totals" and "Over" in oc and "Under" in oc:
                    op, up = _float(oc["Over"].get("point")), _float(oc["Under"].get("point"))
                    if op is None or op != up:
                        continue
                    row.update(market="TOTAL", line=op, over_price=oc["Over"].get("price"),
                               under_price=oc["Under"].get("price"))
                else:
                    continue
                out.append(_quote(row, source="the-odds-api.com:aggregator", source_sha256=digest))
    return out


def eligible_quotes(quotes, gid, kickoff, frozen):
    """Latest two-sided quote per (book, market) captured at/before freeze and kickoff."""
    best = {}
    for q in quotes:
        if q["cfbd_game_id"] != gid:
            continue
        t = utc(q["captured_utc"])
        if t > frozen or t >= kickoff:
            continue
        key = (q["book"], q["market"])
        if key not in best or t > utc(best[key]["captured_utc"]):
            best[key] = q
    return [best[k] for k in sorted(best)]


# ------------------------------------------------------------------ pricing
def model_side_probs(fc, q):
    if q["market"] == "ML":
        p = fc["p_home_win"]
    elif q["market"] == "SPREAD":
        # line is the HOME handicap: home covers when margin + line > 0.
        p = baselines.p_greater(fc["margin_home"], -q["line"], fc["sd_margin"])
    else:
        p = baselines.p_greater(fc["total"], q["line"], fc["sd_total"])
    return p, 1 - p


def price_quote(q, forecasts):
    na, nb, vig = novig(q["price_a"], q["price_b"])
    row = {**q, "market_novig_a": round(na, 6), "market_novig_b": round(nb, 6), "overround": round(vig, 6),
           "models": {}, **PAPER}
    for mid, fc in forecasts.items():
        if fc["status"] != "PROJECTED":
            row["models"][mid] = {"status": "PASS"}
            continue
        pa, pb = model_side_probs(fc, q)
        eva, evb = pa * decimal_odds(q["price_a"]) - 1, pb * decimal_odds(q["price_b"]) - 1
        lean = None
        if max(eva, evb) > 0:
            lean = q["side_a"] if eva >= evb else q["side_b"]
        row["models"][mid] = {"status": "PRICED", "p_model_a": round(pa, 6), "p_model_b": round(pb, 6),
                              "ev_a": round(eva, 6), "ev_b": round(evb, 6),
                              "paper_lean_unvalidated": lean}
    return row


# ------------------------------------------------------------------ card build / freeze
def build_card(capture_dir, *, frozen_utc, quotes=(), ratings_dirs=(), weather_dir=None) -> dict:
    frozen = utc(frozen_utc, "frozen_utc")
    frozen_version = baselines.verify_frozen_model()
    ratings_version = baselines.ratings_only_version()
    fid, rid = frozen_version["model_id"], ratings_version["model_id"]
    quotes = list(quotes)
    # Quote hashes per game/family feed the PIT contract's market census.
    prelim = {}
    for q in quotes:
        if utc(q["captured_utc"]) <= frozen:
            prelim.setdefault(q["cfbd_game_id"], {}).setdefault(q["market"], q["source_sha256"].split(":")[-1])
    slate = assembler.assemble_slate(capture_dir, frozen_utc=frozen_utc, ratings_dirs=ratings_dirs,
                                     weather_dir=weather_dir, quote_receipts=prelim)
    games = []
    for rec in slate["games"]:
        model = rec.pop("_model", None)
        kickoff = utc(rec["kickoff_utc"])
        if rec["status"] == "READY":
            try:
                ff = baselines.frozen_runit_forecast(model["game_row"], model["ctx"])
            except (KeyError, ValueError, ZeroDivisionError, TypeError) as exc:
                ff = baselines.pass_forecast(fid, ["FROZEN_MODEL_ERROR:" + type(exc).__name__])
            rf = baselines.ratings_only_forecast(model["sp_home"], model["sp_away"],
                                                 neutral=rec["neutral_site"], means=model["sp_means"])
        else:
            reasons = [rec["status"] + ":" + r for r in rec["reasons"]]
            ff, rf = baselines.pass_forecast(fid, reasons), baselines.pass_forecast(rid, reasons)
        forecasts = {fid: ff, rid: rf}
        priced = [price_quote(q, forecasts) for q in eligible_quotes(quotes, rec["cfbd_game_id"], kickoff, frozen)]
        missing = sorted(set(MARKETS) - {q["market"] for q in priced})
        games.append({**rec, "forecasts": forecasts, "quotes": priced,
                      "markets_without_prefreeze_quote": missing,
                      "market_status": "QUOTED" if priced else "NO_QUOTE", **PAPER})
    card = {"schema": CARD_SCHEMA, "sport": "CFB", "season": slate["season"], "week": slate["week"],
            "season_type": slate["season_type"], "frozen_utc": stamp(frozen),
            "models": {fid: frozen_version, rid: ratings_version},
            "source_receipts": slate["source_receipts"],
            "quote_sources": sorted({q["source_sha256"] for q in quotes}),
            "games": games,
            "counts": {s: sum(g["status"] == s for g in games) for s in ("READY", "HOLD", "PASS")},
            "disclaimer": ("PAPER ONLY. Untested models; EV is not a verified edge. Passing tests is not "
                           "predictive validation."),
            **PAPER}
    for g in games:
        if g["status"] != "READY" and all(f["status"] != "PASS" for f in g["forecasts"].values()):
            raise AssertionError("NON_READY_GAME_WITHOUT_PASS")
    return card


def freeze_card(card: dict, out_dir, ledger_path, *, now=None) -> dict:
    """Write the card once, then register its sha256 in the append-only ledger."""
    now = now or store.now_utc()
    if now > utc(card["frozen_utc"]) + _grace():
        raise CaptureRefused("CARD_WRITTEN_TOO_LONG_AFTER_FREEZE")
    d = store.private_dir(out_dir, create=True)
    body = (json.dumps(card, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    digest = sha256(body).hexdigest()
    name = f"cfb_card_{card['season']}_wk{card['week']:02d}_{card['frozen_utc'].replace(':', '')}_{digest[:12]}.json"
    store.write_exclusive(d / name, body)
    store.write_exclusive(d / (name[:-5] + ".md"), render_md(card).encode())
    entry = ledger.append(ledger_path, {
        "type": "CARD_FROZEN", "card_file": name, "card_sha256": digest,
        "card_frozen_utc": card["frozen_utc"], "season": card["season"], "week": card["week"],
        "game_ids": [g["cfbd_game_id"] for g in card["games"]],
        "first_kickoff_utc": min((g["kickoff_utc"] for g in card["games"]), default=None),
    }, now=now)
    return {"card_file": str(d / name), "card_sha256": digest, "ledger_seq": entry["seq"], **PAPER}


def _grace():
    from datetime import timedelta
    return timedelta(minutes=10)


def render_md(card) -> str:
    out = [f"# CFB PAPER card {card['season']} week {card['week']} (frozen {card['frozen_utc']})", "",
           "PAPER ONLY / 0u. Untested models; EV is not a verified edge.", ""]
    for g in card["games"]:
        out.append(f"## {g['away_team']} @ {g['home_team']} ({g['kickoff_utc']}) [{g['status']}]")
        if g["status"] != "READY":
            out.append("- Reasons: " + ", ".join(g["reasons"]))
        for mid, f in g["forecasts"].items():
            if f["status"] == "PROJECTED":
                out.append(f"- {mid}: margin {f['margin_home']:+.1f} total {f['total']:.1f} "
                           f"P(home) {f['p_home_win']:.3f}")
        for q in g["quotes"]:
            line = "" if q["line"] is None else (f" {q['line']:g}" if q["market"] == "TOTAL" else f" {q['line']:+g}")
            out.append(f"  - {q['book']} {q['market']}{line} {q['price_a']:+d}/{q['price_b']:+d} "
                       f"no-vig {q['market_novig_a']:.3f} @ {q['captured_utc']}")
        if not g["quotes"]:
            out.append("  - NO_QUOTE")
        out.append("")
    return "\n".join(out) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("capture_dir")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--ratings-dir", action="append", default=[])
    p.add_argument("--weather-dir")
    p.add_argument("--operator-quotes", action="append", default=[])
    p.add_argument("--odds-archive", nargs=3, action="append", default=[],
                   metavar=("RAW", "SUMMARY", "CROSSWALK"))
    a = p.parse_args(argv)
    frozen = stamp(store.now_utc().replace(microsecond=0))
    try:
        quotes = []
        for path in a.operator_quotes:
            quotes += load_operator_quotes(store.read_private(Path(path)), name=Path(path).stem)
        for raw, summ, xw in a.odds_archive:
            quotes += load_odds_api_archive(store.read_private(Path(raw)),
                                            store.strict_json(store.read_private(Path(summ))),
                                            store.strict_json(store.read_private(Path(xw))))
        card = build_card(a.capture_dir, frozen_utc=frozen, quotes=quotes,
                          ratings_dirs=a.ratings_dir, weather_dir=a.weather_dir)
        res = freeze_card(card, a.out_dir, a.ledger)
    except (CaptureRefused, QuoteRefused, baselines.ModelRefused, ledger.LedgerRefused, OSError) as exc:
        print("CFB_CARD_BLOCKED " + (str(exc) if not isinstance(exc, OSError) else "OS_ERROR"), file=sys.stderr)
        return 2
    print(json.dumps({"card_sha256": res["card_sha256"], "counts": card["counts"], **PAPER}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
