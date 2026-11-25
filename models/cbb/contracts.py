"""CBB RUN IT row contracts (PAPER / 0u). The schema every CBB workstream codes against.

Minimal, stdlib-only, frozen dataclasses. Nothing here prices, fits or validates a model; it
only fixes field names, allowed status values and reason codes so the runner stages
(capture -> validate -> project -> simulate -> price -> rank -> card -> freeze -> grade -> audit)
and the parallel streams (fullgame/, dk/, halves/, players/, research/cbb_backtest/) exchange
the same rows.

Rules encoded here (not policy changes, restatements of existing policy):
  * Every market row is PAPER_0U and NON_COUNTED with approved_stake_u == 0. There is no
    counted status in this module; promotion requires a separate governance act.
  * Every quote carries a provenance label. Only AUTHENTICATED_DK_CAPTURE is an authenticated
    provider capture; screenshot/PDF/CSV/operator-transcript rows are supported ingestion paths
    but are always labeled UNAUTHENTICATED_*.
  * Every catalogued CBB market family appears in coverage with a status or a reason code,
    including families that are not implemented. Nothing is silently omitted.
  * Stars are only emitted when a calibration record for that family says VALIDATED; otherwise
    the card prints STARS_UNCALIBRATED ("n/a uncalibrated").
  * The hybrid projection is UNVALIDATED until a blend weight passes chronological validation
    (selected on validation data, evaluated on a separate untouched test set).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional, Tuple

SCHEMA_VERSION = "cbb-run-it-contracts-v1"

# ---------------------------------------------------------------- labels
PAPER_0U = "PAPER_0U"
NON_COUNTED = "NON_COUNTED"
STARS_UNCALIBRATED = "n/a uncalibrated"
HYBRID_UNVALIDATED = "UNVALIDATED"

# Canonical owner grid (model share / market share), issue #57 record. Model weight first.
CANONICAL_BLEND_WEIGHTS = (1.0, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0.0)

# Quote provenance. Only the first value is an authenticated provider capture.
PROVENANCE = (
    "AUTHENTICATED_DK_CAPTURE",          # signed-in DK session capture with event/market IDs + raw bytes hash
    "UNAUTHENTICATED_PDF",               # owner-uploaded PDF extraction
    "UNAUTHENTICATED_SCREENSHOT",        # screenshot transcription
    "UNAUTHENTICATED_CSV",               # hand/agent-built CSV with no byte provenance
    "UNAUTHENTICATED_OPERATOR_TRANSCRIPT",
)
AUTHENTICATED = "AUTHENTICATED_DK_CAPTURE"

# Market status values for a priced or rejected row.
MARKET_STATUS = (
    "PRICED_PAPER",        # priced, PAPER/0u, NON_COUNTED
    "REJECTED",            # quote existed but failed a gate (reason_code says which)
    "NOT_IMPLEMENTED",     # family has no model in the runner yet
    "NO_QUOTE",            # family modeled but no quote on the board
    "LIVE_EXCLUDED",       # quote captured at/after tip
)

# Reason codes. Stages may add a ':detail' suffix; the prefix must be one of these.
REASON_CODES = {
    "MISSING_DK_EVENT_ID": "quote has no DraftKings event id",
    "DK_EVENT_ID_CONFLICT": "one event id maps to several games or a game has several ids",
    "NO_GAME_MATCH": "team names do not match a unique slate game",
    "ORIENTATION_MISMATCH": "home/away designation disagrees with the slate",
    "ORIENTATION_INCONSISTENT": "spread sign / moneyline favourite / ladder monotonicity disagree",
    "TIP_MISMATCH": "board tip time is not within 15 minutes of the slate tip",
    "TOTALS_ORDER_UNVERIFIED": "over/under price order not verified for this board format",
    "ONE_SIDED_QUOTE": "only one side of the market was captured",
    "PRICE_INVALID": "price is not a valid American price",
    "LINE_INVALID": "line missing or unparsable",
    "STALE_QUOTE": "quote older than the configured maximum at freeze",
    "LIVE_GAME": "quote captured at or after tip",
    "QUOTE_AFTER_FREEZE": "quote captured after the card freeze",
    "GAME_NOT_PROJECTED": "projection stage passed on this game",
    "PERIOD_NOT_IMPLEMENTED": "no period model wired into the runner",
    "PLAYER_MODEL_NOT_IMPLEMENTED": "no player projection wired into the runner",
    "PLAYER_TEAM_UNKNOWN": "player team not established on the board row",
    "HALFTIME_ADJUSTED_IS_LIVE": "halftime-adjusted 2H markets are in-game; excluded pregame",
    "UNSUPPORTED_MARKET": "market string not in the CBB catalog",
    "DUPLICATE_QUOTE": "same game/period/market/line/side quoted more than once",
    "ADAPTER_NOT_LANDED": "requested adapter module is not on this branch",
    "STARTED_BEFORE_AS_OF": "game tipped at or before the run's --as-of time",
    "PROVENANCE_UNVERIFIED": "row claims an authenticated capture without a verified DK manifest",
    "PROVIDER_KEY_ABSENT": "provider credential not configured in this environment",
}

# ---------------------------------------------------------------- catalog
# (period, market) families that must ALL appear in coverage. Period codes:
#   FG, 1H, 2H_PREGAME (pregame forecast of the second half), 2H_HALFTIME_ADJUSTED (in-game).
_TEAM_MARKETS = ("SPREAD", "ML", "TOTAL", "TT_HOME", "TT_AWAY", "ALT_SPREAD", "ALT_TOTAL")
PLAYER_STATS = ("PTS", "REB", "AST", "3PM", "PRA", "PR", "PA", "RA")
MARKET_CATALOG: Tuple[Tuple[str, str], ...] = tuple(
    [(p, m) for p in ("FG", "1H", "2H_PREGAME", "2H_HALFTIME_ADJUSTED") for m in _TEAM_MARKETS]
    + [("FG", f"PLAYER_{s}_{kind}") for s in PLAYER_STATS for kind in ("OU", "AT_LEAST")]
)

# Board spellings -> catalog market. Unknown strings get UNSUPPORTED_MARKET, never guessed.
BOARD_MARKET_ALIASES = {
    "PLAYER_POINTS_AT_LEAST": "PLAYER_PTS_AT_LEAST", "PLAYER_REBOUNDS_AT_LEAST": "PLAYER_REB_AT_LEAST",
    "PLAYER_ASSISTS_AT_LEAST": "PLAYER_AST_AT_LEAST", "PLAYER_THREES_AT_LEAST": "PLAYER_3PM_AT_LEAST",
    "PLAYER_PRA_AT_LEAST": "PLAYER_PRA_AT_LEAST", "PLAYER_PR_AT_LEAST": "PLAYER_PR_AT_LEAST",
    "PLAYER_PA_AT_LEAST": "PLAYER_PA_AT_LEAST", "PLAYER_RA_AT_LEAST": "PLAYER_RA_AT_LEAST",
    "PLAYER_POINTS": "PLAYER_PTS_OU", "PLAYER_REBOUNDS": "PLAYER_REB_OU", "PLAYER_ASSISTS": "PLAYER_AST_OU",
    "PLAYER_THREES": "PLAYER_3PM_OU", "PLAYER_PRA": "PLAYER_PRA_OU", "PLAYER_PR": "PLAYER_PR_OU",
    "PLAYER_PA": "PLAYER_PA_OU", "PLAYER_RA": "PLAYER_RA_OU",
}
# Upstream provenance labels (models/cbb/dk runner_board.csv) -> contract provenance.
UPSTREAM_PROVENANCE = {
    "OWNER_PDF_SCREENSHOT_UNAUTHENTICATED": "UNAUTHENTICATED_PDF",
    "OWNER_PDF_RETRANSCRIBED_PR530_UNAUTHENTICATED": "UNAUTHENTICATED_PDF",
    "OPERATOR_TRANSCRIPT_UNAUTHENTICATED": "UNAUTHENTICATED_OPERATOR_TRANSCRIPT",
    "SCREENSHOT_UNAUTHENTICATED": "UNAUTHENTICATED_SCREENSHOT",
    "CSV_UNAUTHENTICATED": "UNAUTHENTICATED_CSV",
    # Reserved upstream; a CSV row can never prove it, so it maps to a rejection (PROVENANCE_UNVERIFIED).
    "DK_AUTHENTICATED_PROVIDER_CAPTURE": None,
}
BOARD_PERIOD_ALIASES = {"FG": "FG", "": "FG", "1H": "1H", "H1": "1H", "2H": "2H_PREGAME", "H2": "2H_PREGAME"}


def catalog_market(period: str, market: str) -> Optional[Tuple[str, str]]:
    """Map a board (period, market) to a catalog family, or None (UNSUPPORTED_MARKET)."""
    p = BOARD_PERIOD_ALIASES.get(str(period or "").strip().upper())
    m = str(market or "").strip().upper()
    m = BOARD_MARKET_ALIASES.get(m, m)
    return (p, m) if p and (p, m) in MARKET_CATALOG else None


# ---------------------------------------------------------------- rows
@dataclass(frozen=True)
class GameRow:
    game_id: str                 # provider game id used by the projection source (CBBD id in production)
    season: int
    tipoff_utc: str              # ISO Z
    tip_ct: str                  # display, America/Chicago
    home: str
    away: str
    home_team_id: str
    away_team_id: str
    neutral: Optional[bool]
    venue_status: str            # VERIFIED_TWO_SOURCE | UNVERIFIED_SINGLE_SOURCE | UNKNOWN
    dk_event_id: Optional[str] = None
    id_source: str = "CBBD"      # CBBD | ESPN_PUBLIC_REPLAY


@dataclass(frozen=True)
class MarketQuote:
    board_index: int             # 0-based row in the original board file (never re-ordered)
    period: str                  # catalog period code
    market: str                  # catalog market code
    home: str
    away: str
    line: Optional[float]        # home line for spreads; total/team-total/milestone threshold otherwise
    price_a: Optional[int]       # home / over / yes
    price_b: Optional[int]       # away / under / no (None = one-sided)
    side_a: str
    side_b: str
    dk_event_id: Optional[str]
    dk_market_id: Optional[str]
    captured_utc: Optional[str]
    tip_utc: Optional[str]
    live: bool                   # True when captured at/after tip (always excluded)
    provenance: str              # one of PROVENANCE
    player: Optional[str] = None
    source_sha256: Optional[str] = None
    source_label: Optional[str] = None   # upstream label verbatim, e.g. dk/ OWNER_PDF_SCREENSHOT_UNAUTHENTICATED
    row_key: Optional[str] = None        # upstream stable row key, e.g. dk/ runner_board row_key


@dataclass(frozen=True)
class Projection:
    """One game's three views. The independent view never reads a sportsbook price."""
    game_id: str
    view: str                    # INDEPENDENT | MARKET_NOVIG | HYBRID
    home_points: Optional[float]
    away_points: Optional[float]
    margin: Optional[float]      # home minus away
    total: Optional[float]
    sd_margin: Optional[float]
    sd_total: Optional[float]
    source: str                  # adapter id, e.g. frozen_native_cbbd / native_formula_public_replay
    status: str                  # PROJECTED | PASS | UNVALIDATED (hybrid) | NO_MARKET
    reason_code: Optional[str] = None
    blend_weight_model: Optional[float] = None


