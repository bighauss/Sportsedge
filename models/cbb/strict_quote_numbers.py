"""Strict numeric admission for CBB research quotes; no pricing or policy changes."""
import math
import re

_PRICE = re.compile(r"[+-]?[1-9][0-9]*")
_LINE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)")

def int_price(value):
    s = "" if value is None else str(value).strip()
    if not s:
        return None
    if not _PRICE.fullmatch(s):
        return "BAD"
    try:
        p = int(s)
        # Downstream pricing converts to float; reject overflow and lossy conversion.
        f = float(p)
        return p if abs(p) >= 100 and math.isfinite(f) and int(f) == p else "BAD"
    except (ValueError, OverflowError):
        return "BAD"

def number(value):
    s = "" if value is None else str(value).strip()
    if not s:
        return None
    if not _LINE.fullmatch(s):
        return "BAD"
    try:
        x = float(s)
        return x if math.isfinite(x) else "BAD"
    except (ValueError, OverflowError):
        return "BAD"
