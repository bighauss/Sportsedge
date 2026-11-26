"""Order-independent canonical identity for NFL quotes.

A quote_id is a pure function of the quote's own content: event, sportsbook, market,
period, player, line, side, price and capture time. It never depends on row position,
emission order, or any counter. Nothing is inferred: a blank period or player stays blank,
and missing required fields raise ValueError.

selection_key identifies WHAT is offered (event/book/market/period/player/line/side).
quote_id identifies one observed offer of it (selection_key + price + captured_at).

Duplicates: identical canonical content collapses to one quote.
Conflicts: the same selection_key captured at the same captured_at with different prices
is ambiguous. All members are excluded from `accepted` and reported in `conflicts`; no
price is ever chosen for them.

captured_at is compared as normalized text, so callers must supply one consistent format
(for example UTC ISO-8601). Time-zone conversion is not performed here.
"""
import hashlib
from decimal import Decimal, InvalidOperation

REQUIRED = ("home", "away", "book", "market", "side", "price", "captured_at")
SEP = "\x1f"


def _txt(v):
    return " ".join(str(v if v is not None else "").split()).casefold()


def _line(v):
    s = str(v if v is not None else "").strip()
    if s == "":
        return ""
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"unparseable line: {v!r}")
    if not d.is_finite():
        raise ValueError(f"non-finite line: {v!r}")
    if d == 0:
        return "0"
    return format(d.normalize(), "f")


def _price(v):
    try:
        d = Decimal(str(v).strip())
    except InvalidOperation:
        raise ValueError(f"unparseable price: {v!r}")
    if not d.is_finite() or d != d.to_integral_value() or abs(d) < 100:
        raise ValueError(f"not an American price: {v!r}")
    return str(int(d))


def canonical(row):
    r = {str(k).strip().lower(): v for k, v in row.items()}
    for k in REQUIRED:
        if _txt(r.get(k)) == "":
            raise ValueError(f"missing required field: {k}")
    c = {
        "sport": "nfl",
        "home": _txt(r["home"]),
        "away": _txt(r["away"]),
        "event_date": _txt(r.get("event_date")),
        "book": _txt(r["book"]),
        "market": _txt(r["market"]),
        "period": _txt(r.get("period")),
        "player": _txt(r.get("player")),
        "line": _line(r.get("line")),
        "side": _txt(r["side"]),
        "price": _price(r["price"]),
        "captured_at": _txt(r["captured_at"]),
    }
    c["selection_key"] = selection_key(c)
    c["quote_id"] = quote_id(c)
    return c


SELECTION_FIELDS = ("sport", "home", "away", "event_date", "book", "market",
                    "period", "player", "line", "side")
QUOTE_FIELDS = SELECTION_FIELDS + ("price", "captured_at")


def _digest(c, fields):
    return hashlib.sha256(SEP.join(c[k] for k in fields).encode("utf-8")).hexdigest()


def selection_key(c):
    return _digest(c, SELECTION_FIELDS)[:24]


def quote_id(c):
    return _digest(c, QUOTE_FIELDS)[:24]


def dedupe(rows):
    """Return {'accepted': [canonical quotes sorted by quote_id], 'conflicts': [[quote_id, ...], ...]}.

    The result is identical for every permutation of `rows`."""
    by_id = {}
    for row in rows:
        c = canonical(row)
        by_id.setdefault(c["quote_id"], c)
    groups = {}
    for qid, c in by_id.items():
        groups.setdefault((c["selection_key"], c["captured_at"]), []).append(qid)
    accepted, conflicts = [], []
    for ids in groups.values():
        if len(ids) == 1:
            accepted.append(by_id[ids[0]])
        else:
            conflicts.append(sorted(ids))
    accepted.sort(key=lambda c: c["quote_id"])
    conflicts.sort()
    return {"accepted": accepted, "conflicts": conflicts}
