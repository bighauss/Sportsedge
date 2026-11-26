"""Projection-provenance classification for NFL board rows. Pure python; reads the raw board CSV and, for
verification, a signed evidence manifest.

Frozen v5 labels a row PROJECTION or ANCHOR itself, but (a) hard-codes PROJECTION on touchdown props even when the
game simulation they depend on is market-fitted, and (b) gives same-game parlays the game's label without checking
the player legs. So provenance is rebuilt here from the board, from each row's real dependencies:

  game line / OT / REG_* / margin band   -> game projection
  single stat prop                        -> that player+stat mean            (v5 stat_probs uses only the mean)
  ATD / TD2 / FTD                         -> game projection AND player share (v5 td_probs reads the game simulation)
  SGP (>= 2 legs, sides A/B)              -> game projection AND every leg's own dependencies

A component is VERIFIED only when BOTH hold: the board row claims proj_provenance = PIT_VERIFIED, AND a signed
evidence entry for that exact subject exists whose HMAC-SHA256 verifies under the caller's key, whose recorded values
equal the board's exactly, which names a model_version and an input_hash, and whose forecast_ts is strictly
before its kickoff_ts (both timezone-aware). A claim without evidence is UNVERIFIED. The CSV tag alone is never proof.
Trust rests on custody of the key; this module does not recompute input hashes or re-run the model.

Projection cells are parsed STRICTLY (plain ASCII decimals, bounded length). Frozen v5's num() deletes every '+', so
'2+7' would become 27; here it is INVALID_INPUT.

No projection -> ANCHOR (v5 fits it to the book). Partial team projection -> ANCHOR. Non-finite, malformed or
out-of-range numbers, unknown players/teams, a player on two teams, malformed or one-leg SGPs -> INVALID. Conflicting or
unknown tags -> AMBIGUOUS. Only a row whose every component is VERIFIED has provenance VERIFIED_PIT; card eligibility
is a separate decision (eligible() is necessary, not sufficient).
"""
import csv
import hashlib
import hmac
import json
import math
import re
from datetime import datetime

VERIFIED, UNVERIFIED, ANCHOR, MIXED, AMBIGUOUS, INVALID = (
    "VERIFIED_PIT", "UNVERIFIED_PROJECTION", "ANCHOR", "MIXED", "AMBIGUOUS", "INVALID_INPUT")
TD_MARKETS = {"ATD", "TD2", "FTD"}
VERIFIED_TAG = "PIT_VERIFIED"
UNVERIFIED_TAGS = {"", "UNVERIFIED"}
TEAM_PTS = (0.0, 100.0)
STAT_MEAN = (0.0, 2000.0)
TD_SHARE = (0.0, 1.0)
DECIMAL = re.compile(r"[+-]?(?:[0-9]{1,6}(?:\.[0-9]{1,6})?|\.[0-9]{1,6})")
MAX_CELL = 16


def eligible(classification):
    """Necessary condition for the independent card; later gates (calibration, freeze) are separate."""
    return classification == VERIFIED


# ---------- evidence ----------
def _key(key):
    return key.encode() if isinstance(key, str) else key


def _canon(entry):
    return json.dumps({k: v for k, v in entry.items() if k != "sig"}, sort_keys=True, separators=(",", ":")).encode()


def sign(entry, key):
    return hmac.new(_key(key), _canon(entry), hashlib.sha256).hexdigest()


def load_manifest(path):
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)["entries"]
    out = {}
    for e in entries:
        if e.get("subject") in out:
            raise ValueError("duplicate evidence subject %r" % e.get("subject"))
        out[e.get("subject")] = e
    return out


def _ts(x):
    t = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("naive timestamp")
    return t


def _evidence(subject, values, manifest, key):
    if not manifest or not key:
        return "no signed evidence supplied"
    e = manifest.get(subject)
    if e is None:
        return "no evidence entry for %s" % subject
    if not isinstance(e.get("sig"), str) or not hmac.compare_digest(e["sig"], sign(e, key)):
        return "evidence signature invalid for %s" % subject
    if e.get("values") != values:
        return "evidence values differ from the board for %s" % subject
    if not e.get("model_version") or not e.get("input_hash"):
        return "evidence lacks model_version or input_hash for %s" % subject
    try:
        if not _ts(e.get("forecast_ts")) < _ts(e.get("kickoff_ts")):
            return "forecast_ts is not before kickoff_ts for %s" % subject
    except (ValueError, TypeError):
        return "evidence timestamps missing, malformed or timezone-naive for %s" % subject
    return ""


# ---------- parsing ----------
def _num(x):
    """None for blank; 'bad' for anything but a plain ASCII decimal (no inner '+', no exponent, no NaN/inf)."""
    s = (x or "").strip().replace("\u2212", "-")
    if not s:
        return None
    if len(s) > MAX_CELL or not DECIMAL.fullmatch(s):
        return "bad"
    v = float(s)
    return v if math.isfinite(v) else "bad"


def _in(v, rng):
    return rng[0] <= v <= rng[1]


def _component(supplied, tag, ev_problem):
    if not supplied:
        return ANCHOR, ""
    if tag in UNVERIFIED_TAGS:
        return UNVERIFIED, ""
    if tag != VERIFIED_TAG:
        return AMBIGUOUS, "unknown proj_provenance %r" % tag
    return (VERIFIED, "") if not ev_problem else (UNVERIFIED, "claimed PIT_VERIFIED without proof: " + ev_problem)


