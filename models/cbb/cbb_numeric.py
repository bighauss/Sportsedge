"""Strict numeric and identity helpers for CBB quote intake. Pure python; no pipeline imports.

Replaces the permissive parsing in cbb_run_it_pipeline.normalize_quotes, which (read at adea86f5):
  * _int_price strips every '+' and then int(float(s)): '1+10' -> 110, '1e3' -> 1000, and 'inf' raises OverflowError
    (not caught by its ValueError/TypeError handler) so one malformed cell can crash intake;
  * _num returns float(s) for 'nan' and 'inf', which pass the line_bad check and reach pricing.
And supplies the player-aware identities the duplicate key (gid, period, market, line) lacks.

Parsing is ASCII-only and length-bounded: no Unicode-compatibility folding (superscript, circled or fullwidth digits
are BAD, not silently converted), no giant integers, and no decimal that a float cannot hold exactly enough to keep
distinct lines distinct (at most 3 decimal places, at most 4 integer digits).
"""
import math
import re
import unicodedata

BAD = "BAD"
_PRICE = re.compile(r"[+-]?[1-9][0-9]{2,5}")
_LINE = re.compile(r"[+-]?(?:[0-9]{1,4}(?:\.[0-9]{1,3})?|\.[0-9]{1,3})")
MAX_ABS_PRICE = 100000
MAX_ABS_LINE = 1000.0
MAX_CELL = 16


def _clean(v):
    """Strip surrounding whitespace and map the single Unicode minus sign U+2212 to '-'. Nothing else is folded."""
    s = str(v).strip().replace("\u2212", "-")
    return s if len(s) <= MAX_CELL else None


def strict_price(v):
    """None for blank; BAD for anything not an exact ASCII signed integer with |price| in [100, 100000]."""
    if v is None:
        return None
    s = _clean(v)
    if s is None:
        return BAD
    if not s:
        return None
    if not _PRICE.fullmatch(s):
        return BAD
    p = int(s)
    return p if 100 <= abs(p) <= MAX_ABS_PRICE else BAD


def strict_line(v):
    """None for blank; BAD unless a plain ASCII decimal (<= 4 integer digits, <= 3 decimals), finite, |x| <= 1000."""
    if v is None:
        return None
    s = _clean(v)
    if s is None:
        return BAD
    if not s:
        return None
    if not _LINE.fullmatch(s):
        return BAD
    x = float(s)
    if not math.isfinite(x) or abs(x) > MAX_ABS_LINE:
        return BAD
    return x + 0.0                      # -0.0 -> 0.0


def norm_player(name):
    """Casefolded, NFKC-normalised, whitespace-collapsed player key; None when blank. DIAGNOSTIC ONLY."""
    s = " ".join(unicodedata.normalize("NFKC", str(name or "")).casefold().split())
    return s or None


def player_identity_verified(player_id):
    """A player identity is verified only by a permanent provider/league id, never by a name."""
    return bool(player_id and str(player_id).strip())


def _who(player, player_id):
    return ("id", str(player_id).strip()) if player_identity_verified(player_id) else ("name", norm_player(player))


def semantic_identity(game_id, period, market, line, player=None, player_id=None):
    """WHAT is quoted: the same bet from two providers/markets-ids is the same semantic quote (duplicate detection)."""
    return (game_id, period, market, line, _who(player, player_id))


def provider_identity(game_id, period, market, line, player=None, player_id=None,
                      dk_event_id=None, dk_market_id=None, dk_selection_a=None, dk_selection_b=None):
    """WHERE it came from: semantic identity plus the provider's own ids (provenance / replay, never de-duplication)."""
    ids = tuple(str(x).strip() if x not in (None, "") else None
                for x in (dk_event_id, dk_market_id, dk_selection_a, dk_selection_b))
    return semantic_identity(game_id, period, market, line, player, player_id) + ids
