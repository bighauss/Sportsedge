"""Shared append-only PREGAME prediction log (hash-chained JSONL). PAPER / 0u.

One row per selection the runner evaluated -- priced, non-selected AND withheld -- so the
full denominator survives. Rows are frozen before kickoff and never edited; outcomes live
in a separate grades file joined at export time.

Rejects: capture or forecast freeze at/after kickoff, a quote captured after the forecast
freeze is fine (forecast must precede odds), duplicate selection keys, malformed
probabilities/prices, and any tampering with earlier lines (chain re-verified on append).

export_harness() writes the exact CSV consumed by research/backtest_harness/harness.py:
event_id,date,market,selection,line,model_p,push_p,price,opp_price,outcome
"""
from __future__ import annotations
import csv, hashlib, json, math, os
from datetime import datetime, timezone

SCHEMA = "sportsedge-pregame-prediction-log-v1"
GENESIS = "0" * 64
REQUIRED = ("event_id", "sport", "market", "period", "selection", "line", "model_p", "push_p",
            "model_version", "model_sha256", "price", "opp_price", "book", "quote_captured_utc",
            "forecast_freeze_utc", "kickoff_utc", "eligibility")
HARNESS_COLUMNS = ["event_id", "date", "market", "selection", "line", "model_p", "push_p",
                   "price", "opp_price", "outcome"]


class LogError(ValueError):
    pass


def _utc(s, field):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise LogError("BAD_UTC:" + field)
    try:
        return datetime.fromisoformat(s[:-1] + "+00:00")
    except ValueError as e:
        raise LogError("BAD_UTC:" + field) from e


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def key(r):
    return (str(r["event_id"]), r["sport"], r["market"], r["period"], r["selection"],
            None if r["line"] is None else float(r["line"]), r["model_version"])


def validate(r):
    if not isinstance(r, dict) or set(r) != set(REQUIRED):
        raise LogError("FIELDS_MISMATCH")
    for f in ("event_id", "sport", "market", "period", "selection", "model_version", "eligibility", "book"):
        if not isinstance(r[f], str) or not r[f].strip():
            raise LogError("BAD_TEXT:" + f)
    ko = _utc(r["kickoff_utc"], "kickoff_utc")
    fz = _utc(r["forecast_freeze_utc"], "forecast_freeze_utc")
    if fz >= ko:
        raise LogError("FORECAST_NOT_PREGAME")
    priced = r["eligibility"] != "WITHHELD" and not r["eligibility"].startswith("WITHHELD:")
    if r["line"] is not None and (isinstance(r["line"], bool) or not isinstance(r["line"], (int, float))
                                  or not math.isfinite(r["line"])):
        raise LogError("BAD_LINE")
    if not priced:
        for f in ("model_p", "push_p", "price", "opp_price", "quote_captured_utc"):
            if r[f] is not None and f in ("model_p", "push_p"):
                _prob(r[f], f)
        if r["quote_captured_utc"] is not None and _utc(r["quote_captured_utc"], "quote_captured_utc") >= ko:
            raise LogError("QUOTE_NOT_PREGAME")
        return r
    _prob(r["model_p"], "model_p"); _prob(r["push_p"], "push_p")
    if r["model_p"] + r["push_p"] > 1 + 1e-9:
        raise LogError("PROBABILITIES_EXCEED_ONE")
    for f in ("price", "opp_price"):
        v = r[f]
        if isinstance(v, bool) or not isinstance(v, int) or abs(v) < 100:
            raise LogError("BAD_AMERICAN_PRICE:" + f)
    if _utc(r["quote_captured_utc"], "quote_captured_utc") >= ko:
        raise LogError("QUOTE_NOT_PREGAME")
    if not isinstance(r["model_sha256"], str) or len(r["model_sha256"]) < 12:
        raise LogError("MODEL_SHA_REQUIRED")
    return r


def _prob(v, f):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1:
        raise LogError("BAD_PROBABILITY:" + f)


def read(path):
    """Verified rows. Raises on any tampering or broken chain."""
    out, prev = [], GENESIS
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            try:
                e = json.loads(line)
            except ValueError as ex:
                raise LogError(f"MALFORMED_LINE:{n}") from ex
            if set(e) != {"schema", "seq", "prev_sha256", "row", "sha256"} or e["schema"] != SCHEMA:
                raise LogError(f"BAD_ENTRY:{n}")
            if e["seq"] != n or e["prev_sha256"] != prev:
                raise LogError(f"CHAIN_BROKEN:{n}")
            body = {k: e[k] for k in ("schema", "seq", "prev_sha256", "row")}
            if hashlib.sha256(_canon(body).encode()).hexdigest() != e["sha256"]:
                raise LogError(f"TAMPERED:{n}")
            validate(e["row"]); out.append(e["row"]); prev = e["sha256"]
    return out


