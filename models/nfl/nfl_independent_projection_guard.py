"""NFL independent projection freeze guard (PAPER / 0u / NON_COUNTED).

Call after native projection and before any sportsbook quote is examined.
The receipt contains only model-derived fields and is SHA-256 hashed.
No blend weight, no market no-vig, no quote arguments.
"""
from __future__ import annotations
import hashlib, json, math
from typing import Any, Mapping


def _digest(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def freeze_nfl_projection(proj: Mapping[str, Any]) -> dict:
    """Freeze a market-blind NFL projection receipt.

    Expected keys (optional): margin, total, home_points, away_points, plays, pass_rate.
    Rejects non-finite numeric fields.
    """
    body = {
        "schema": "sportsedge-nfl-independent-projection-v1",
        "margin": proj.get("margin"),
        "total": proj.get("total"),
        "home_points": proj.get("home_points") or proj.get("home_pts"),
        "away_points": proj.get("away_points") or proj.get("away_pts"),
        "plays": proj.get("plays"),
        "pass_rate": proj.get("pass_rate"),
        "label": "PURE_INDEPENDENT_BEFORE_ODDS",
        "release_ready": False,
        "approved_stake_u": 0,
        "official_counted": 0,
    }
    for k, v in body.items():
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("NONFINITE_PROJECTION_FIELD")
    body["sha256"] = _digest({k: v for k, v in body.items() if k != "sha256"})
    return body


def attach_nfl_independent_receipts(projections: list[Mapping[str, Any]]) -> list[dict]:
    return [freeze_nfl_projection(p) for p in projections]
