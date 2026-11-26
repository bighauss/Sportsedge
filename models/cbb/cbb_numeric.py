"""Strict numeric and identity helpers for CBB quote intake. Pure python; no pipeline imports.

Replaces the permissive parsing in cbb_run_it_pipeline.normalize_quotes, which (read at adea86f5):
  * _int_price strips every '+' and then int(float(s)): '1+10' -> 110, '1e3' -> 1000, and 'inf' raises OverflowError
    (not caught by its ValueError/TypeError handler) so one malformed cell can crash intake;
  * _num returns float(s) for 'nan' and 'inf', which pass the line_bad check and reach pricing.
And supplies the player-aware identity the duplicate key (gid, period, market, line) lacks.
"""
import math
import re
import unicodedata

BAD = "BAD"
_PRICE = re.compile(r"[+-]?[1-9][0-9]*")
_LINE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)")
MAX_ABS_PRICE = 100000
MAX_ABS_LINE = 1000.0


def _clean(v):
    return unicodedata.normalize("NFKC", str(v)).strip().replace("\u2212", "-")


def strict_price(v):
    """None for blank; BAD for anything not an exact signed integer with |price| in [100, 100000]."""
    if v is None:
        return None
    s = _clean(v)
    if not s:
        return None
    if not _PRICE.fullmatch(s):
        return BAD
    p = int(s)
    return p if 100 <= abs(p) <= MAX_ABS_PRICE else BAD


def strict_line(v):
    """None for blank; BAD for non-decimal text, non-finite values, or |line| > 1000."""
    if v is None:
        return None
    s = _clean(v)
    if not s:
        return None
    if not _LINE.fullmatch(s):
        return BAD
    x = float(s)
    return x if math.isfinite(x) and abs(x) <= MAX_ABS_LINE else BAD


def norm_player(name):
    """Casefolded, NFKC-normalised, whitespace-collapsed player key; None when blank."""
    s = " ".join(unicodedata.normalize("NFKC", str(name or "")).casefold().split())
    return s or None


def quote_identity(game_id, period, market, line, player=None, player_id=None, dk_market_id=None):
    """Duplicate-detection identity. A permanent player_id beats a name; names are only a fallback."""
    who = ("id", str(player_id).strip()) if player_id and str(player_id).strip() else ("name", norm_player(player))
    return (game_id, period, market, line, who, str(dk_market_id).strip() if dk_market_id else None)
