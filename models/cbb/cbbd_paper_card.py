"""Daily CBBD-native CBB paper card: freeze forecast + quote BEFORE tipoff.

Every slate game receives either a projection or an explicit PASS reason.
Markets: full-game moneyline, spread, total only. The market is no-vigged
and the model probability, market probability and EV at the ACTUAL price are
reported, all labelled PAPER / 0u (official_counted=0, approved_stake_u=0).
A positive paper EV is NOT verified +EV; nothing here is a recommendation.

Quote intake (both normalised to one two-sided row per book/market):
* operator CSV/JSON: game_id, market, book, line, price_a, price_b, captured_utc
  (spread line = HOME line, price_a = home/over, price_b = away/under);
* an Odds API archive written by ``sportsedge.odds.free_odds_aggregator_intake``
  (which supports ``basketball_ncaab``) plus an operator crosswalk that maps
  each provider event ID to an exact CBBD game ID and the provider's exact
  home/away names. No fuzzy matching: unmapped events are counted, never used.
``sportsedge.odds.daily_main_odds`` is NFL-only and is not used for CBB.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path

from cbbd_native_score_model import (
    MODEL_CODE_SHA256, MODEL_VERSION, Pass, canonical_id, decimal_odds,
    ev_per_unit, fit_context, market_probs, no_vig, project, season_of, stamp, utc,
)
from cbbd_prospective_capture import safe_path, _private_directory, _private_create
from sportsedge.validation.cbb_venue_registry import verify_cbb_venue
from sportsedge.validation.daily_ratings_capture import eligible_bytes

CARD_SCHEMA = "sportsedge-cbbd-paper-card-v1"
CARD_STATUS = "CBBD_PAPER_CARD_PAPER_0U_UNVALIDATED"
BUILDER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
MARKETS = ("moneyline", "spread", "total")
RATINGS_SOURCE = "cbbd_ratings_adjusted"
SLATE_COLUMNS = ("game_id", "season", "tipoff_utc", "home_team_id",
                 "away_team_id", "neutral")
QUOTE_COLUMNS = ("game_id", "market", "book", "line", "price_a", "price_b",
                 "captured_utc")
CROSSWALK_COLUMNS = ("odds_event_id", "game_id", "odds_home_team", "odds_away_team")
PAPER = {"label": "PAPER", "stake_u": 0, "official_counted": 0, "approved_stake_u": 0}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def card_digest(card):
    return sha(canonical_bytes({k: v for k, v in card.items() if k != "card_sha256"}))


def _csv_rows(raw, columns, kind):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    if tuple(reader.fieldnames or ()) != columns:
        raise Pass(kind + "_CSV_SCHEMA_INVALID")
    rows = []
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise Pass(kind + "_CSV_ROW_INVALID")
        rows.append(row)
    return rows


def _json_loads(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise Pass("DUPLICATE_JSON_KEY")
            out[k] = v
        return out

    def bad(_):
        raise Pass("NONFINITE_JSON")
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=bad)


# ---------------------------------------------------------------- quotes

def _num_or_none(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise Pass("LINE_INVALID")
    try:
        f = float(value)
    except (TypeError, ValueError) as exc:
        raise Pass("LINE_INVALID") from exc
    if not math.isfinite(f):
        raise Pass("LINE_INVALID")
    return f


def _price(value):
    if isinstance(value, str) and value.strip().lstrip("+-").isdecimal():
        value = int(value.strip())
    decimal_odds(value)  # validates type and range
    return value


def normalise_quote(row, source):
    """One complete two-sided full-game quote, or raise Pass."""
    if not isinstance(row, dict):
        raise Pass("QUOTE_NOT_OBJECT")
    gid = canonical_id(row.get("game_id"))
    if gid is None:
        raise Pass("QUOTE_GAME_ID_NONCANONICAL")
    market = row.get("market")
    if market not in MARKETS:
        raise Pass("QUOTE_MARKET_UNSUPPORTED")
    book = row.get("book")
    if not isinstance(book, str) or not book.strip() or book != book.strip():
        raise Pass("QUOTE_BOOK_INVALID")
    line = _num_or_none(row.get("line"))
    if market == "moneyline" and line is not None:
        raise Pass("MONEYLINE_HAS_LINE")
    if market == "spread" and (line is None or not -60 <= line <= 60 or (line * 2) % 1):
        raise Pass("SPREAD_LINE_INVALID")
    if market == "total" and (line is None or not 80 <= line <= 220 or (line * 2) % 1):
        raise Pass("TOTAL_LINE_INVALID")
    try:
        pa, pb = _price(row.get("price_a")), _price(row.get("price_b"))
    except Pass as exc:
        raise Pass("QUOTE_PRICE_NOT_TWO_SIDED_AMERICAN") from exc
    captured = utc(row.get("captured_utc"), "quote.captured_utc")
    return {"game_id": gid, "market": market, "book": book, "line": line,
            "price_a": pa, "price_b": pb, "captured_utc": stamp(captured),
            "source": source}


def operator_quotes(raw, kind):
    """Operator-supplied lines as CSV or JSON list (exact columns)."""
    if kind == "csv":
        rows = _csv_rows(raw, QUOTE_COLUMNS, "QUOTE")
    else:
        rows = _json_loads(raw)
        if not isinstance(rows, list):
            raise Pass("QUOTE_JSON_NOT_A_LIST")
    return rows


def odds_api_quotes(raw, manifest, crosswalk_raw):
    """Odds API CBB archive -> quote rows via an EXACT operator crosswalk."""
    if not isinstance(manifest, dict) or manifest.get("sport") != "CBB" or \
            manifest.get("schema") != "sportsedge-oddsapi-aggregator-raw-v1":
        raise Pass("ODDS_API_MANIFEST_NOT_CBB")
    if manifest.get("original_raw_sha256") != "sha256:" + sha(raw):
        raise Pass("ODDS_API_RAW_HASH_MISMATCH")
    try:
        captured = datetime.fromisoformat(manifest.get("captured_utc"))
    except (TypeError, ValueError) as exc:
        raise Pass("ODDS_API_CAPTURE_CLOCK_INVALID") from exc
    if captured.utcoffset() != timedelta(0):
        raise Pass("ODDS_API_CAPTURE_CLOCK_INVALID")
    cap = stamp(captured)
    xw = {}
    for r in _csv_rows(crosswalk_raw, CROSSWALK_COLUMNS, "CROSSWALK"):
        if r["odds_event_id"] in xw or canonical_id(r["game_id"]) is None:
            raise Pass("CROSSWALK_DUPLICATE_OR_NONCANONICAL")
        xw[r["odds_event_id"]] = r
    if len({r["game_id"] for r in xw.values()}) != len(xw):
        raise Pass("CROSSWALK_GAME_ID_NOT_ONE_TO_ONE")
    events = _json_loads(raw)
    if not isinstance(events, list):
        raise Pass("ODDS_API_EVENTS_NOT_LIST")
    rows, census = [], Counter()
    for ev in events:
        m = xw.get(ev.get("id")) if isinstance(ev, dict) else None
        if m is None:
            census["UNMAPPED_PROVIDER_EVENT"] += 1
            continue
        if ev.get("home_team") != m["odds_home_team"] or ev.get("away_team") != m["odds_away_team"]:
            census["CROSSWALK_TEAM_ORIENTATION_MISMATCH"] += 1
            continue
        home, away = ev["home_team"], ev["away_team"]
        for book in ev.get("bookmakers") or ():
            for mk in book.get("markets") or ():
                by = {}
                for o in mk.get("outcomes") or ():
                    by.setdefault(o.get("name"), []).append(o)
                key = mk.get("key")
                try:
                    if key == "h2h":
                        a, b, market, line = by[home], by[away], "moneyline", None
                    elif key == "spreads":
                        a, b, market = by[home], by[away], "spread"
                        line = a[0].get("point")
                        if len(a) != 1 or len(b) != 1 or b[0].get("point") != -line:
                            raise KeyError
                    elif key == "totals":
                        a, b, market = by["Over"], by["Under"], "total"
                        line = a[0].get("point")
                        if len(a) != 1 or len(b) != 1 or b[0].get("point") != line:
                            raise KeyError
                    else:
                        census["MARKET_NOT_IN_SCOPE"] += 1
                        continue
                    if len(a) != 1 or len(b) != 1:
                        raise KeyError
                except (KeyError, TypeError, IndexError):
                    census["NOT_TWO_SIDED_OR_LINES_DISAGREE"] += 1
                    continue
                rows.append({"game_id": m["game_id"], "market": market,
                             "book": book.get("key"), "line": line,
                             "price_a": a[0].get("price"), "price_b": b[0].get("price"),
                             "captured_utc": cap})
    return rows, dict(census)


def select_quotes(candidates, freeze, *, max_age_hours):
    """Per (game, market): latest pre-freeze complete quote; ties -> book name.

    Selection never looks at the model or EV. Conflicting copies of the same
    (game, market, book, captured_utc) quarantine every copy.
    """
    census, valid = Counter(), []
    for row, source in candidates:
        try:
            q = normalise_quote(row, source)
        except Pass as exc:
            census["rejected:" + str(exc)] += 1
            continue
        cap = utc(q["captured_utc"], "q")
        if cap > freeze:
            census["rejected:QUOTE_CAPTURED_AFTER_FREEZE"] += 1
            continue
        if (freeze - cap).total_seconds() > max_age_hours * 3600:
            census["rejected:QUOTE_STALE"] += 1
            continue
        valid.append(q)
    keys = Counter((q["game_id"], q["market"], q["book"], q["captured_utc"]) for q in valid)
    chosen = {}
    for q in valid:
        k = (q["game_id"], q["market"], q["book"], q["captured_utc"])
        if keys[k] > 1:
            census["rejected:CONFLICTING_DUPLICATE_QUOTE_ALL_COPIES"] += 1
            continue
        census["eligible"] += 1
        slot = (q["game_id"], q["market"])
        best = chosen.get(slot)
        if best is None or utc(q["captured_utc"], "q") > utc(best["captured_utc"], "q") or (
                q["captured_utc"] == best["captured_utc"] and q["book"] < best["book"]):
            chosen[slot] = q
    return chosen, dict(sorted(census.items()))


# ---------------------------------------------------------------- card

def _slate(raw):
    rows = _csv_rows(raw, SLATE_COLUMNS, "SLATE")
    return rows, Counter(r["game_id"] for r in rows)


def _registry_tips(raw):
    out = defaultdict(list)
    if raw is None:
        return out
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")):
        out[row.get("game_id")].append(row.get("tipoff_utc"))
    return out


def _price_market(proj, q):
    m = q["market"]
    pa, push, pb = market_probs(proj, m, q["line"])
    ma, mb, overround = no_vig(q["price_a"], q["price_b"])
    sides = {"moneyline": ("home", "away"), "spread": ("home", "away"),
             "total": ("over", "under")}[m]
    return {
        "market": m, "status": "PRICED_PAPER", "pass_reason": None,
        "quote": q, "sides": list(sides),
        "model_prob": {sides[0]: pa, "push": push, sides[1]: pb},
        "market_novig_prob": {sides[0]: ma, sides[1]: mb},
        "market_overround": overround,
        "paper_ev_per_1u_at_price": {sides[0]: ev_per_unit(pa, push, q["price_a"]),
                                     sides[1]: ev_per_unit(pb, push, q["price_b"])},
        **PAPER,
    }


def build_card(*, freeze_utc, built_utc, season, slate_path, registry_path,
               ratings_body, ratings_receipt, prior_games, quotes,
               prior_residuals=None, quote_census=None, input_sha256=None,
               max_quote_age_hours=24, max_ratings_age_hours=36, settings=None):
    """Pure card builder; file paths are only used for the venue gate."""
    freeze = utc(freeze_utc, "freeze_utc")
    built = utc(built_utc, "built_utc")
    if built < freeze:
        raise Pass("CARD_BUILT_BEFORE_DECLARED_FREEZE")
    if type(season) is not int or not 2000 <= season <= 2100:
        raise Pass("SEASON_INVALID")
    slate_raw = Path(slate_path).read_bytes()
    registry_raw = Path(registry_path).read_bytes() if registry_path else None
    slate, dup = _slate(slate_raw)
    reg_tips = _registry_tips(registry_raw)
    ctx, ctx_error = None, None
    try:
        body = eligible_bytes(ratings_body, ratings_receipt, source=RATINGS_SOURCE,
                              season=season, decision=freeze,
                              kickoff=freeze + timedelta(microseconds=1),
                              max_age_seconds=max_ratings_age_hours * 3600)
        ctx = fit_context(body, prior_games, season=season, freeze_utc=stamp(freeze),
                          prior_residuals=prior_residuals, settings=settings)
    except (Pass, ValueError) as exc:
        ctx_error = "RATINGS_OR_CONTEXT_NOT_ELIGIBLE_AT_FREEZE:" + str(exc)
    chosen, census = select_quotes(quotes, freeze, max_age_hours=max_quote_age_hours)
    rows = []
    for i, g in enumerate(slate):
        row = {"input_index": i, "game_id": g["game_id"], "season": g["season"],
               "tipoff_utc": g["tipoff_utc"], "home_team_id": g["home_team_id"],
               "away_team_id": g["away_team_id"], "neutral": None,
               "status": "PASS", "pass_reason": None, "projection": None,
               "markets": [], **PAPER}
        try:
            gid = canonical_id(g["game_id"])
            if gid is None:
                raise Pass("GAME_ID_NONCANONICAL")
            if dup[g["game_id"]] > 1:
                raise Pass("DUPLICATE_GAME_ID_ALL_COPIES")
            if not g["season"].isdecimal() or int(g["season"]) != season:
                raise Pass("WRONG_SEASON")
            tip = utc(g["tipoff_utc"], "tipoff_utc")
            if season_of(tip) != season:
                raise Pass("TIP_DATE_SEASON_MISMATCH")
            if not freeze < tip:
                raise Pass("TIPOFF_NOT_AFTER_FREEZE")
            if not built < tip:
                raise Pass("CARD_BUILT_AT_OR_AFTER_TIPOFF")
            home, away = canonical_id(g["home_team_id"]), canonical_id(g["away_team_id"])
            if home is None or away is None or home == away:
                raise Pass("UNMAPPED_CBBD_TEAM_ID")
            try:
                neutral = verify_cbb_venue(str(slate_path), str(registry_path), gid, freeze)
            except (ValueError, TypeError) as exc:
                raise Pass("NEUTRAL_SITE_UNVERIFIED:" + str(exc)) from None
            if reg_tips.get(gid) != [g["tipoff_utc"]]:
                raise Pass("VENUE_REGISTRY_TIPOFF_MISMATCH")
            row["neutral"] = neutral
            if ctx is None:
                raise Pass(ctx_error)
            proj = project(ctx, home, away, neutral=neutral)
        except Pass as exc:
            row["pass_reason"] = str(exc)
            row["markets"] = [{"market": m, "status": "PASS", "pass_reason": "GAME_PASS",
                               "quote": None, **PAPER} for m in MARKETS]
            rows.append(row)
            continue
        row.update(status="PROJECTED", projection=proj)
        for m in MARKETS:
            q = chosen.get((gid, m))
            if q is None:
                row["markets"].append({"market": m, "status": "PASS",
                                       "pass_reason": "MISSING_QUOTE", "quote": None, **PAPER})
            else:
                row["markets"].append(_price_market(proj, q))
        rows.append(row)
    ctx_summary = None if ctx is None else {
        k: ctx[k] for k in ("model_version", "model_code_sha256", "league_mean_ortg",
                            "league_pace", "hca", "sd", "prior_game_census",
                            "prior_games_used", "settings")}
    card = {
        "schema": CARD_SCHEMA, "status": CARD_STATUS, "sport": "CBB",
        "season": season, "freeze_utc": stamp(freeze), "built_utc": stamp(built),
        "model_version": MODEL_VERSION, "model_code_sha256": MODEL_CODE_SHA256,
        "card_builder_sha256": BUILDER_SHA256,
        "input_sha256": dict(input_sha256 or {}),
        "ratings_receipt": {k: ratings_receipt.get(k) for k in (
            "source", "season", "observed_utc", "sha256", "row_count")}
        if isinstance(ratings_receipt, dict) else None,
        "context": ctx_summary, "context_error": ctx_error,
        "quote_census": census, "quote_source_census": dict(quote_census or {}),
        "row_count": len(rows),
        "projected_rows": sum(r["status"] == "PROJECTED" for r in rows),
        "priced_market_rows": sum(m["status"] == "PRICED_PAPER" for r in rows for m in r["markets"]),
        "pass_reason_counts": dict(sorted(Counter(
            r["pass_reason"] for r in rows if r["status"] == "PASS").items())),
        "rows": rows,
        "official_counted": 0, "approved_stake_u": 0,
        "warnings": [
            "PAPER_0U_RESEARCH_ONLY_NOT_A_RECOMMENDATION",
            "POSITIVE_PAPER_EV_IS_NOT_VERIFIED_PLUS_EV",
            "MODEL_UNVALIDATED_PASSING_TESTS_ARE_NOT_PREDICTIVE_VALIDATION",
            "QUOTE_AND_RATINGS_TIMES_ARE_LOCAL_CAPTURE_CLAIMS_NOT_PROVIDER_ATTESTED",
        ],
    }
    card["card_sha256"] = card_digest(card)
    return card


def run(args, *, clock=None):
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    inputs = {"slate": args.slate, "registry": args.registry,
              "ratings": args.ratings, "ratings_receipt": args.ratings_receipt,
              "prior_games": args.prior_games}
    raws = {k: safe_path(v).read_bytes() for k, v in inputs.items()}
    hashes = {k: sha(v) for k, v in raws.items()}
    receipt_doc = _json_loads(raws["ratings_receipt"])
    found = [r for r in (receipt_doc.get("receipts") or [] if isinstance(receipt_doc, dict) else [])
             if isinstance(r, dict) and r.get("source") == RATINGS_SOURCE]
    receipt = found[0] if len(found) == 1 else None
    if args.prior_residuals:
        raw = safe_path(args.prior_residuals).read_bytes()
        hashes["prior_residuals"] = sha(raw)
        residuals = _json_loads(raw)
    else:
        residuals = None
    quotes, qcensus = [], Counter()
    for i, path in enumerate(args.quotes or ()):
        raw = safe_path(path).read_bytes()
        hashes[f"operator_quotes_{i}"] = sha(raw)
        kind = "csv" if path.lower().endswith(".csv") else "json"
        quotes += [(r, "OPERATOR") for r in operator_quotes(raw, kind)]
    if args.odds_api_raw:
        raw = safe_path(args.odds_api_raw).read_bytes()
        man_raw = safe_path(args.odds_api_manifest).read_bytes()
        xw_raw = safe_path(args.odds_api_crosswalk).read_bytes()
        hashes.update(odds_api_raw=sha(raw), odds_api_manifest=sha(man_raw),
                      odds_api_crosswalk=sha(xw_raw))
        rows, c = odds_api_quotes(raw, _json_loads(man_raw), xw_raw)
        quotes += [(r, "ODDS_API_AGGREGATOR_NOT_BOOK_AUTHENTICATED") for r in rows]
        qcensus.update(c)
    card = build_card(
        freeze_utc=args.freeze_utc, built_utc=stamp(now), season=args.season,
        slate_path=safe_path(args.slate), registry_path=safe_path(args.registry),
        ratings_body=raws["ratings"], ratings_receipt=receipt,
        prior_games=_json_loads(raws["prior_games"]), quotes=quotes,
        prior_residuals=residuals, quote_census=qcensus, input_sha256=hashes,
        max_quote_age_hours=args.max_quote_age_hours)
    out = safe_path(args.output)
    if out.exists():
        raise FileExistsError("CREATE_ONLY_CARD_EXISTS")
    _private_directory(out.parent)
    _private_create(out, (json.dumps(card, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
    return {"status": card["status"], "card_sha256": card["card_sha256"],
            "row_count": card["row_count"], "projected_rows": card["projected_rows"],
            "priced_market_rows": card["priced_market_rows"],
            "official_counted": 0, "approved_stake_u": 0}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--freeze-utc", required=True)
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--slate", required=True)
    p.add_argument("--registry", required=True)
    p.add_argument("--ratings", required=True, help="decrypted cbbd_ratings_adjusted.json")
    p.add_argument("--ratings-receipt", required=True, help="matching receipt.json")
    p.add_argument("--prior-games", required=True)
    p.add_argument("--prior-residuals")
    p.add_argument("--quotes", action="append")
    p.add_argument("--odds-api-raw")
    p.add_argument("--odds-api-manifest")
    p.add_argument("--odds-api-crosswalk")
    p.add_argument("--max-quote-age-hours", type=float, default=24)
    p.add_argument("--output", required=True)
    a = p.parse_args(argv)
    if bool(a.odds_api_raw) != bool(a.odds_api_manifest) or \
            bool(a.odds_api_raw) != bool(a.odds_api_crosswalk):
        p.error("ODDS_API_RAW_MANIFEST_CROSSWALK_REQUIRED_TOGETHER")
    try:
        print(json.dumps(run(a), sort_keys=True))
    except Pass as exc:
        print("CBBD_PAPER_CARD_BLOCKED:" + str(exc)[:160])
        return 2
    except (ValueError, OSError) as exc:  # never echo private paths
        print("CBBD_PAPER_CARD_BLOCKED:" + type(exc).__name__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