@dataclass(frozen=True)
class PricedMarket:
    game_id: str
    period: str
    market: str
    line: Optional[float]
    side: str
    price: Optional[int]
    prob_model: Optional[float]      # independent, push-aware win probability
    prob_push: Optional[float]
    prob_market_novig: Optional[float]
    prob_hybrid: Optional[float]     # at the displayed (unvalidated) weight
    fair_american: Optional[int]     # from prob_model conditional on no push
    ev_model: Optional[float]        # paper EV per 1u at the offered price (push refunds)
    ev_hybrid: Optional[float]
    stars: str = STARS_UNCALIBRATED
    status: str = "PRICED_PAPER"
    reason_code: Optional[str] = None
    counted: str = NON_COUNTED
    label: str = PAPER_0U
    approved_stake_u: int = 0
    dk_event_id: Optional[str] = None
    captured_utc: Optional[str] = None
    provenance: Optional[str] = None
    prob_source: str = "SIMULATION"  # SIMULATION | HALVES_<version> | CLOSED_FORM
    prob_challenger: Optional[float] = None   # fullgame FG1C challenger (research), when wired
    ev_challenger: Optional[float] = None
    hybrid_method: Optional[str] = None       # e.g. LOGIT_BLEND_W0.125_VALIDATION_SELECTED_OPEN
    audit_flags: Tuple[str, ...] = ()         # EV sanity flags (never caps)


