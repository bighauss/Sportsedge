"""Extracted-content loader with design §5 point-in-time enforcement.

Loads the per-event extracted-content JSON files produced by the
G-PGA-2 extraction of record (``PGA_DG_CONTENT_EXTRACT_V1``): one file
per event, keyed by the composite ``(event_id, calendar_year)`` —
design §5 makes composite keys a hard rule (an event_id-only key is
the exact lookahead class §5 names).

Schema per file: ``event_id``, ``calendar_year``, ``season``, ``date``
(ISO, the event's final day as published), ``name``, ``num_rounds``,
``rows``. Each row: ``dg_id``, ``player_name``, ``fin``, ``owgr_rank``,
``open``, ``close``, ``rounds`` (``{r, score, sg, par}``), and an
``excluded`` sub-object holding ``dg_pts`` / ``dg_rank``.

The loader NEVER exposes ``dg_pts`` (Amendment 1 §3.1: it is an
outcome field — lookahead — and is disqualified) or ``dg_rank``
(Amendment 1 §3.1: not used). They are dropped at load.

Validity rules enforced here:
- ``owgr_rank`` is valid iff an integer >= 1; the corpus sentinels
  -9999 / -9998 and any other non-conforming value mean NO RANK
  (Amendment 1 §3.2 step 1).
- ``close`` (reference (a)) is valid iff present, not the -9999
  sentinel, and > 1.0 (readings register R-REFA-1).

Point-in-time: :meth:`Corpus.events_before` is the only history view
the feature builder uses; it returns events dated STRICTLY BEFORE the
target event's date (R-SKILL-1: a round's date is its event's date),
so an event's own rounds and anything later can never enter its
features (design §5: features use only rounds completed before the
event's first tee time; the archive carries no per-round dates, so
event-date granularity is the enforceable form).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from . import config


class LoaderError(ValueError):
    """Raised on schema violations in extracted content."""


def valid_owgr_rank(value) -> Optional[int]:
    """Return the rank if valid per Amendment 1 §3.2 step 1, else None."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value in config.OWGR_RANK_SENTINELS:
        return None
    return value if value >= 1 else None


