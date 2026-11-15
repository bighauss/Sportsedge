"""Strict offline quote-board preflight R4. NEVER authenticates a sportsbook.

A syntactically valid URL, timestamp or original-bytes SHA256 cannot prove a
real pregame offer was captured. Board rows remain BLOCK/PAPER 0u, no bets.
This input may include one row per selection and two opposing selections.
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
from pathlib import Path
import re
from urllib.parse import urlparse

REQUIRED = frozenset({
    "sport", "event_id", "event_start_utc", "captured_utc", "book",
    "market", "period", "side", "price_american", "provider_quote_id",
    "receipt_sha256", "source_url",
})
OPTIONAL = frozenset({
    "line", "player_id", "team_id", "stat", "settlement",
    "provider_market_id", "upstream_provider", "upstream_book",
})
SPORTS = frozenset({"NFL", "CFB", "CBB", "NBA", "MLB", "NHL"})
MARKETS = frozenset({
    "ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP",
    "ATTD", "FIRST_TD", "TD_2PLUS", "FIRST_BASKET", "NRFI", "YRFI",
})
PERIODS = frozenset({"FG","1H","2H","1Q","2Q","3Q","4Q","F5","1IN"})
YES_NO = frozenset({"ATTD","FIRST_TD","TD_2PLUS","FIRST_BASKET","NRFI","YRFI"})
NUMERIC = frozenset({"SPREAD","TOTAL","TEAM_TOTAL","PLAYER_PROP"})
HASH = re.compile(r"[a-f0-9]{64}\Z")
ODDS = re.compile(r"[+-][0-9]{3,7}\Z")
NORMAL_MARKET = {
    "ML":"ML", "MONEYLINE":"ML", "MONEY_LINE":"ML",
    "PLAYERPROP":"PLAYER_PROP", "PROP":"PLAYER_PROP", "TEAMTOTAL":"TEAM_TOTAL",
}
NORMAL_PERIOD = {
    "FULL_GAME":"FG", "FULLGAME":"FG", "H1":"1H", "H2":"2H",
    "FIRST_HALF":"1H", "SECOND_HALF":"2H", "FIRST_FIVE":"F5",
}
NORMAL_SIDE = {"HOME":"HOME","AWAY":"AWAY","OVER":"OVER",
               "UNDER":"UNDER","YES":"YES","NO":"NO"}

def stamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip() or len(value)>70:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        d = datetime.fromisoformat(value.strip().replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return d.astimezone(timezone.utc)

def american(value: str) -> int:
    if not isinstance(value, str) or not ODDS.fullmatch(value.strip()):
        raise ValueError("INVALID_AMERICAN_PRICE")
    n=int(value.strip())
    if abs(n)<100 or abs(n)>1000000:
        raise ValueError("INVALID_AMERICAN_PRICE")
    return n

def _line(value: str, kind: str) -> str:
    value=(value or "").strip()
    if kind in YES_NO or kind=="ML":
        if kind=="ML" and value in ("","+0","-0","0","0.0"):
            return ""
        if kind in YES_NO and value=="":
            return ""
        raise ValueError("CATEGORICAL_MARKET_HAS_LINE")
    if kind in NUMERIC:
        try:
            d=Decimal(value)
        except (InvalidOperation,ValueError) as exc:
            raise ValueError("INVALID_NUMERIC_LINE") from exc
        if not d.is_finite():
            raise ValueError("INVALID_NUMERIC_LINE")
        return str(d.normalize())
    raise ValueError("UNSUPPORTED_MARKET_KIND")

def _https(value: str) -> bool:
    # Never fetch, trust or echo a supplied URL; syntax only.
    try:
        parsed=urlparse(value)
        return (parsed.scheme=="https" and bool(parsed.hostname)
                and not parsed.username and not parsed.password
                and not any(ch.isspace() for ch in value))
    except ValueError:
        return False

def _parsed_board(raw: bytes):
    if not isinstance(raw,bytes) or len(raw)>20_000_000:
        raise ValueError("INVALID_BOARD_SIZE")
    try:
        reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig"),newline=""),
            restkey=None,restval=None,strict=True)
        heads=reader.fieldnames or []
        if not heads or any(not isinstance(h,str) or not h.strip()
                             or h!=h.strip() for h in heads):
            raise ValueError("INVALID_CSV_HEADERS")
        if len({h.strip().casefold() for h in heads})!=len(heads):
            raise ValueError("DUPLICATE_CSV_HEADERS")
        if not REQUIRED.issubset(heads):
            raise ValueError("MISSING_REQUIRED_CSV_HEADERS")
        if set(heads)-(REQUIRED|OPTIONAL):
            raise ValueError("UNREGISTERED_OR_SECRET_CSV_COLUMN")
        rows=list(reader)
        if any(None in r or any(v is None for v in r.values()) for r in rows):
            raise ValueError("RAGGED_CSV_ROW")
        if not rows:raise ValueError("EMPTY_BOARD")
        return rows
    except (UnicodeError,csv.Error) as exc:
        raise ValueError("INVALID_BOARD_CSV") from exc

def validate(path):
    """Sanitized deterministic report; no provider authentication is implied."""
    raw=Path(path).read_bytes()
    result={"status":"BLOCK","official_counted":0,"approved_stake_u":0,
            "input_sha256":"sha256:"+sha256(raw).hexdigest(),
            "rows":0,"errors":[],"structural_rows_clean":0,
            "structural_ok":False,
            "source_authenticated":False,
            "bookmaker_independence_authenticated":False,
            "note":"Unverified offline board; 0u even if structurally clean."}
    try:
        rows=_parsed_board(raw)
    except ValueError as e:
        result["errors"].append({"row":1,"reasons":[str(e)]})
        return result
    starts={}
    seen=set()
    quotes=set()
    for n,r in enumerate(rows,2):
        errors=[]
        get=lambda k: (r.get(k) or "").strip()
        for k in REQUIRED:
            if not get(k):
                errors.append("MISSING_"+k.upper())
        sport=get("sport").upper()
        if sport not in SPORTS:errors.append("UNSUPPORTED_SPORT")
        event=get("event_id")
        book=get("book").casefold()
        if not event:errors.append("MISSING_EVENT_ID")
        kind=NORMAL_MARKET.get(get("market").upper(),get("market").upper())
        if kind not in MARKETS:errors.append("UNSUPPORTED_MARKET")
        period=NORMAL_PERIOD.get(get("period").upper(),get("period").upper())
        if period not in PERIODS:errors.append("UNSUPPORTED_PERIOD")
        side=NORMAL_SIDE.get(get("side").upper(),"")
        try:
            if kind=="ML" or kind=="SPREAD":
                if side not in ("HOME","AWAY"):
                    errors.append("MARKET_SIDE_MISMATCH")
            elif kind in ("TOTAL","TEAM_TOTAL","PLAYER_PROP"):
                if side not in ("OVER","UNDER"):
                    errors.append("MARKET_SIDE_MISMATCH")
            elif kind in YES_NO and side not in ("YES","NO"):
                errors.append("MARKET_SIDE_MISMATCH")
            line=_line(get("line"),kind)
        except ValueError as exc:
            line=""
            errors.append(str(exc))
        if kind in {"PLAYER_PROP","ATTD","FIRST_TD","TD_2PLUS","FIRST_BASKET"} and not get("player_id"):
            errors.append("PLAYER_ID_REQUIRED")
        if kind=="PLAYER_PROP" and not get("stat"):
            errors.append("PLAYER_PROP_STAT_REQUIRED")
        if kind=="TEAM_TOTAL" and not get("team_id"):
            errors.append("TEAM_TOTAL_ID_REQUIRED")
        try:
            captured,start=stamp(get("captured_utc")),stamp(get("event_start_utc"))
            if captured>=start:errors.append("POST_START_CAPTURE")
            ev=(sport,event)
            if ev in starts and starts[ev]!=start:
                errors.append("CONFLICTING_EVENT_START")
            starts.setdefault(ev,start)
            timekey=captured.isoformat()
        except ValueError:
            timekey=get("captured_utc")
            errors.append("INVALID_TIMESTAMP")
        try:american(get("price_american"))
        except ValueError:errors.append("INVALID_AMERICAN_PRICE")
        h=get("receipt_sha256").lower()
        if not HASH.fullmatch(h):errors.append("INVALID_RECEIPT_HASH")
        if not _https(get("source_url")):errors.append("INVALID_SOURCE_URL")
        idq=(book,get("provider_quote_id").casefold())
        if idq in quotes:errors.append("REUSED_PROVIDER_QUOTE_ID")
        quotes.add(idq)
        identity=(sport,event,book,kind,period,side,line,get("team_id"),
                  get("player_id"),get("stat").upper(),get("settlement").upper(),
                  timekey)
        if identity in seen:errors.append("DUPLICATE_SELECTION_SNAPSHOT")
        seen.add(identity)
        if errors:result["errors"].append({"row":n,"reasons":sorted(set(errors))})
        else:result["structural_rows_clean"]+=1
    # R4 originally checked rows independently; a one-sided/mispaired board
    # could appear clean. Canonical pair audit is now part of actual validate().
    # This remains an offline, unauthenticated PAPER/0u validator.
    from research.audit.r4_pairing_adversarial import audit_rows
    combined = {e["row"]: set(e["reasons"]) for e in result["errors"]}
    for e in audit_rows(rows):
        combined.setdefault(e["row"], set()).update(e["reasons"])
    result["errors"] = [{"row": number, "reasons": sorted(reasons)}
                        for number, reasons in sorted(combined.items())]
    result["structural_rows_clean"] = len(rows) - len(combined)
    result["structural_ok"] = not combined
    result["rows"] = len(rows)
    return result

def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("board")
    parser.add_argument("--report")
    args=parser.parse_args(argv)
    result=validate(args.board)
    body=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if args.report:
        with open(args.report,"x",encoding="utf-8") as f:f.write(body)
    else:print(body,end="")
    return 2  # Deliberate: offline research-only validator never promotes.

if __name__=="__main__":
    raise SystemExit(main())
