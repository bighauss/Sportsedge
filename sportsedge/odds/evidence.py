"""Offline source-to-card evidence contracts. No live adapter and NO bet authorization.

Never promote a quote because it contains an auth string, hash, or matching number.
All inputs are untrusted until their upstream provenance is independently verified.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any
import json
import re

SHA_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
SPORTS = frozenset({"NFL","CFB","CBB","NBA","MLB"})
FOOTBALL = frozenset({"NFL","CFB"})
BASKETBALL = frozenset({"CBB","NBA"})
PERIODS = frozenset({"FG", "1H", "2H", "1Q", "2Q", "3Q", "4Q", "F5", "1IN"})
KINDS = frozenset({"MONEYLINE", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP", "ATTD", "FIRST_TD", "TD_2PLUS", "FIRST_BASKET", "NRFI", "YRFI"})
SIDES = frozenset({"HOME", "AWAY", "OVER", "UNDER", "YES", "NO"})
YES_NO = frozenset({"ATTD","FIRST_TD","TD_2PLUS","FIRST_BASKET","NRFI","YRFI"})
NUMERIC = frozenset({"SPREAD","TOTAL","TEAM_TOTAL","PLAYER_PROP"})
SETTLEMENTS = frozenset({"REGULATION","INCLUDES_OT","POSTED_RULES"})


def utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("UTC_TIME_REQUIRED:" + label)
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("NON_UTC_TIMESTAMP:" + label)
    return value.astimezone(timezone.utc)


def valid_sha(value: str, label: str) -> None:
    if not isinstance(value, str) or not SHA_PATTERN.fullmatch(value):
        raise ValueError("INVALID_SHA256:" + label)


def dec(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("INVALID_DECIMAL:" + label)
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("INVALID_DECIMAL:" + label) from None
    if not d.is_finite():
        raise ValueError("INVALID_DECIMAL:" + label)
    return d


def american(value: Any) -> int:
    d = dec(value, "american_price")
    if d != d.to_integral_value() or abs(d) < 100:
        raise ValueError("INVALID_AMERICAN_ODDS")
    return int(d)


def implied(odds: int) -> Decimal:
    a = Decimal(american(odds))
    return (Decimal(100) / (a + 100)) if a > 0 else (-a / (100 - a))


@dataclass(frozen=True, slots=True)
class MarketKey:
    """Exact canonical identity. Team/participant IDs must be versioned externally."""
    sport: str
    event_id: str
    kind: str
    period: str
    side: str
    line: str = ""
    team_id: str = ""
    player_id: str = ""
    stat: str = ""
    settlement: str = "REGULATION"

    def __post_init__(self) -> None:
        for k in ("sport", "event_id", "kind", "period", "side", "settlement"):
            v = getattr(self, k)
            if not isinstance(v, str) or not v.strip() or v != v.strip():
                raise ValueError("INVALID_MARKET_ID:" + k)
        if self.kind == "ML":
            # Versioned adapters may emit either spelling. Reconcile exactly.
            object.__setattr__(self, "kind", "MONEYLINE")
        if self.sport not in SPORTS or self.kind not in KINDS:
            raise ValueError("INVALID_SPORT_OR_MARKET_KIND")
        if self.period not in PERIODS or self.side not in SIDES:
            raise ValueError("INVALID_PERIOD_OR_SIDE")
        if self.settlement not in SETTLEMENTS:
            raise ValueError("UNKNOWN_SETTLEMENT_CONTRACT")
        if self.sport=="MLB" and self.period not in {"FG","F5","1IN"}:
            raise ValueError("PERIOD_UNSUPPORTED_FOR_BASEBALL")
        if self.sport!="MLB" and self.period in {"F5","1IN"}:
            raise ValueError("BASEBALL_PERIOD_ON_OTHER_SPORT")
        if self.kind in ("NRFI","YRFI") and (self.sport!="MLB" or self.period!="1IN"):
            raise ValueError("FIRST_INNING_ONLY_MLB")
        if self.kind=="FIRST_BASKET" and (self.sport not in BASKETBALL or self.period!="FG"):
            raise ValueError("FIRST_BASKET_ONLY_BASKETBALL_FG")
        if self.kind in ("ATTD","FIRST_TD","TD_2PLUS") and self.sport not in FOOTBALL:
            raise ValueError("TOUCHDOWN_MARKET_ONLY_FOOTBALL")
        if self.kind in ("MONEYLINE","SPREAD"):
            if self.side not in ("HOME","AWAY"):
                raise ValueError("TEAM_SIDE_REQUIRED")
        elif self.kind in ("TOTAL","TEAM_TOTAL","PLAYER_PROP"):
            if self.side not in ("OVER","UNDER"):
                raise ValueError("OVER_UNDER_REQUIRED")
        elif self.kind in YES_NO:
            if self.side not in ("YES","NO"):
                raise ValueError("YES_NO_REQUIRED")
        if self.kind == "MONEYLINE":
            if self.line not in ("", "0", "0.0", "+0", "-0"):
                raise ValueError("ML_LINE_MUST_BE_EMPTY")
            object.__setattr__(self, "line", "")
        elif self.kind in YES_NO:
            if self.line != "":
                raise ValueError("YES_NO_MARKET_CANNOT_HAVE_LINE")
        else:
            d=dec(self.line, "line")
            if self.kind!="SPREAD" and d<0:
                raise ValueError("NEGATIVE_OVER_UNDER_LINE")
            object.__setattr__(self, "line", str(d.normalize()))
        if self.kind == "PLAYER_PROP" and not (self.player_id and self.stat):
            raise ValueError("MISSING_PLAYER_OR_STAT_ID")
        if self.kind in ("ATTD","FIRST_TD","TD_2PLUS","FIRST_BASKET") and not self.player_id:
            raise ValueError("MISSING_PLAYER_ID")
        if self.kind == "TEAM_TOTAL" and not self.team_id:
            raise ValueError("MISSING_TEAM_ID")
        for field in ("team_id","player_id","stat","event_id"):
            value=getattr(self,field)
            if not isinstance(value,str) or value!=value.strip():
                raise ValueError("INVALID_MARKET_PARTICIPANT_ID:"+field)

    def key(self) -> tuple[str, ...]:
        return (self.sport, self.event_id, self.kind, self.period,
                self.side, self.line, self.team_id, self.player_id,
                self.stat, self.settlement)


@dataclass(frozen=True, slots=True)
class QuoteReceipt:
    market: MarketKey
    quote_id: str
    provider: str
    upstream_book: str
    upstream_provider: str
    provider_event_id: str
    provider_market_id: str
    odds_american: int
    observed_at_utc: datetime
    ingested_at_utc: datetime
    game_start_utc: datetime
    payload_sha256: str
    receipt_id: str
    source_auth_method_claim: str = "UNVERIFIED"

    def __post_init__(self) -> None:
        for k in ("quote_id", "provider", "upstream_book", "upstream_provider",
                  "provider_event_id", "provider_market_id", "receipt_id"):
            v = getattr(self, k)
            if not isinstance(v, str) or not v.strip():
                raise ValueError("MISSING_QUOTE_FIELD:" + k)
        valid_sha(self.payload_sha256, "payload")
        american(self.odds_american)
        observed = utc(self.observed_at_utc, "observed")
        ingested = utc(self.ingested_at_utc, "ingested")
        start = utc(self.game_start_utc, "start")
        if observed > ingested or ingested >= start:
            raise ValueError("QUOTE_CHRONOLOGY_INVALID")


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    name: str
    source_id: str
    captured_at_utc: datetime
    payload_sha256: str
    value: Any

    def __post_init__(self) -> None:
        if not self.name or not self.source_id:
            raise ValueError("FEATURE_SOURCE_MISSING")
        utc(self.captured_at_utc, "feature")
        valid_sha(self.payload_sha256, "feature")


@dataclass(frozen=True, slots=True)
class PITBinding:
    features: tuple[FeatureSnapshot, ...]
    required_features: frozenset[str]
    freeze_at_utc: datetime

    def check(self, quote: QuoteReceipt) -> tuple[str, ...]:
        problems = []
        freeze = utc(self.freeze_at_utc, "freeze")
        seen: set[str] = set()
        if freeze > quote.observed_at_utc:
            problems.append("FEATURE_FREEZE_AFTER_ODDS_CAPTURE")
        for feat in self.features:
            if feat.name in seen:
                problems.append("DUPLICATE_FEATURE:" + feat.name)
            seen.add(feat.name)
            if feat.captured_at_utc > freeze or feat.captured_at_utc > quote.observed_at_utc:
                problems.append("FEATURE_LOOKAHEAD:" + feat.name)
            if feat.value is None or feat.value == "":
                problems.append("FEATURE_VALUE_MISSING:" + feat.name)
        for name in sorted(self.required_features - seen):
            problems.append("REQUIRED_FEATURE_MISSING:" + name)
        return tuple(sorted(set(problems)))


@dataclass(frozen=True, slots=True)
class DualSourceDecision:
    state: str                        # BLOCK or RESEARCH_ONLY; NEVER PROMOTABLE
    reasons: tuple[str, ...]
    primary_receipt_id: str | None
    secondary_receipt_id: str | None
    implied_probability_gap: str | None
    approved_stake_u: int = 0
    official_counted: int = 0

    def __post_init__(self) -> None:
        if self.state not in ("BLOCK", "RESEARCH_ONLY") or self.approved_stake_u != 0 or self.official_counted != 0:
            raise ValueError("BET_PROMOTION_FORBIDDEN")


def evaluate_dual_source(
    primary: QuoteReceipt | None,
    secondary: QuoteReceipt | None,
    decision_at_utc: datetime,
    *,
    live: bool = False,
    max_age_seconds: int | None = None,
    market_mapping_verified: bool = False,
) -> DualSourceDecision:
    """A strict structural comparator; provenance remains UNAUTHENTICATED.

    BestBook can compare offers but a BestBook display of a DK quote is not a
    second independent original sportsbook offer.
    """
    now = utc(decision_at_utc, "decision")
    age_cap = 90 if live else 300
    if max_age_seconds is not None:
        if not isinstance(max_age_seconds, int) or isinstance(max_age_seconds, bool) or max_age_seconds <= 0:
            raise ValueError("INVALID_QUOTE_AGE_POLICY")
        age_cap = min(age_cap, max_age_seconds)
    issues: list[str] = []
    if primary is None:
        issues.append("PRIMARY_MISSING")
    if secondary is None:
        issues.append("SECONDARY_MISSING")
    for name, quote in (("PRIMARY", primary), ("SECONDARY", secondary)):
        if quote is None:
            continue
        if quote.observed_at_utc > now or quote.ingested_at_utc > now:
            issues.append(name + "_OBSERVED_AFTER_DECISION")
        if now >= quote.game_start_utc:
            issues.append(name + "_EVENT_ALREADY_STARTED")
        if (now - quote.observed_at_utc).total_seconds() > age_cap:
            issues.append(name + "_STALE")
    gap: str | None = None
    if primary is not None and secondary is not None:
        if primary.market.key() != secondary.market.key():
            issues.append("MARKET_IDENTITY_MISMATCH")
        if primary.game_start_utc != secondary.game_start_utc:
            issues.append("EVENT_START_MISMATCH")
        if primary.provider == secondary.provider and primary.receipt_id == secondary.receipt_id:
            issues.append("REUSED_SOURCE_RECEIPT")
        # Two logos from a single aggregator/capture path are not two
        # independently authenticated data sources. Reject both shared
        # collection paths and shared underlying bookmakers, irrespective of
        # their receipt IDs or displayed prices.
        if primary.upstream_book.strip().casefold() == secondary.upstream_book.strip().casefold():
            issues.append("NO_INDEPENDENT_UPSTREAM_BOOK")
        if (primary.provider.strip().casefold() == secondary.provider.strip().casefold()
                or primary.upstream_provider.strip().casefold() == secondary.upstream_provider.strip().casefold()):
            issues.append("NO_INDEPENDENT_CAPTURE_PATH")
        if not market_mapping_verified:
            issues.append("CROSS_PROVIDER_MARKET_MAP_UNVERIFIED")
        gap = str(abs(implied(primary.odds_american) - implied(secondary.odds_american)))
    if issues:
        return DualSourceDecision("BLOCK", tuple(sorted(set(issues))),
                                  primary.receipt_id if primary else None,
                                  secondary.receipt_id if secondary else None, gap)
    return DualSourceDecision(
        "RESEARCH_ONLY",
        ("UPSTREAM_SOURCE_AUTHENTICATION_UNVERIFIED", "PIT_CALIBRATION_CLV_AND_V21_NOT_ALL_CERTIFIED"),
        primary.receipt_id, secondary.receipt_id, gap,
    )


@dataclass(frozen=True, slots=True)
class CLVTriple:
    open: QuoteReceipt
    taken: QuoteReceipt
    close: QuoteReceipt

    def audit(self) -> dict[str, str | bool]:
        q = (self.open, self.taken, self.close)
        reasons = []
        if len({p.market.key() for p in q}) != 1:
            reasons.append("CLV_MARKET_DEFINITION_MISMATCH")
        if len({p.game_start_utc for p in q}) != 1:
            reasons.append("CLV_EVENT_START_MISMATCH")
        if len({p.upstream_book.strip().casefold() for p in q}) != 1:
            reasons.append("CLV_BOOK_MISMATCH")
        if len({(p.provider.strip().casefold(),p.upstream_provider.strip().casefold()) for p in q}) != 1:
            reasons.append("CLV_CAPTURE_PATH_MISMATCH")
        if len({(p.provider_event_id,p.provider_market_id) for p in q}) != 1:
            reasons.append("CLV_PROVIDER_MARKET_MISMATCH")
        if not (q[0].observed_at_utc <= q[1].observed_at_utc < q[2].observed_at_utc < q[0].game_start_utc):
            reasons.append("CLV_TIME_ORDER_INVALID")
        if len({p.receipt_id for p in q}) != 3:
            reasons.append("CLV_RECEIPT_REUSED")
        # Illustrative same-line movement, not a no-vig or model-EV number.
        result: dict[str, str | bool] = {
            "valid_structural_match": not reasons,
            "reason": ",".join(reasons) if reasons else "RECEIPT_BYTES_AND_SOURCE_NOT_EXTERNALLY_AUTHENTICATED",
            "official_counted": False,
        }
        if not reasons:
            result["raw_break_even_probability_gain"] = str(implied(q[2].odds_american) - implied(q[1].odds_american))
        return result


def hash_payload(raw: bytes) -> str:
    if not isinstance(raw, bytes):
        raise TypeError("HASH_ORIGINAL_BYTES_ONLY")
    return "sha256:" + sha256(raw).hexdigest()