@dataclass(frozen=True)
class Rejection:
    stage: str                   # validate | project | price | ...
    period: str
    market: str
    reason_code: str
    detail: str = ""
    board_index: Optional[int] = None
    game: Optional[str] = None
    provenance: Optional[str] = None


@dataclass(frozen=True)
class GradeRow:
    game_id: str
    period: str
    market: str
    line: Optional[float]
    side: str
    price: Optional[int]
    result: str                  # W | L | P | NO_SELECTION | PENDING_NO_FINAL | NOT_GRADABLE
    return_1u: Optional[float]
    prob_model: Optional[float]
    clv_cents: Optional[float] = None   # None = no closing quote captured
    label: str = PAPER_0U
    counted: str = NON_COUNTED


def row_dict(row) -> dict:
    """Plain JSON-safe dict for any contract row."""
    return asdict(row)


def check_paper(row) -> None:
    """Raise ValueError if a row claims anything other than PAPER/0u NON_COUNTED."""
    d = asdict(row)
    if d.get("label", PAPER_0U) != PAPER_0U or d.get("counted", NON_COUNTED) != NON_COUNTED \
            or d.get("approved_stake_u", 0) != 0:
        raise ValueError("CONTRACT_NON_PAPER_ROW")
    if "provenance" in d and d["provenance"] is not None and d["provenance"] not in PROVENANCE:
        raise ValueError("CONTRACT_PROVENANCE_UNKNOWN")
    if "status" in d and isinstance(row, PricedMarket) and d["status"] not in MARKET_STATUS:
        raise ValueError("CONTRACT_STATUS_UNKNOWN")
    rc = d.get("reason_code")
    if rc and rc.split(":")[0] not in REASON_CODES:
        raise ValueError("CONTRACT_REASON_CODE_UNKNOWN")
