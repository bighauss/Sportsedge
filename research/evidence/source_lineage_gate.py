"""Research-only claimed source-independence check. NEVER authenticates offers.

Source-native IDs must be retained separately for every upstream sportsbook.
Shared canonical event/market/selection IDs are caller-asserted crosswalks,
not provider-native IDs and NOT independently attested by this function.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re


class Refused(ValueError):
    pass


SHA = re.compile(r"^[a-f0-9]{64}$")
REQUIRED = {
    "source_id", "upstream_operator_id", "aggregator_id", "book_id",
    "event_id", "market_id", "selection_id", "opposite_selection_id",
    "canonical_sport", "canonical_event_id", "canonical_market_key",
    "canonical_period", "canonical_selection_id",
    "canonical_opposite_selection_id", "crosswalk_source_sha256",
    "crosswalk_observed_utc",
    "line", "price", "opposite_price", "observed_utc", "captured_utc",
    "decision_utc", "kickoff_utc", "raw_sha256", "receipt_id", "status",
}
NATIVE_IDS = ("event_id", "market_id", "selection_id", "opposite_selection_id")
CANONICAL_IDS = (
    "canonical_sport", "canonical_event_id", "canonical_market_key",
    "canonical_period", "canonical_selection_id", "canonical_opposite_selection_id",
)


def utc(value):
    if not isinstance(value, str):
        raise Refused("INVALID_UTC")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Refused("INVALID_UTC") from exc
    if instant.tzinfo is None or instant.utcoffset().total_seconds() != 0:
        raise Refused("UTC_REQUIRED")
    return instant.astimezone(timezone.utc)


def number(value, *, price=False):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise Refused("INVALID_NUMBER") from exc
    if not result.is_finite():
        raise Refused("INVALID_NUMBER")
    if price and (result != result.to_integral_value() or
                  not 100 <= abs(result) <= 100000):
        raise Refused("INVALID_NUMBER")
    return format(result.normalize(), "f")


def _identity(value):
    """Basic alias handling is NOT publisher identity authentication."""
    clean = " ".join(value.strip().casefold().replace("-", " ").split())
    return {"dk": "draftkings", "draft kings": "draftkings",
            "fd": "fanduel", "fan duel": "fanduel"}.get(clean, clean)


def inspect_pair(rows, max_age_seconds=300):
    """Return PAPER-only source-claims result; never a certified Gate A pass."""
    if type(max_age_seconds) is not int or not 0 < max_age_seconds <= 300:
        raise Refused("INVALID_AGE_POLICY")
    if not isinstance(rows, list) or len(rows) != 2:
        raise Refused("TWO_RECEIPTS_REQUIRED")

    canonical = []
    for q in rows:
        if (not isinstance(q, dict) or set(q) != REQUIRED or
                any(not isinstance(value, str) or not value.strip()
                    for value in q.values())):
            raise Refused("RECEIPT_SCHEMA_INVALID")
        if q["status"] != "OPEN":
            raise Refused("MARKET_NOT_OPEN")
        for key in ("raw_sha256", "crosswalk_source_sha256"):
            if not SHA.fullmatch(q[key]):
                raise Refused("INVALID_SHA256:" + key)

        number(q["price"], price=True)
        number(q["opposite_price"], price=True)
        line = number(q["line"])
        if (q["selection_id"] == q["opposite_selection_id"] or
                q["canonical_selection_id"] == q["canonical_opposite_selection_id"]):
            raise Refused("INVALID_OPPOSITE")

        observed, captured, decision, kickoff = (
            utc(q[k]) for k in
            ("observed_utc", "captured_utc", "decision_utc", "kickoff_utc")
        )
        crosswalk_seen = utc(q["crosswalk_observed_utc"])
        if not observed <= captured <= decision < kickoff:
            raise Refused("LOOKAHEAD_OR_LIVE")
        if crosswalk_seen > decision:
            raise Refused("FUTURE_CROSSWALK")
        if (decision - observed).total_seconds() > max_age_seconds:
            raise Refused("STALE_QUOTE")
        canonical.append((
            *(q[key].strip() for key in CANONICAL_IDS),
            line, kickoff, q["crosswalk_source_sha256"], crosswalk_seen,
        ))

    if canonical[0] != canonical[1]:
        raise Refused("MARKET_IDENTITY_MISMATCH")

    # Different operator declarations are not proof of independent origin.
    for key in ("source_id", "upstream_operator_id", "aggregator_id",
                "book_id", "receipt_id"):
        if _identity(rows[0][key]) == _identity(rows[1][key]):
            raise Refused("NOT_INDEPENDENT_" + key.upper())

    if rows[0]["raw_sha256"] == rows[1]["raw_sha256"]:
        raise Refused("SHARED_RAW_SOURCE_BYTES")
    if all(rows[0][key] == rows[1][key] for key in NATIVE_IDS):
        raise Refused("SUSPICIOUS_SHARED_PROVIDER_NATIVE_IDS")

    return {
        "status": "PAPER_SOURCE_CLAIMS_ONLY",
        "authenticated": False,
        "crosswalk_attested": False,
        "approved_stake_u": 0,
        "warning": ("Canonical mapping and upstream-operator declarations are "
                    "caller claims, not independent provider authentication"),
    }
