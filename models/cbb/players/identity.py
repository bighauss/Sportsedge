"""Event and player identity for CBB prop rows (fail-closed).

Event: both team names (cbb_run_it.norm/cands aliases, dated aliases allowed
only with an exact tip) and the exact UTC tip must match exactly one ESPN
schedule game. Player: sportsedge_cbb_model.resolve_prop_player (#292 logic,
restricted to the two event teams, unique match or a reason code). A second,
normalized-name pass (accents, punctuation, Jr/Sr/II-V suffixes) uses the same
function and is labelled; ambiguity never resolves by first match.
"""
import csv
from datetime import date, datetime, timezone
import re
import unicodedata

from cbb_run_it import cands, norm                    # reuse RUN IT aliasing
from sportsedge_cbb_model import resolve_prop_player   # #292 logic (frozen file, read-only)

SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def norm_person(name):
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`’]", "", s)
    s = SUFFIX.sub(" ", s.replace("-", " "))
    return " ".join(s.split())


def parse_utc(s):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError("UTC_Z_TIMESTAMP_REQUIRED")
    d = datetime.fromisoformat(s[:-1] + "+00:00")
    return d.astimezone(timezone.utc)


def resolve_event(away, home, tip_utc, schedule):
    """schedule: dicts with game_id, start_date ('...Z'), home/away location, short name, ids."""
    tip = parse_utc(tip_utc)
    def names(g, side):
        return {norm(g[f"{side}_location"]), norm(g[f"{side}_short_display_name"])}
    ca, ch = set(cands(away, dated=True)), set(cands(home, dated=True))
    hits = []
    for g in schedule:
        if parse_utc(g["start_date"]) != tip:
            continue
        if ca & names(g, "away") and ch & names(g, "home"):
            hits.append((g, False))
        elif ca & names(g, "home") and ch & names(g, "away"):
            hits.append((g, True))
    if not hits:
        return None, "EVENT_NOT_FOUND_EXACT_NAMES_AND_TIP"
    if len(hits) > 1:
        return None, "EVENT_AMBIGUOUS"
    g, flipped = hits[0]
    if flipped:
        return None, "EVENT_HOME_AWAY_ORIENTATION_CONFLICT"
    return g, None


def load_rosters(path, team_ids, cutoff):
    """{team_id: {athlete_id: display_name}} from box rows dated <= cutoff (DNP rows count)."""
    out = {t: {} for t in team_ids}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            t = r.get("team_id")
            if t in out and date.fromisoformat(r["game_date"]) <= cutoff:
                out[t][r["athlete_id"]] = r["athlete_display_name"]
    return out


def resolve_player(name, home_id, away_id, rosters):
    """Return (athlete_id, team_id, method) or (None, None, reason)."""
    game = {"home": home_id, "away": away_id}
    for method, f in (("EXACT_DISPLAY_NAME", lambda s: s.strip()), ("NORMALIZED_NAME", norm_person)):
        players = {t: [{"player": f(n), "player_id": pid, "team": t} for pid, n in rosters.get(t, {}).items()]
                   for t in (home_id, away_id)}
        pl, reason = resolve_prop_player(game, {"player": f(name)}, players)
        if pl is not None:
            return pl["player_id"], pl["team"], method
        if reason != "PROP_PLAYER_NOT_ON_EVENT_ROSTER":
            return None, None, reason
    return None, None, "PROP_PLAYER_NOT_ON_EVENT_ROSTER"