def valid_close(value) -> Optional[float]:
    """Return the outright Close odds if valid per R-REFA-1, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    if v == config.CLOSE_ODDS_SENTINEL or v <= 1.0:
        return None
    return v


@dataclass(frozen=True)
class Round:
    r: int
    score: Optional[float]
    sg: Optional[float]


@dataclass(frozen=True)
class PlayerRow:
    dg_id: int
    player_name: str
    fin: Optional[str]
    owgr_rank: Optional[int]  # validity-resolved (None = no rank)
    close: Optional[float]    # validity-resolved outright Close odds
    rounds: Tuple[Round, ...]

    @property
    def measured_rounds(self) -> int:
        """Rounds with an SG value (R-SKILL-3's 'measured rounds')."""
        return sum(1 for rd in self.rounds if rd.sg is not None)


@dataclass(frozen=True)
class Event:
    event_id: str
    calendar_year: int
    season: int
    date: date
    name: str
    num_rounds: int
    rows: Tuple[PlayerRow, ...]
    source_file: str

    @property
    def key(self) -> Tuple[str, int]:
        """Composite (event_id, year) key — design §5."""
        return (self.event_id, self.calendar_year)

    def row_for(self, dg_id: int) -> Optional[PlayerRow]:
        for r in self.rows:
            if r.dg_id == dg_id:
                return r
        return None


def _parse_row(raw, where: str) -> PlayerRow:
    if not isinstance(raw, dict):
        raise LoaderError(f"{where}: row is not an object")
    dg_id = raw.get("dg_id")
    if isinstance(dg_id, bool) or not isinstance(dg_id, int):
        raise LoaderError(f"{where}: row dg_id missing or not an int")
    rounds = []
    for rd in raw.get("rounds") or []:
        if not isinstance(rd, dict) or "r" not in rd:
            raise LoaderError(f"{where}: malformed round entry")
        score = rd.get("score")
        sg = rd.get("sg")
        rounds.append(Round(
            r=int(rd["r"]),
            score=float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None,
            sg=float(sg) if isinstance(sg, (int, float)) and not isinstance(sg, bool) else None,
        ))
    # NOTE: raw["excluded"] (dg_pts / dg_rank) is deliberately never read.
    return PlayerRow(
        dg_id=dg_id,
        player_name=str(raw.get("player_name", "")),
        fin=raw.get("fin"),
        owgr_rank=valid_owgr_rank(raw.get("owgr_rank")),
        close=valid_close(raw.get("close")),
        rounds=tuple(rounds),
    )


def parse_event(raw, source_file: str = "<memory>") -> Event:
    """Validate and build one Event from an extracted-content object."""
    if not isinstance(raw, dict):
        raise LoaderError(f"{source_file}: event payload is not an object")
    for k in ("event_id", "calendar_year", "date", "rows"):
        if k not in raw:
            raise LoaderError(f"{source_file}: missing key {k!r}")
    try:
        ev_date = date.fromisoformat(str(raw["date"]))
    except ValueError as e:
        raise LoaderError(f"{source_file}: bad date {raw['date']!r}") from e
    rows = tuple(_parse_row(r, source_file) for r in raw["rows"])
    ids = [r.dg_id for r in rows]
    if len(ids) != len(set(ids)):
        raise LoaderError(f"{source_file}: duplicate dg_id within event")
    return Event(
        event_id=str(raw["event_id"]),
        calendar_year=int(raw["calendar_year"]),
        season=int(raw.get("season", raw["calendar_year"])),
        date=ev_date,
        name=str(raw.get("name", "")),
        num_rounds=int(raw.get("num_rounds", 4)),
        rows=rows,
        source_file=source_file,
    )


@dataclass
class Corpus:
    events: Dict[Tuple[str, int], Event] = field(default_factory=dict)

    def sorted_events(self) -> List[Event]:
        return sorted(self.events.values(), key=lambda e: (e.date, e.event_id))

    def events_before(self, when: date) -> List[Event]:
        """Events dated strictly before ``when`` — the only PIT history."""
        return [e for e in self.sorted_events() if e.date < when]

    def events_in_fit_window(self, test_season: int) -> List[Event]:
        """Design §6 fit window for a test season: events before Jan 1."""
        return self.events_before(date(test_season, 1, 1))

    def test_events(self, season: int) -> List[Event]:
        return [e for e in self.sorted_events() if e.season == season]


def _is_manifest_payload(raw) -> bool:
    """True iff ``raw`` is a packet-manifest payload, not an event.

    CANDIDATE R1 GOVERNED FIX (loader only): the extracted-content
    directory legitimately contains the packet's own manifest
    (``content_manifest.json`` — the G-PGA-2 content pin list) beside
    the per-event files. The original loader fed it to
    :func:`parse_event`, which raised ``missing key 'event_id'`` and
    made every real-corpus run crash before any fit or score.

    Skip rule (narrow, fail-closed): a parsed payload is skipped
    ONLY when it is manifest-shaped — a dict carrying an ``events``
    list AND a ``corpus_sha256`` string, and carrying NEITHER
    ``event_id`` NOR ``rows`` (the two keys every event payload has).
    The filename alone never suffices: a file named
    ``content_manifest.json`` whose payload is not manifest-shaped
    is NOT skipped and still raises via :func:`parse_event`. A
    malformed event (has ``event_id`` but is otherwise broken) and
    any JSON that is neither event nor manifest still raise.
    """
    if not isinstance(raw, dict):
        return False
    if "event_id" in raw or "rows" in raw:
        return False
    if not isinstance(raw.get("events"), list):
        return False
    return isinstance(raw.get("corpus_sha256"), str)


def load_corpus(corpus_dir: str) -> Corpus:
    """Load every extracted-content JSON in ``corpus_dir``.

    Duplicate composite (event_id, year) keys are a hard error (§5).
    This loader performs NO gate check and NO fitting: authorization
    for a screen run is the gate's job (see gate.py / screen.py).

    Candidate R1: manifest-shaped payloads (see
    :func:`_is_manifest_payload`) are skipped; every other file is
    parsed as an event exactly as in the original loader, so
    malformed events and unknown-shaped JSONs still raise.
    """
    if not os.path.isdir(corpus_dir):
        raise LoaderError(f"corpus dir not found: {corpus_dir}")
    corpus = Corpus()
    for fname in sorted(os.listdir(corpus_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(corpus_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if _is_manifest_payload(raw):
            continue
        ev = parse_event(raw, source_file=fname)
        if ev.key in corpus.events:
            raise LoaderError(
                f"duplicate composite key {ev.key}: {fname} vs "
                f"{corpus.events[ev.key].source_file} (design §5)"
            )
        corpus.events[ev.key] = ev
    if not corpus.events:
        raise LoaderError(f"no event files in {corpus_dir}")
    return corpus
