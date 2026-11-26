"""Projection-provenance classification for NFL board rows. Pure python; reads only the raw board CSV.

Frozen v5 labels a row PROJECTION or ANCHOR itself, but (a) hard-codes PROJECTION on touchdown props even when the
game simulation they depend on is market-fitted, and (b) gives same-game parlays the game's label without checking
the player legs. So provenance is rebuilt here from the board, from each row's real dependencies:

  game line / OT / REG_* / margin band   -> game projection
  single stat prop                        -> that player+stat mean            (v5 stat_probs uses only the mean)
  ATD / TD2 / FTD                         -> game projection AND player share (v5 td_probs reads the game simulation)
  SGP                                     -> game projection AND every leg's own dependencies

A component is VERIFIED only when its board row carries proj_provenance = PIT_VERIFIED (a point-in-time-verified
independent forecast). A supplied projection with a blank tag or UNVERIFIED is UNVERIFIED; no projection is ANCHOR
(v5 fits it to the book); any other tag value, a conflicting value, or a missing required share is AMBIGUOUS.
Only a row whose every component is VERIFIED is card-eligible; every other class is HELD.
"""
import csv

VERIFIED, UNVERIFIED, ANCHOR, MIXED, AMBIGUOUS = (
    "VERIFIED_PIT", "UNVERIFIED_PROJECTION", "ANCHOR", "MIXED", "AMBIGUOUS")
TD_MARKETS = {"ATD", "TD2", "FTD"}
VERIFIED_TAG = "PIT_VERIFIED"
UNVERIFIED_TAGS = {"", "UNVERIFIED"}


def eligible(classification):
    return classification == VERIFIED


def _num(x):
    x = (x or "").strip().replace("+", "")
    if not x:
        return None
    try:
        return float(x)
    except ValueError:
        return "bad"


def _component(supplied, tag):
    if not supplied:
        return ANCHOR
    if tag == VERIFIED_TAG:
        return VERIFIED
    return UNVERIFIED if tag in UNVERIFIED_TAGS else AMBIGUOUS


def combine(parts):
    s = set(parts)
    if not s or AMBIGUOUS in s:
        return AMBIGUOUS
    if len(s) == 1:
        return next(iter(s))
    return MIXED if ANCHOR in s else UNVERIFIED


def _read(path):
    games = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            if r.get("sport", "").upper() != "NFL" or not r.get("market"):
                continue
            r["market"] = r["market"].upper()
            r["tag"] = r.get("proj_provenance", "").upper()
            games.setdefault((r["home"], r.get("away", "")), []).append(r)
    return games


def _game_component(rows):
    """Mirror v5: the FIRST row (game lines before props) carrying BOTH team projections sets the game."""
    ordered = [r for r in rows if not r.get("player")] + [r for r in rows if r.get("player")]
    full = [r for r in ordered if _num(r.get("home_proj")) is not None and _num(r.get("away_proj")) is not None]
    if any("bad" in (_num(r.get("home_proj")), _num(r.get("away_proj"))) for r in rows):
        return AMBIGUOUS, "unparseable team projection"
    if not full:
        partial = any((_num(r.get("home_proj")) is None) != (_num(r.get("away_proj")) is None) for r in rows)
        return ANCHOR, "partial team projection ignored by v5; fitted to the book" if partial else "no team projections"
    first = full[0]
    for r in full[1:]:
        if (_num(r["home_proj"]), _num(r["away_proj"])) != (_num(first["home_proj"]), _num(first["away_proj"])):
            return AMBIGUOUS, "conflicting team projections on one game"
        if r["tag"] != first["tag"]:
            return AMBIGUOUS, "conflicting proj_provenance on one game's team projections"
    return _component(True, first["tag"]), ""


def _prop_component(rows, player, market):
    grp = [r for r in rows if r.get("player") == player and r["market"] == market]
    vals = {_num(r.get("proj")) for r in grp}
    tags = {r["tag"] for r in grp}
    if "bad" in vals or len(vals - {None}) > 1 or (None in vals and len(vals) > 1) or len(tags) > 1:
        return AMBIGUOUS, "conflicting or unparseable proj / proj_provenance for %s %s" % (player, market)
    supplied = next(iter(vals)) is not None
    if market in TD_MARKETS and not supplied:
        return AMBIGUOUS, "%s %s needs a player touchdown share; none supplied" % (player, market)
    return _component(supplied, next(iter(tags))), ""


def classify(path):
    """{(game, market, player, sgp): (classification, reason)} for every NFL board row."""
    out = {}
    for (home, away), rows in _read(path).items():
        game = "%s @ %s" % (away, home)
        gcomp, greason = _game_component(rows)
        legs = {}
        for r in rows:
            if r["market"] != "SGP" and r.get("sgp"):
                legs.setdefault(r["sgp"], []).append(r)
        for r in rows:
            m, p, sg = r["market"], r.get("player", ""), r.get("sgp", "")
            why = [greason] if greason else []

            def dep(row):
                if not row.get("player"):
                    return [gcomp]
                c, why_ = _prop_component(rows, row["player"], row["market"])
                if why_:
                    why.append(why_)
                return ([gcomp] if row["market"] in TD_MARKETS else []) + [c]

            if m == "SGP":
                members = legs.get(sg, [])
                parts = [gcomp] + [c for leg in members for c in dep(leg)]
                if not members:
                    parts.append(AMBIGUOUS)
                    why.append("SGP row %r has no legs on the board" % sg)
            else:
                parts = dep(r)
            key, val = (game, m, p, sg), (combine(parts), "; ".join(dict.fromkeys(w for w in why if w)))
            if key in out and out[key][0] != val[0]:
                val = (AMBIGUOUS, "duplicate quote with different provenance")
            out[key] = val
    return out
