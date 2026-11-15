"""Authorized offline payload ingestion. No live BestBook or DK endpoint is assumed.

BestBook.app is a valuable comparison UI, but this module does not claim it
provides a public programmable API or independently authenticated book prices.
Use only an authorized raw export / a documented partnership adapter.
"""
from __future__ import annotations

from datetime import datetime
import json

from .evidence import MarketKey, QuoteReceipt, hash_payload


def unique_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_RAW_JSON_KEY:" + key)
        out[key] = value
    return out


def capture_authorized_export(
    raw_payload_bytes: bytes,
    *,
    ingested_at_utc: datetime,
    provider: str,
    upstream_book: str,
    upstream_provider: str,
    receipt_id: str,
    mapping_version: str,
) -> QuoteReceipt:
    """Parse a *known, approved export schema*. Never infer authenticity or URLs.

    A provider token/user session is deliberately not part of the receipt or log.
    The full raw bytes must be retained privately by the operator.
    """
    if not mapping_version or mapping_version == "UNVERSIONED":
        raise ValueError("VERSIONED_PROVIDER_MAPPING_REQUIRED")
    if not isinstance(raw_payload_bytes, bytes) or not raw_payload_bytes:
        raise ValueError("RAW_PROVIDER_RESPONSE_BYTES_MISSING")
    try:
        q = json.loads(raw_payload_bytes.decode("utf-8"), object_pairs_hook=unique_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("INVALID_AUTHORIZED_EXPORT_JSON") from exc
    if not isinstance(q, dict):
        raise ValueError("EXPORT_NOT_JSON_OBJECT")
    required = {
        "sport", "event_id", "market_kind", "period", "side", "line",
        "provider_event_id", "provider_market_id", "quote_id",
        "odds_american", "observed_at_utc", "game_start_utc",
    }
    if not required.issubset(q):
        raise ValueError("EXPORT_REQUIRED_KEYS_MISSING")
    if not provider or not upstream_provider or not upstream_book or not receipt_id:
        raise ValueError("SOURCE_IDENTIFIERS_MISSING")
    try:
        market = MarketKey(
            sport=q["sport"], event_id=q["event_id"],
            kind=q["market_kind"], period=q["period"], side=q["side"],
            line=q["line"], team_id=q.get("team_id", ""),
            player_id=q.get("player_id", ""), stat=q.get("stat", ""),
            settlement=q.get("settlement", "REGULATION"),
        )
        obs = datetime.fromisoformat(q["observed_at_utc"].replace("Z", "+00:00"))
        start = datetime.fromisoformat(q["game_start_utc"].replace("Z", "+00:00"))
        return QuoteReceipt(
            market=market, quote_id=q["quote_id"], provider=provider,
            upstream_book=upstream_book, upstream_provider=upstream_provider,
            provider_event_id=q["provider_event_id"],
            provider_market_id=q["provider_market_id"],
            odds_american=q["odds_american"], observed_at_utc=obs,
            ingested_at_utc=ingested_at_utc, game_start_utc=start,
            payload_sha256=hash_payload(raw_payload_bytes), receipt_id=receipt_id,
            source_auth_method_claim="OFFLINE_EXPORT_UNVERIFIED",
        )
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError("EXPORT_NORMALIZATION_BLOCKED:" + str(exc)) from exc


def bestbook_export_available(has_documented_permission: bool) -> bool:
    """No guessed API URLs. Authorization alone does not prove an export exists."""
    return False  # Until real API/export docs and sample provider response are validated.
