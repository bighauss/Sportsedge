"""Research-only venue HFA v2 challenger. Not wired to frozen CFB production.

Synthetic semantics only; source receipts and predictive validation required before promotion.
"""
import math


def _validated_hfa(value, label):
    """Require a finite native number within the documented venue HFA domain."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a native numeric value")
    try:
        numeric = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} cannot be represented as finite float") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    if not 0.0 <= numeric <= 4.0:
        raise ValueError(f"{label} outside [0, 4]")
    return numeric


def venue_hfa_v2(neutral, venue, default_hfa):
    """Return home-field points, preserving zero; fail closed on malformed inputs.

    Validate the default and venue even for neutral games so invalid source
    configuration cannot be silently hidden by a neutral-site override.
    """
    if not isinstance(neutral, bool):
        raise ValueError("neutral must be boolean")
    default = _validated_hfa(default_hfa, "default_hfa")
    if not isinstance(venue, dict):
        raise ValueError("venue must be a mapping")
    raw = venue.get("hfa")
    hfa = default if raw is None else _validated_hfa(raw, "venue hfa")
    return 0.0 if neutral else hfa
