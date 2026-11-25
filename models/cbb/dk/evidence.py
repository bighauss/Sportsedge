"""Parse public DraftKings / ESPN evidence into plain records (no network here).

A DK event page (https://sportsbook.draftkings.com/event/<id>) embeds
``window.__INITIAL_STATE__``; its ``pageData[<id>].data`` carries leagueId, eventName,
participants with venueRole, eventStatus and startEventDate. Prices and market IDs are
NOT in the server-rendered page (they load from an API that is not publicly reachable
from this environment), so market IDs stay empty.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone

NCAAB_MEN_LEAGUE_ID = "92483"
PAGE_KEYS = ("sportId", "leagueId", "leagueName", "eventName", "eventStatus", "startEventDate", "eventSeoId")


def parse_event_page(html: bytes | str, event_id: str) -> dict | None:
    """Return the page record for ``event_id`` or None if the page has no such event."""
    text = html.decode("utf-8", "replace") if isinstance(html, (bytes, bytearray)) else html
    marker = "window.__INITIAL_STATE__ ="
    i = text.find(marker)
    if i < 0:
        return None
    try:
        state, _ = json.JSONDecoder().raw_decode(text[i + len(marker):].lstrip())
    except ValueError:
        return None
    data = ((state.get("pageData") or {}).get(str(event_id)) or {}).get("data")
    if not isinstance(data, dict):
        return None
    rec = {k: data.get(k) for k in PAGE_KEYS}
    rec["participants"] = [{k: p.get(k) for k in ("id", "name", "venueRole")}
                           for p in data.get("participants") or [] if isinstance(p, dict)]
    return rec


def page_record(event_id, request_url, final_url, http, retrieved_utc, html: bytes):
    rec = {"event_id": str(event_id), "request_url": request_url, "final_url": final_url,
           "http": str(http), "retrieved_utc": retrieved_utc,
           "html_sha256": hashlib.sha256(html).hexdigest(), "html_bytes": len(html)}
    page = parse_event_page(html, event_id) if str(http) == "200" else None
    if page:
        rec["page"] = page
    return rec


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_utc(s: str) -> datetime:
    s = str(s).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # DK uses 7 fractional digits; trim to microseconds
    if "." in s:
        head, rest = s.split(".", 1)
        frac, _, tz = rest.partition("+")
        s = f"{head}.{frac[:6]}+{tz}" if tz else f"{head}.{frac[:6]}"
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        raise ValueError("timestamp lacks a UTC offset: " + s)
    return d.astimezone(timezone.utc)


def participants_by_role(page: dict) -> dict:
    out = {}
    for p in page.get("participants") or []:
        role = str(p.get("venueRole") or "")
        if role in out:
            return {}  # ambiguous
        out[role] = p
    return out
