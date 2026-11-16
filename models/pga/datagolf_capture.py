"""Authenticated, read-only DataGolf capture with original bytes and audit receipt.

No API requests occur without a caller-provided key or DATAGOLF_API_KEY.
Do not print request URLs: DataGolf uses a query-string key.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://feeds.datagolf.com"
ENDPOINTS = {
    "players": ("/get-player-list", {}),
    "schedule": ("/get-schedule", {"tour": {"pga", "euro", "kft", "all"}}),
    "field": ("/field-updates", {"tour": {"pga", "euro", "kft", "opp", "alt", "upcoming_pga"}}),
    "rankings": ("/preds/get-dg-rankings", {}),
    "skill": ("/preds/skill-ratings", {"display": {"value", "rank"}}),
    "decompositions": ("/preds/player-decompositions", {"tour": {"pga", "euro", "opp", "alt"}}),
    "pregame": ("/preds/pre-tournament", {"tour": {"pga", "euro", "kft", "opp", "alt"}}),
    "live_stats": ("/preds/live-tournament-stats", {"round": {"event_avg", "event_cumulative", "1", "2", "3", "4"}, "display": {"value", "rank"}}),
    "live_predictions": ("/preds/in-play", {"tour": {"pga", "euro", "opp", "kft", "alt"}}),
    "outrights": ("/betting-tools/outrights", {"tour": {"pga", "euro", "kft", "opp", "alt"}, "market": {"win", "top_5", "top_10", "top_20", "mc", "make_cut", "frl"}}),
    "matchups": ("/betting-tools/matchups", {"tour": {"pga", "euro", "opp", "alt"}, "market": {"tournament_matchups", "round_matchups", "3_balls"}}),
    "historical_event_list": ("/historical-raw-data/event-list", {"tour": {"pga", "euro", "kft"}}),
    "historical_rounds": ("/historical-raw-data/rounds", {"tour": {"pga", "euro", "kft"}}),
    "pregame_archive": ("/preds/pre-tournament-archive", {}),
}
REQUIRED = {"outrights": {"market"}, "matchups": {"market"}, "historical_rounds": {"tour", "event_id", "year"}}
ALLOWED_EXTRA = {"year", "event_id", "season", "upcoming_only", "stats", "add_position", "dead_heat", "odds_format", "slate", "site"}

def capture(endpoint, *, params=None, api_key=None, opener=urlopen, clock=None, timeout=15):
    if endpoint not in ENDPOINTS:
        raise ValueError("UNSUPPORTED_ENDPOINT")
    key = api_key if api_key is not None else os.environ.get("DATAGOLF_API_KEY")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("DATAGOLF_API_KEY_REQUIRED")
    params = {} if params is None else params
    if not isinstance(params, dict):
        raise ValueError("INVALID_PARAMS")
    path, constraints = ENDPOINTS[endpoint]
    if REQUIRED.get(endpoint, set()) - params.keys():
        raise ValueError("REQUIRED_PARAMS_MISSING")
    if set(params) - (set(constraints) | ALLOWED_EXTRA):
        raise ValueError("UNSUPPORTED_PARAMS")
    for name, value in params.items():
        if not isinstance(value, (str, int)) or isinstance(value, bool) or len(str(value)) > 128:
            raise ValueError("INVALID_PARAM_VALUE")
        if name in constraints and str(value) not in constraints[name]:
            raise ValueError("INVALID_PARAM_CHOICE")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
        raise ValueError("INVALID_TIMEOUT")
    query = urlencode({**params, "file_format": "json", "key": key})
    req = Request(BASE + path + "?" + query, headers={"Accept": "application/json", "User-Agent": "SportsEdge-PGA/1"})
    with opener(req, timeout=timeout) as response:
        raw = response.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError("RESPONSE_TOO_LARGE")
    payload = json.loads(raw)
    if not isinstance(payload, (list, dict)):
        raise ValueError("INVALID_RESPONSE_SHAPE")
    if isinstance(payload, dict) and any(k in payload for k in ("error", "errors", "message")):
        raise ValueError("PROVIDER_ERROR_RESPONSE")
    now = clock() if clock else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_CLOCK_REQUIRED")
    return {"endpoint": endpoint, "params": dict(params),
            "captured_utc": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "raw_bytes": raw, "source_sha256": hashlib.sha256(raw).hexdigest(),
            "payload": payload, "status": "UNVERIFIED_RESEARCH_PAPER_0U"}