def append(path, rows):
    """Validate all rows first (all-or-nothing), refuse duplicates, then append."""
    existing = read(path)
    seen = {key(r) for r in existing}
    batch = []
    for r in rows:
        validate(r)
        k = key(r)
        if k in seen:
            raise LogError("DUPLICATE_SELECTION:" + "|".join(map(str, k)))
        seen.add(k); batch.append(r)
    prev = GENESIS
    if existing:
        with open(path, encoding="utf-8") as f:
            prev = json.loads(f.readlines()[-1])["sha256"]
    seq = len(existing)
    with open(path, "a", encoding="utf-8") as f:
        for r in batch:
            seq += 1
            body = {"schema": SCHEMA, "seq": seq, "prev_sha256": prev, "row": r}
            sha = hashlib.sha256(_canon(body).encode()).hexdigest()
            f.write(_canon({**body, "sha256": sha}) + "\n"); prev = sha
    return {"appended": len(batch), "total": seq, "head_sha256": prev}


def selection_id(r):
    return "|".join("" if v is None else str(v) for v in key(r))


def export_harness(log_path, outcomes, out_csv):
    """outcomes: {selection_id: 'W'|'L'|'P'|'V'} from the grader. Only priced rows export."""
    rows, census = read(log_path), {"exported": 0, "withheld_not_exported": 0, "ungraded": 0}
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, HARNESS_COLUMNS); w.writeheader()
        for r in rows:
            if r["eligibility"] == "WITHHELD" or r["eligibility"].startswith("WITHHELD:"):
                census["withheld_not_exported"] += 1; continue
            o = outcomes.get(selection_id(r))
            if o not in ("W", "L", "P", "V"):
                census["ungraded"] += 1; continue
            w.writerow({"event_id": r["event_id"], "date": r["kickoff_utc"][:10],
                        "market": f'{r["sport"]}:{r["market"]}:{r["period"]}',
                        "selection": r["selection"], "line": "" if r["line"] is None else r["line"],
                        "model_p": r["model_p"], "push_p": r["push_p"], "price": r["price"],
                        "opp_price": r["opp_price"], "outcome": o})
            census["exported"] += 1
    return census


def rows_from_cbb_card(card, names, extra=None):
    """Every CBB market on the frozen card, priced or withheld. Reads only frozen values."""
    sha = card.get("model_code_sha256") or card.get("card_builder_sha256") or ""
    base = {"sport": "CBB", "model_version": card["model_version"], "model_sha256": sha,
            "forecast_freeze_utc": card["freeze_utc"]}
    out = []
    for r in card["rows"]:
        tip = r.get("tipoff_utc") or names.get(r["game_id"], (None, None, None))[2]
        for m in r["markets"]:
            if m["status"] != "PRICED_PAPER":
                for side in ("home", "away") if m["market"] != "total" else ("over", "under"):
                    q = m.get("quote") or {}
                    out.append({**base, "event_id": str(r["game_id"]), "market": m["market"], "period": "FG",
                                "selection": side, "line": q.get("line"), "model_p": None, "push_p": None,
                                "price": None, "opp_price": None, "book": q.get("book") or "DraftKings",
                                "quote_captured_utc": q.get("captured_utc"), "kickoff_utc": tip,
                                "eligibility": "WITHHELD:" + str(m.get("pass_reason") or m["status"])})
                continue
            q = m["quote"]
            prices = (q["price_a"], q["price_b"])
            for i, side in enumerate(m["sides"]):
                line = q["line"]
                if line is not None and m["market"] == "spread" and side == "away":
                    line = -line
                out.append({**base, "event_id": str(r["game_id"]), "market": m["market"], "period": "FG",
                            "selection": side, "line": line, "model_p": m["model_prob"][side],
                            "push_p": m["model_prob"]["push"], "price": int(prices[i]),
                            "opp_price": int(prices[1 - i]), "book": q["book"],
                            "quote_captured_utc": q["captured_utc"], "kickoff_utc": tip,
                            "eligibility": "BLOWOUT_EXCLUDED" if m.get("blowout_excluded") else "PRICED_UNVALIDATED"})
    for m in (extra or {}).get("ladders", []):
        tip = names.get(m["game_id"], (None, None, None))[2]
        for i, side in enumerate(m["sides"]):
            line = -m["line"] if m["kind"] == "alt_spread" and side == "away" else m["line"]
            out.append({**base, "event_id": str(m["game_id"]), "market": m["kind"], "period": "FG",
                        "selection": side, "line": line, "model_p": m["model_prob"][i], "push_p": m["push"],
                        "price": int(m["price"][i]), "opp_price": int(m["price"][1 - i]),
                        "book": "DraftKings", "quote_captured_utc": m["captured_utc"], "kickoff_utc": tip,
                        "eligibility": "BLOWOUT_EXCLUDED" if m["blowout_excluded"] else "PRICED_UNVALIDATED"})
    return out
