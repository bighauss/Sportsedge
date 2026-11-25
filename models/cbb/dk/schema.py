"""Plain row schemas and reason codes shared with the runner (see docs/cbb/dk_interface.md)."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict, fields

SCHEMA_VERSION = "sportsedge-cbb-dk-derived-v1"

# Provenance labels. Nothing currently on main is an authenticated provider capture.
PROV_PDF = "OWNER_PDF_SCREENSHOT_UNAUTHENTICATED"
PROV_PDF_RETRANSCRIBED = "OWNER_PDF_RETRANSCRIBED_PR530_UNAUTHENTICATED"
PROV_TRANSCRIPT = "OPERATOR_TRANSCRIPT_UNAUTHENTICATED"
PROV_AUTHENTICATED = "DK_AUTHENTICATED_PROVIDER_CAPTURE"  # reserved; no rows use it yet

# Event-ID evidence states
EID_VERIFIED = "VERIFIED_PUBLIC_DK_EVENT_PAGE"
EID_BOARD_VERIFIED = "BOARD_ID_CONFIRMED_PUBLIC_DK_EVENT_PAGE"
EID_MISSING = "MISSING"

# Dispositions
ACCEPTED = "ACCEPTED"             # usable by the runner (still PAPER/0u, NON_COUNTED)
HELD = "HELD"                     # identity/price fine, but a governance or verification hold applies
REJECTED = "REJECTED"
SUPERSEDED = "SUPERSEDED"         # a later capture of the same market exists

REASONS = {
    # identity
    "DK_EVENT_ID_MISSING": "No DraftKings event ID could be verified from a public DK source; never guessed.",
    "DK_EVENT_TEAM_MISMATCH": "DK event page participants/venue roles do not match board away/home.",
    "DK_EVENT_TIP_MISMATCH": "DK startEventDate differs from board tip_utc by more than the tolerance.",
    "DK_EVENT_NOT_NCAAB_MEN": "DK event page is not leagueId 92483 (College Basketball (M)).",
    "ESPN_EVENT_UNMATCHED": "No unique ESPN scoreboard event for this matchup/tip (venue/neutral unknown).",
    # time
    "LIVE_AT_CAPTURE": "Quote captured at or after tip; live quotes are excluded.",
    "STARTED_BEFORE_AS_OF": "Game tipped before the run's as-of time; not a pregame quote for this run.",
    # prices / market identity
    "ONE_SIDED_QUOTE": "Only one side priced (e.g. DK milestone 'N+' offer); no no-vig pair.",
    "PLAYER_TEAM_NOT_ESTABLISHED": "Board does not establish which team the player is on.",
    "PRICE_INVALID_AMERICAN": "A price is not a valid American price (|odds| >= 100).",
    "PRICE_PAIR_IMPLAUSIBLE": "Two-way implied probability sum outside [1.00, 1.15].",
    "LINE_INVALID": "Line missing, non-half-point where required, or outside the plausible range.",
    "LINE_TRUNCATED_SUPERSEDED_PR530": "Original PDF row had a truncated line/price; replaced by the PR #530 re-transcription.",
    "ORIENTATION_SPREAD_VS_ML_CONFLICT": "Spread favourite and moneyline favourite disagree under price_a=home.",
    "TT_INCONSISTENT_WITH_MAIN": "Team totals inconsistent with main total/spread (|diff| > tolerance).",
    "TOTALS_ORDER_UNVERIFIED": "No in-board evidence that price_a=over for this matchup's totals.",
    "TOTALS_ORDER_CONFLICT": "Alternate-total vs main-total prices contradict price_a=over.",
    "ALT_SPREAD_ORIENTATION_CONFLICT": "Alternate-spread vs main-spread prices contradict price_a=home.",
    "UNSUPPORTED_MARKET": "Market family not consumable by the runner contract (kept for coverage).",
    "SELECTED_RUNG_ONLY": "Only the selected alternate rung is visible; the rest of the ladder is not captured.",
    # governance
    "ISSUE57_ORIENTATION_HOLD": "Issue #57 directs both 9 AM orientation captures to be withheld pending owner verification.",
    "SUPERSEDED_BY_LATER_CAPTURE": "A later capture of the same market (same event/period/market/line/player) exists.",
    "UNAUTHENTICATED_SOURCE": "Row comes from a PDF/screenshot/transcript, not an authenticated provider capture.",
}

@dataclass
class DerivedRow:
    # runner-compatible leading columns (same names as the original boards)
    sport: str
    away: str
    home: str
    market: str
    line: str
    price_a: str
    price_b: str
    period: str
    player: str
    tip_utc: str
    captured_utc: str
    dk_event_id: str
    # added by this module
    row_key: str = ""
    capture_id: str = ""
    source_file: str = ""
    source_row: int = 0
    provenance: str = ""
    authenticated: int = 0
    dk_event_id_state: str = EID_MISSING
    dk_event_url: str = ""
    dk_event_retrieved_utc: str = ""
    dk_start_utc: str = ""
    dk_market_id: str = ""          # not recoverable from public pages (see docs/cbb/dk_reconciliation_2026-11-25.md)
    away_canonical: str = ""
    home_canonical: str = ""
    espn_event_id: str = ""
    neutral_site: str = ""          # "1"/"0"/"" (ESPN at retrieval)
    venue: str = ""
    tip_ct: str = ""
    implied_a: str = ""
    implied_b: str = ""
    novig_a: str = ""
    novig_b: str = ""
    totals_order: str = ""          # over_under when supported by in-board evidence
    disposition: str = ""
    reason_codes: str = ""          # ';'-joined
    notes: str = ""
    label: str = "PAPER_0U"
    official_counted: int = 0
    approved_stake_u: int = 0

    @classmethod
    def columns(cls):
        return [f.name for f in fields(cls)]

    def as_dict(self):
        return asdict(self)

LEDGER_COLUMNS = ["row_key", "capture_id", "source_file", "source_row", "away", "home", "period",
                  "market", "line", "player", "price_a", "price_b", "disposition", "reason_codes",
                  "reason_text", "notes"]
