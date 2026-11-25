"""NBA market-contract ingestion guard (research only, PAPER_0U).

Sits at the board-loader / adapter boundary that feeds the frozen model.
It does not import or wrap sportsedge_nba_model.price_game_market at module
import time, and it never edits the frozen model file.

Invalid contracts are rejected fail-closed with a reason code and are not
returned in the accepted board that a runner may pass to pricing.
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from typing import Iterable

# Frozen model file — this module must never write it.
FROZEN_MODEL = "models/nba/sportsedge_nba_model.py"
FROZEN_BLOB = "b353de86445188288cab4050f6cae13eee76bff6"

SOURCE_KINDS = frozenset({
    "dk_capture", "pdf", "screenshot", "csv", "manual", "replay",
})
# Extracted, structured odds rows are required for every source kind.
# PDF/screenshot files are not parsed here: without extracted rows they fail closed.
STRUCTURED_ROW_REQUIRED = frozenset(SOURCE_KINDS)

TIE_SELECTIONS = frozenset({"TIE", "DRAW", "X"})
OU_SELECTIONS = frozenset({"OVER", "UNDER"})
PERIODS = ("", "1H", "2H", "1Q", "2Q", "3Q", "4Q")
# Markets the frozen model can price. Anything else is rejected, not forwarded.
FROZEN_PRICEABLE_PERIODS = frozenset({"", "FG", "1H", "1Q"})

REASON = {
    "TIE_OR_DRAW_IN_TWO_WAY_ML": "Tie/Draw selection cannot be priced as a two-way moneyline",
    "THREE_WAY_ML_UNSUPPORTED": "Three-way moneyline (Tie/Draw offered) is not priced by the two-way model",
    "INCOMPLETE_TWO_WAY": "Two-way market is missing a complementary selection",
    "DUPLICATE_SELECTION": "Duplicate selection in the same market contract",
    "AMBIGUOUS_MARKET_CONTRACT": "Selections do not form a unique two-way contract",
    "MIXED_PERIOD_CONTRACT": "Selections from different periods were grouped as one contract",
    "UNSUPPORTED_PERIOD_MARKET": "Period is not priceable by the frozen model (no silent fallback to full-game)",
    "UNKNOWN_MARKET": "Market name is not a recognized NBA game market",
    "MISSING_REQUIRED_FIELD": "Required board field is missing",
    "ODDS_MALFORMED_OR_FRACTIONAL": "Price is not a whole-number American quote with |price| >= 100 (fractional, decimal, non-numeric, NaN/inf or bool)",
    "INVALID_LINE": "Line is malformed or inconsistent with the market type",
    "SOURCE_KIND_INVALID": "Source kind is not a supported ingestion path",
    "SOURCE_ROWS_MISSING": "PDF/screenshot/other capture has no extracted structured odds rows",
}


def _norm(value) -> str:
    return str(value or "").strip().upper()


def _period(market: str) -> str:
    m = _norm(market)
    for p in ("1H", "2H", "1Q", "2Q", "3Q", "4Q"):
        if m.startswith(p + "_"):
            return p
    return "FG"


def _base(market: str) -> str:
    m = _norm(market)
    p = _period(m)
    rest = m[len(p) + 1:] if p != "FG" else m
    if rest.startswith("TT"):
        return "TT"
    return rest


def _line_key(row: dict) -> str:
    line = row.get("line", "")
    if line in (None, ""):
        return ""
    try:
        return str(abs(float(line))) if _base(row.get("market", "")) != "TOTAL" and _base(row.get("market", "")) != "TT" else str(float(line))
    except (TypeError, ValueError):
        return str(line).strip()


def _group_key(row: dict):
    return (str(row.get("game_id") or "").strip(), _norm(row.get("market")), _line_key(row))


def _reject(row, code, extra=None):
    rec = dict(row)
    rec["reason_code"] = code
    rec["reason"] = REASON[code]
    if extra:
        rec["reason_detail"] = extra
    return rec


def parse_american_price(value):
    """Return the whole-number American price, or None when it is malformed or fractional.

    Accepts ints and numeric strings such as '-110', '+150', '150' and integer-valued
    floats ('150.0'). Rejects bool, NaN/inf, fractional ('-110.5'), decimal odds ('1.91'),
    fractions ('5/2'), words ('EVEN'), blanks and |price| < 100.
    """
    import math
    if isinstance(value, bool) or value is None:
        return None
    try:
        num = float(str(value).strip().replace("\u2212", "-")) if not isinstance(value, (int, float)) else float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num) or num != int(num) or abs(num) < 100:
        return None
    return int(num)


def _line_ok(row: dict) -> bool:
    """ML must have no line; spread/total/TT need a finite numeric line."""
    import math
    base = _base(row.get("market", ""))
    line = row.get("line", "")
    has = line not in (None, "")
    if base not in {"ML", "SPREAD", "TOTAL", "TT"} or "/" in str(row.get("market", "")):
        return True  # unknown / mixed markets get their own reason code in inspect_group
    if base == "ML":
        return not has
    if not has:
        return False
    try:
        return math.isfinite(float(line))
    except (TypeError, ValueError):
        return False


def _missing_fields(row: dict) -> list[str]:
    needed = ("game_id", "market", "selection", "price")
    return [k for k in needed if str(row.get(k) or "").strip() == ""]


def inspect_group(key, rows: list[dict], *, home: str = "", away: str = "") -> tuple[list[dict], list[dict]]:
    """Return (accepted, rejected) for one (game_id, market, line) group."""
    rejected: list[dict] = []
    # Field completeness first — the whole row is unusable.
    usable = []
    for r in rows:
        miss = _missing_fields(r)
        if miss:
            rejected.append(_reject(r, "MISSING_REQUIRED_FIELD", ",".join(miss)))
        elif parse_american_price(r.get("price")) is None:
            rejected.append(_reject(r, "ODDS_MALFORMED_OR_FRACTIONAL", str(r.get("price"))))
        elif not _line_ok(r):
            rejected.append(_reject(r, "INVALID_LINE", str(r.get("line"))))
        else:
            usable.append(r)
    if not usable:
        return [], rejected
    if rejected:
        # One bad quote poisons the contract: never price a surviving half of a pair.
        return [], rejected + [_reject(r, "AMBIGUOUS_MARKET_CONTRACT", "sibling_quote_rejected") for r in usable]

    market = _norm(usable[0]["market"])
    period = _period(market)
    base = _base(market)
    # Mixed period names inside one market string (e.g. "1H/1Q_ML") or inconsistent market spellings.
    periods_seen = {_period(r.get("market", "")) for r in usable}
    if len(periods_seen) > 1 or "/" in market:
        return [], rejected + [_reject(r, "MIXED_PERIOD_CONTRACT") for r in usable]

    if base not in {"ML", "SPREAD", "TOTAL", "TT"} and not market.startswith("TT_"):
        # 3-way labelled markets
        if "3WAY" in market or "3-WAY" in market or market.endswith("1X2"):
            return [], rejected + [_reject(r, "THREE_WAY_ML_UNSUPPORTED") for r in usable]
        return [], rejected + [_reject(r, "UNKNOWN_MARKET") for r in usable]

    if period not in FROZEN_PRICEABLE_PERIODS:
        return [], rejected + [_reject(r, "UNSUPPORTED_PERIOD_MARKET", period) for r in usable]

    sels = [_norm(r["selection"]) for r in usable]
    # Duplicates: same selection more than once (after normalization).
    counts = defaultdict(int)
    for s in sels:
        counts[s] += 1
    if any(c > 1 for c in counts.values()):
        return [], rejected + [_reject(r, "DUPLICATE_SELECTION", _norm(r["selection"])) for r in usable]

    ties = [s for s in sels if s in TIE_SELECTIONS]
    is_ml = base == "ML"

    if is_ml:
        teams = [s for s in sels if s not in TIE_SELECTIONS]
        if ties:
            if len(teams) >= 2:
                return [], rejected + [_reject(r, "THREE_WAY_ML_UNSUPPORTED") for r in usable]
            # Home+TIE (the frozen-model bug) or TIE only: never price as two-way.
            return [], rejected + [_reject(r, "TIE_OR_DRAW_IN_TWO_WAY_ML") for r in usable]
        if len(teams) < 2:
            return [], rejected + [_reject(r, "INCOMPLETE_TWO_WAY") for r in usable]
        if len(teams) > 2:
            return [], rejected + [_reject(r, "AMBIGUOUS_MARKET_CONTRACT") for r in usable]
        if home and away:
            allowed = {_norm(home), _norm(away)}
            if set(teams) != allowed:
                # A selection that is not either event team, or swapped-event identity.
                return [], rejected + [_reject(r, "AMBIGUOUS_MARKET_CONTRACT", "selection_not_event_teams") for r in usable]
        return list(usable), rejected

    # Spreads / totals / team totals: must be a complementary two-way pair.
    if base in {"TOTAL", "TT"} or market.startswith("TT_"):
        if set(sels) != OU_SELECTIONS:
            code = "INCOMPLETE_TWO_WAY" if len(sels) < 2 and set(sels) <= OU_SELECTIONS else "AMBIGUOUS_MARKET_CONTRACT"
            if len(sels) == 1 and sels[0] in OU_SELECTIONS:
                code = "INCOMPLETE_TWO_WAY"
            return [], rejected + [_reject(r, code) for r in usable]
        return list(usable), rejected

    # SPREAD: two distinct team selections, complementary lines already encoded in the group key.
    if len(sels) < 2:
        return [], rejected + [_reject(r, "INCOMPLETE_TWO_WAY") for r in usable]
    if len(sels) > 2:
        return [], rejected + [_reject(r, "AMBIGUOUS_MARKET_CONTRACT") for r in usable]
    if home and away and set(sels) != {_norm(home), _norm(away)}:
        return [], rejected + [_reject(r, "AMBIGUOUS_MARKET_CONTRACT", "selection_not_event_teams") for r in usable]
    if sels[0] == sels[1]:
        return [], rejected + [_reject(r, "DUPLICATE_SELECTION") for r in usable]
    return list(usable), rejected


def filter_odds(rows: Iterable[dict], *, home_away: dict | None = None,
                source_kind: str = "csv") -> dict:
    """Filter a structured odds board. Never returns an invalid row in 'accepted'."""
    kind = _norm(source_kind).lower()
    rejected: list[dict] = []
    if kind not in SOURCE_KINDS:
        return {"source_kind": source_kind, "accepted": [],
                "rejected": [_reject(r, "SOURCE_KIND_INVALID", source_kind) for r in rows] or
                            [_reject({"source_kind": source_kind}, "SOURCE_KIND_INVALID", source_kind)]}
    material = list(rows or [])
    if not material:
        return {"source_kind": kind, "accepted": [],
                "rejected": [_reject({"source_kind": kind}, "SOURCE_ROWS_MISSING")]}

    groups: dict[tuple, list] = defaultdict(list)
    for r in material:
        groups[_group_key(r)].append(dict(r))

    accepted: list[dict] = []
    for key, grp in groups.items():
        ha = (home_away or {}).get(key[0], {})
        ok, bad = inspect_group(key, grp, home=ha.get("home", ""), away=ha.get("away", ""))
        accepted.extend(ok)
        rejected.extend(bad)
    return {"source_kind": kind, "accepted": accepted, "rejected": rejected,
            "accepted_count": len(accepted), "rejected_count": len(rejected)}


def load_csv_odds(path: str) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def load_games_home_away(path: str) -> dict:
    out = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            gid = (r.get("game_id") or "").strip()
            if gid:
                out[gid] = {"home": (r.get("home") or "").strip(), "away": (r.get("away") or "").strip()}
    return out


def load_board(inputs: dict, *, source_kind: str = "csv") -> dict:
    """Load a board from a runner input map and filter it.

    inputs may include 'odds' (csv path), 'games' (csv path), or 'odds_rows'
    (already extracted structured rows). PDF and screenshot paths are accepted
    only when structured odds_rows (or an extracted odds csv) are also supplied.
    """
    kind = _norm(source_kind).lower()
    if kind not in SOURCE_KINDS:
        return filter_odds([], source_kind=source_kind)
    rows = list(inputs.get("odds_rows") or [])
    if not rows:
        rows = load_csv_odds(inputs.get("odds") or "")
    # A raw PDF/screenshot file with no extracted rows cannot be priced.
    raw_capture = inputs.get("capture_path") or inputs.get("pdf") or inputs.get("screenshot")
    if kind in {"pdf", "screenshot"} and not rows:
        return {"source_kind": kind, "accepted": [], "rejected": [
            _reject({"capture_path": raw_capture or ""}, "SOURCE_ROWS_MISSING",
                    "extracted structured odds rows are required; the capture file is not parsed")
        ]}
    home_away = dict(inputs.get("home_away") or {})
    if inputs.get("games"):
        home_away.update(load_games_home_away(inputs["games"]))
    result = filter_odds(rows, home_away=home_away, source_kind=kind)
    result["inputs"] = {k: inputs[k] for k in inputs if k != "odds_rows"}
    return result


def write_accepted_odds(path: str, rows: list[dict], fieldnames=None) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    fields = fieldnames or ["game_id", "market", "selection", "line", "price"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


# Runner entry points that are allowed to feed price_game_market. The frozen
# model functions remain callable for unit tests of the frozen file itself,
# but production/research runners must go through these names.
GUARDED_ENTRY_POINTS = (
    "models.nba.market_contract.load_board",
    "models.nba.market_contract.filter_odds",
    "models.nba.market_contract.run_card_guarded",
    "models.nba.run_it.main",
    "models.nba.run_it.run_from_inputs",
)

# Frozen callables that still exist and will price a bad board if called directly.
# They are not runner entry points; a test enumerates and documents them.
UNGUARDED_FROZEN_CALLABLES = (
    "models/nba/sportsedge_nba_model.py:run_card",
    "models/nba/sportsedge_nba_model.py:price_games",
    "models/nba/sportsedge_nba_model.py:price_game_market",
    "models/nba/sportsedge_nba_model.py:__main__",
)


def run_card_guarded(inputs: dict, out_dir: str = ".", *, source_kind: str = "csv"):
    """Filter the odds board, then call the frozen run_card on accepted rows only.

    Imported lazily so this module can be unit-tested without executing pricing.
    A pricing_hook, if provided via the module-level _PRICING_HOOK for tests, is
    called with each accepted odds row just before the frozen card runs.
    """
    board = load_board(inputs, source_kind=source_kind)
    os.makedirs(out_dir, exist_ok=True)
    # Write rejection ledger even when nothing is accepted.
    ledger = os.path.join(out_dir, "nba_rejected_markets.csv")
    fields = sorted({k for r in board["rejected"] for k in r} | {"reason_code", "reason"})
    write_accepted_odds(ledger, board["rejected"], fields or ["reason_code", "reason"])
    hook = globals().get("_PRICING_HOOK")
    if hook:
        for row in board["accepted"]:
            hook(dict(row))
    if not board["accepted"]:
        return {"projections": {}, "picks": [], "rejected": board["rejected"],
                "accepted": [], "csv": None, "md": None, "ledger": ledger,
                "source_kind": board["source_kind"]}

    # Materialize a filtered odds file so the frozen loader never sees rejects.
    filtered = os.path.join(out_dir, "_accepted_odds.csv")
    write_accepted_odds(filtered, board["accepted"])
    frozen_inputs = dict(inputs)
    frozen_inputs["odds"] = filtered
    frozen_inputs.pop("odds_rows", None)

    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import sportsedge_nba_model as frozen
    card = frozen.run_card(frozen_inputs, out_dir=out_dir)
    card["rejected"] = board["rejected"]
    card["accepted"] = board["accepted"]
    card["ledger"] = ledger
    card["source_kind"] = board["source_kind"]
    return card
