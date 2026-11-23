"""Research-only venue HFA v2 challenger. Not wired to frozen CFB production.

Synthetic semantics only; source receipts and predictive validation required before promotion.
"""
import math


def venue_hfa_v2(neutral, venue, default_hfa):
    """Return capped home-field points, preserving an explicitly supplied zero.

    Missing/null values use the configured default. Reject nonfinite/invalid inputs
    rather than silently substituting an untrusted venue adjustment.
    """
    if not isinstance(neutral, bool):
        raise ValueError("neutral must be boolean")
    if neutral:
        return 0.0
    if not isinstance(venue, dict):
        raise ValueError("venue must be a mapping")
    value = venue.get("hfa")
    if value is None:
        value = default_hfa
    if isinstance(value, bool):
        raise ValueError("boolean venue HFA is invalid")
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid venue HFA") from exc
    if not math.isfinite(value):
        raise ValueError("nonfinite venue HFA")
    return max(0.0, min(4.0, value))