def combine(parts):
    s = set(parts)
    if not s:
        return AMBIGUOUS
    for worst in (INVALID, AMBIGUOUS):
        if worst in s:
            return worst
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
            games.setdefault((r.get("home", ""), r.get("away", "")), []).append(r)
    return games


def _game_component(home, away, rows, manifest, key):
    if not home or not away or home == away:
        return INVALID, "game needs two distinct, non-empty teams"
    ordered = [r for r in rows if not r.get("player")] + [r for r in rows if r.get("player")]
    pairs = [(_num(r.get("home_proj")), _num(r.get("away_proj"))) for r in ordered]
    if any("bad" in p for p in pairs):
        return INVALID, "non-finite, malformed or unparseable team projection"
    full = [(r, p) for r, p in zip(ordered, pairs) if p[0] is not None and p[1] is not None]
    if any(not (_in(p[0], TEAM_PTS) and _in(p[1], TEAM_PTS)) for _, p in full):
        return INVALID, "team projection outside %g-%g points" % TEAM_PTS
    if not full:
        partial = any((p[0] is None) != (p[1] is None) for p in pairs)
        return ANCHOR, "partial team projection ignored by v5; fitted to the book" if partial else "no team projections"
    (first, fp) = full[0]
    for r, p in full[1:]:
        if p != fp:
            return AMBIGUOUS, "conflicting team projections on one game"
        if r["tag"] != first["tag"]:
            return AMBIGUOUS, "conflicting proj_provenance on one game's team projections"
    values = [repr(fp[0]), repr(fp[1])]
    return _component(True, first["tag"], _evidence("game|%s|%s" % (home, away), values, manifest, key))


def _prop_component(home, away, rows, player, market, manifest, key):
    grp = [r for r in rows if r.get("player") == player and r["market"] == market]
    vals = {_num(r.get("proj")) for r in grp}
    tags = {r["tag"] for r in grp}
    if "bad" in vals:
        return INVALID, "non-finite, malformed or unparseable proj for %s %s" % (player, market)
    if len(vals - {None}) > 1 or (None in vals and len(vals) > 1) or len(tags) > 1:
        return AMBIGUOUS, "conflicting proj / proj_provenance for %s %s" % (player, market)
    v = next(iter(vals))
    rng = TD_SHARE if market in TD_MARKETS else STAT_MEAN
    if v is not None and not _in(v, rng):
        return INVALID, "%s %s projection %g outside %g-%g" % ((player, market, v) + rng)
    if market in TD_MARKETS and v is None:
        return AMBIGUOUS, "%s %s needs a player touchdown share; none supplied" % (player, market)
    subject = "prop|%s|%s|%s|%s" % (home, away, player, market)
    return _component(v is not None, next(iter(tags)), "" if v is None else _evidence(subject, [repr(v)], manifest, key))


def _player_problem(home, away, rows, player):
    teams = {r.get("team", "") for r in rows if r.get("player") == player}
    if len(teams) != 1 or not teams <= {home, away}:
        return "player %r has team(s) %s; must be exactly one of %r / %r" % (player, sorted(teams), home, away)
    return ""


def classify(path, manifest=None, key=None):
    """{(game, market, player, sgp): (classification, reason)} for every NFL board row."""
    out, sgp_games = {}, {}
    boards = _read(path)
    for (home, away), rows in boards.items():
        for r in rows:
            if r.get("sgp"):
                sgp_games.setdefault(r["sgp"], set()).add((home, away))
    for (home, away), rows in boards.items():
        game = "%s @ %s" % (away, home)
        gcomp, greason = _game_component(home, away, rows, manifest, key)
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
                bad = _player_problem(home, away, rows, row["player"])
                if bad:
                    why.append(bad)
                    return [INVALID]
                c, why_ = _prop_component(home, away, rows, row["player"], row["market"], manifest, key)
                if why_:
                    why.append(why_)
                return ([gcomp] if row["market"] in TD_MARKETS else []) + [c]

            if m == "SGP" or sg:
                members = legs.get(sg, [])
                sides_ok = all(l.get("side", "").upper() in ("A", "B") and l.get("side", "") in ("A", "B") for l in members)
                problem = ""
                if not sg:
                    problem = "SGP row has no sgp id"
                elif len(sgp_games.get(sg, ())) > 1:
                    problem = "sgp id %r spans more than one game" % sg
                elif len(members) < 2:
                    problem = "sgp %r has %d leg(s); needs at least 2" % (sg, len(members))
                elif not sides_ok:
                    problem = "sgp %r has a leg whose side is not exactly A or B" % sg
                if problem:
                    why.append(problem)
                    parts = [INVALID]
                elif m == "SGP":
                    parts = [gcomp] + [c for leg in members for c in dep(leg)]
                else:
                    parts = dep(r)
            else:
                parts = dep(r)
            key_, val = (game, m, p, sg), (combine(parts), "; ".join(dict.fromkeys(w for w in why if w)))
            if key_ in out and out[key_][0] != val[0]:
                val = (AMBIGUOUS, "duplicate quote with different provenance")
            out[key_] = val
    return out
