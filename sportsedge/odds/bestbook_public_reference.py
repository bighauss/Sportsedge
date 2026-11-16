"""BestBook PUBLIC HOMEPAGE research import. NOT a sportsbook/book-original feed.

No undocumented API, session, paid content, logins or background polling.
Parses only publicly readable named-book examples from the homepage. A
BestBook-displayed price is NOT a confirmed DraftKings original quote.
Every result is PAPER/0u and has no upstream quote publication timestamp.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import stat
from urllib import request, robotparser

REPO = Path(__file__).resolve().parents[2]
HOME = "https://bestbook.app/"
ROBOTS = "https://bestbook.app/robots.txt"
AGENT = "SportsEdgeResearch/1.0"
MAX_HTML = 2_000_000
FAMILIES = ("ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP", "PERIOD",
            "ALTERNATE", "ATTD", "FIRST_TD", "TD_2PLUS", "SGP", "SPECIAL")
SPORTS = ("NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA")
HEADING = re.compile(
    r"^(?P<away>[A-Za-z][A-Za-z .&'-]{1,72}) at "
    r"(?P<home>[A-Za-z][A-Za-z .&'-]{1,72}) odds$", re.I)
MARKET_HEADER = re.compile(r"\b(Spread|Total|Moneyline)\s*:", re.I)
LINE = re.compile(r"^[+\-−]\d+(?:\.\d+)?$")
PRICE = re.compile(r"^[+\-−]\d{3,7}$")
SPREAD = re.compile(r"^\s*([A-Z]{2,4})\s*([+\-−]\d+(?:\.\d+)?)\s*"
                    r"([+\-−]\d{3,7})\s+at\s+(.+?)\s*$")
TOTAL = re.compile(r"^\s*(over|under)\s+(\d+(?:\.\d+)?)\s*"
                   r"([+\-−]\d{3,7})\s+at\s+(.+?)\s*$", re.I)
MONEY = re.compile(r"^\s*([A-Z]{2,4})\s*([+\-−]\d{3,7})"
                   r"\s+at\s+(.+?)\s*$")


class PublicReferenceError(ValueError):
    pass


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg", "head"):
            self.hidden += 1
        elif not self.hidden and tag in (
                "h1", "h2", "h3", "h4", "p", "li", "div", "article", "section", "br"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "head"):
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in (
                "h1", "h2", "h3", "h4", "p", "li", "div", "article", "section"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(" " + data + " ")


def _source_text(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_HTML:
        raise PublicReferenceError("PUBLIC_PAGE_EMPTY_OR_OVERSIZED")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise PublicReferenceError("PUBLIC_PAGE_UTF8_REQUIRED") from exc
    if re.search(r"<(?:html|body|section|h2|h3)\b", decoded[:4000], re.I):
        parser = VisibleText()
        parser.feed(decoded)
        decoded = "".join(parser.parts)
    return re.sub(r"[ \t]+", " ", decoded).replace("\r", "")


def _clock(value):
    if value is None:
        value = datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise PublicReferenceError("UTC_CAPTURE_CLOCK_REQUIRED")
    if value.utcoffset().total_seconds() != 0:
        raise PublicReferenceError("NON_UTC_CAPTURE_CLOCK")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_number(raw):
    if not PRICE.fullmatch(raw):
        raise PublicReferenceError("INVALID_DISPLAYED_AMERICAN_ODDS")
    value = int(raw.replace("−", "-"))
    if not 100 <= abs(value) <= 100000:
        raise PublicReferenceError("INVALID_DISPLAYED_AMERICAN_ODDS")
    return value


def _safe_line(raw):
    if not LINE.fullmatch(raw):
        raise PublicReferenceError("INVALID_DISPLAYED_SPREAD")
    try:
        v = Decimal(raw.replace("−", "-"))
        if not v.is_finite():
            raise ValueError
    except (ValueError, InvalidOperation):
        raise PublicReferenceError("INVALID_DISPLAYED_SPREAD") from None
    return str(v)


def _book(raw):
    value = " ".join(raw.split())
    if not value or len(value) > 48 or ";" in value or ":" in value:
        raise PublicReferenceError("INVALID_DISPLAYED_BOOK_LABEL")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 &'()._-]*", value):
        raise PublicReferenceError("INVALID_DISPLAYED_BOOK_LABEL")
    return value


def _pair(kind, body):
    halves = body.split(";")
    if len(halves) != 2:
        raise PublicReferenceError("MISSING_TWO_SIDED_DISPLAY")
    found = []
    for half in halves:
        text = " ".join(half.split())
        if kind == "SPREAD":
            match = SPREAD.fullmatch(text)
            if not match:
                raise PublicReferenceError("INVALID_DISPLAYED_SPREAD_PAIR")
            selection, line, price, book = match.groups()
            found.append((selection, _safe_line(line), _safe_number(price), _book(book)))
        elif kind == "TOTAL":
            match = TOTAL.fullmatch(text)
            if not match:
                raise PublicReferenceError("INVALID_DISPLAYED_TOTAL_PAIR")
            selection, line, price, book = match.groups()
            if Decimal(line) <= 0:
                raise PublicReferenceError("INVALID_DISPLAYED_TOTAL_LINE")
            found.append((selection.upper(), str(Decimal(line)), _safe_number(price),
                          _book(book)))
        else:
            match = MONEY.fullmatch(text)
            if not match:
                raise PublicReferenceError("INVALID_DISPLAYED_ML_PAIR")
            selection, price, book = match.groups()
            found.append((selection, "", _safe_number(price), _book(book)))
    if found[0][0] == found[1][0]:
        raise PublicReferenceError("DUPLICATE_SELECTION_ON_DISPLAY")
    if kind == "TOTAL":
        if {found[0][0], found[1][0]} != {"OVER", "UNDER"} or found[0][1] != found[1][1]:
            raise PublicReferenceError("TOTAL_SIDES_OR_LINES_MISMATCH")
    return found


def _event_blocks(text):
    lines = text.splitlines()
    active = False
    current = None
    buffer = []
    for line in lines:
        line = line.strip().lstrip("#").strip()
        if line.startswith("Best NFL odds this week"):
            active = True
            continue
        if not active:
            continue
        matched = HEADING.fullmatch(line)
        if matched:
            if current is not None:
                yield current, " ".join(buffer)
            current = matched.group(0)
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        yield current, " ".join(buffer)


def analyze(raw, *, read_at_utc=None, acquisition_mode="AUTHORIZED_LOCAL_PAGE_SNAPSHOT"):
    """Local-only parse; source-page displayed line does not confer odds freshness."""
    if acquisition_mode not in (
        "AUTHORIZED_LOCAL_PAGE_SNAPSHOT", "EXPLICIT_ONE_SHOT_PUBLIC_HOMEPAGE_GET"):
        raise PublicReferenceError("INVALID_ACQUISITION_MODE")
    stamp = _clock(read_at_utc)
    text = _source_text(raw)
    if "Best NFL odds this week" not in text:
        raise PublicReferenceError("BESTBOOK_PUBLIC_NFL_SECTION_NOT_FOUND")
    rows, gaps = [], []
    events = []
    for event_label, body in _event_blocks(text):
        if event_label in events:
            gaps.append({"event_label": event_label, "reason": "DUPLICATE_PUBLIC_EVENT_LABEL"})
            continue
        events.append(event_label)
        positions = list(MARKET_HEADER.finditer(body))
        seen_families = set()
        for i, marker in enumerate(positions):
            kind = {"spread": "SPREAD", "total": "TOTAL", "moneyline": "ML"}[
                marker.group(1).lower()]
            if kind in seen_families:
                gaps.append({"event_label": event_label, "market_family": kind,
                             "reason": "REPEATED_PUBLIC_FAMILY_BLOCK"})
                continue
            seen_families.add(kind)
            end = positions[i+1].start() if i+1 < len(positions) else len(body)
            value = body[marker.end():end].strip()
            # Drop irrelevant next-section labels; no guessing after 250 chars.
            try:
                if len(value) > 250:
                    raise PublicReferenceError("UNBOUNDED_PUBLIC_FAMILY_TEXT")
                parsed = _pair(kind, value)
            except PublicReferenceError as exc:
                gaps.append({"event_label": event_label, "market_family": kind,
                             "raw_public_family_text": value[:250],
                             "reason": str(exc)})
                continue
            for selection, line, price, book in parsed:
                rows.append({
                    "event_label": event_label, "event_id": None,
                    "market_family": kind, "period": "FG_AS_DISPLAYED_UNVERIFIED",
                    "selection_label": selection, "line": line, "price_american": price,
                    "displayed_book_label": book, "provider_market_id": None,
                    "provider_quote_id": None, "provider_original_quote_utc": None,
                    "book_direct_response_sha256": None,
                    "quote_status": "PUBLIC_PAGE_REFERENCE_UNVERIFIED",
                    "approved_stake_u": 0, "official_counted": 0,
                })
        for family in ("SPREAD", "TOTAL", "ML"):
            if family not in seen_families:
                gaps.append({"event_label": event_label, "market_family": family,
                             "reason": "NOT_CAPTURED_IN_PUBLIC_HOMEPAGE"})
    if not events:
        raise PublicReferenceError("NO_EVENT_HEADING_IN_PUBLIC_NFL_SECTION")
    duplicate_key = Counter(
        (r["event_label"], r["market_family"], r["selection_label"], r["line"])
        for r in rows
    )
    for row in rows:
        key = row["event_label"], row["market_family"], row["selection_label"], row["line"]
        if duplicate_key[key] > 1:
            row["quote_status"] = "BLOCKED_DUPLICATE_PUBLIC_OUTCOME"
    return {
        "schema": "sportsedge-bestbook-public-reference-v1",
        "source_home": HOME, "acquisition_mode": acquisition_mode,
        "source_page_sha256": "sha256:" + sha256(raw).hexdigest(),
        "source_page_bytes": len(raw), "local_page_read_utc": stamp,
        "page_publication_utc": None, "source_account_authenticated": False,
        "provider_original_quote_timestamps_verified": False,
        "provider_book_independence_verified": False,
        "source_market_completeness_verified": False,
        "claim_all_offered_markets_captured": False,
        "sports_scope_of_parser": ["NFL"],
        "not_observed_sports": [sport for sport in SPORTS if sport != "NFL"],
        "not_observed_market_families": [family for family in FAMILIES
                                         if family not in ("ML", "SPREAD", "TOTAL")],
        "event_count": len(events), "displayed_reference_quote_count": len(rows),
        "rows": rows, "missing_or_blocked_public_rows": gaps,
        "status": "PAPER_0U_PUBLIC_PAGE_RESEARCH_ONLY",
        "gate_a_closed": False, "gate_d_clv_closed": False,
        "approved_stake_u": 0, "official_counted": 0,
    }


def _private(value, *, existing=False):
    path = Path(os.path.abspath(os.fspath(value)))
    target = path.resolve()
    for candidate in (path, target):
        if candidate == REPO or REPO in candidate.parents:
            raise PublicReferenceError("PUBLIC_REPOSITORY_PATH_FORBIDDEN")
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise PublicReferenceError("SYMLINK_PUBLIC_PAGE_PATH_FORBIDDEN")
    if not path.parent.is_dir() or (path.parent.stat().st_mode & 0o077):
        raise PublicReferenceError("PRIVATE_DIRECTORY_0700_REQUIRED")
    if existing:
        if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise PublicReferenceError("ORIGINAL_PAGE_FILE_REQUIRED")
        if path.stat().st_mode & 0o077:
            raise PublicReferenceError("PRIVATE_PAGE_FILE_0600_REQUIRED")
    elif path.exists():
        raise FileExistsError("PRIVATE_PAGE_OUTPUT_MUST_BE_NEW")
    return path


def _read_source(path):
    path = _private(path, existing=True)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077
                or not 0 < metadata.st_size <= MAX_HTML):
            raise PublicReferenceError("PRIVATE_PAGE_SOURCE_INTEGRITY_FAILED")
        with os.fdopen(fd, "rb") as source:
            fd = -1
            raw = source.read(MAX_HTML + 1)
        if not 0 < len(raw) <= MAX_HTML:
            raise PublicReferenceError("PUBLIC_PAGE_EMPTY_OR_OVERSIZED")
        return raw
    finally:
        if fd >= 0:
            os.close(fd)


def _write_new(path, data):
    path = _private(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            fd = -1
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        if fd >= 0:
            os.close(fd)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _public_get(url, opener):
    if url not in (ROBOTS, HOME):
        raise PublicReferenceError("UNAPPROVED_PUBLIC_SITE_URL")
    headers = {"User-Agent": AGENT, "Accept": "text/plain" if url == ROBOTS else "text/html"}
    with opener.open(request.Request(url, headers=headers, method="GET"), timeout=12) as res:
        if getattr(res, "status", None) != 200 or res.geturl() != url:
            raise PublicReferenceError("PUBLIC_SITE_NOT_200_OR_REDIRECT")
        if url == HOME and "text/html" not in res.headers.get("Content-Type", ""):
            raise PublicReferenceError("PUBLIC_PAGE_NOT_HTML")
        raw = res.read(MAX_HTML + 1)
    if not 0 < len(raw) <= MAX_HTML:
        raise PublicReferenceError("PUBLIC_PAGE_EMPTY_OR_OVERSIZED")
    return raw


def fetch_once(*, source_policy_reviewed=False, opener=None):
    """Opt-in, bounded two-GET public home import. Never a logged-in feed."""
    if not source_policy_reviewed:
        raise PublicReferenceError("SOURCE_TERMS_REVIEW_REQUIRED")
    opener = opener or request.build_opener(_NoRedirect())
    try:
        raw_robots = _public_get(ROBOTS, opener)
        rules = robotparser.RobotFileParser()
        rules.parse(raw_robots.decode("utf-8", errors="strict").splitlines())
        if not rules.can_fetch(AGENT, HOME):
            raise PublicReferenceError("ROBOTS_POLICY_DENIES_PUBLIC_HOME")
        return _public_get(HOME, opener)
    except (OSError, UnicodeError) as exc:
        raise PublicReferenceError("PUBLIC_SITE_UNAVAILABLE_OR_ROBOTS_UNVERIFIED") from exc


def save_report(raw, report_path, *, mode, read_at_utc=None):
    result = analyze(raw, read_at_utc=read_at_utc, acquisition_mode=mode)
    serialized = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    _write_new(report_path, serialized)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    local = sub.add_parser("from-file", help="import user-permitted ORIGINAL public HTML/text")
    local.add_argument("page")
    local.add_argument("--report", required=True)
    fetch = sub.add_parser("fetch-once", help="opt-in two-GET public homepage research")
    fetch.add_argument("--raw", required=True, help="private create-once original HTML")
    fetch.add_argument("--report", required=True)
    fetch.add_argument("--source-terms-reviewed", action="store_true",
                       help="operator confirms provider policy review; not granted by this tool")
    args = p.parse_args(argv)
    if args.action == "from-file":
        raw = _read_source(args.page)
        mode = "AUTHORIZED_LOCAL_PAGE_SNAPSHOT"
    else:
        _private(args.raw)
        _private(args.report)
        if Path(args.raw).resolve() == Path(args.report).resolve():
            raise PublicReferenceError("SOURCE_EQUALS_REPORT")
        raw = fetch_once(source_policy_reviewed=args.source_terms_reviewed)
        _write_new(args.raw, raw)
        mode = "EXPLICIT_ONE_SHOT_PUBLIC_HOMEPAGE_GET"
    out = save_report(raw, args.report, mode=mode)
    print(json.dumps({field: out[field] for field in (
        "status", "event_count", "displayed_reference_quote_count",
        "gate_a_closed", "approved_stake_u")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
