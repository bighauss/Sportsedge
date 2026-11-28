"""Adapter: freeze CBB independent projections before odds are read.

Call this after the native projection is available and before board quotes are joined.
The receipt is deterministic and market-blind. Attach it to the run document so that
independent forecasts are recorded and auditable prior to any DraftKings comparison.
"""
from __future__ import annotations
import hashlib, json, math
from typing import Any, Mapping

import cbb_independent_pricing as IP


def _digest(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def freeze_independent_receipt(proj: Mapping[str, Any], cfg: Mapping[str, Any] | None = None) -> dict:
    """Build and hash an independent projection receipt. No quote arguments accepted."""
    cfg = cfg or IP.independent_config()
    if cfg.get("blend_weight_model") != 1.0:
        raise ValueError("INDEPENDENT_RECEIPT_REQUIRES_WEIGHT_ONE")
    body = {
        "schema": "sportsedge-cbb-independent-projection-v1",
        "blend_weight_model": 1.0,
        "margin": proj.get("margin"),
        "total": proj.get("total"),
        "home_points": proj.get("home_points") or proj.get("home_pts"),
        "away_points": proj.get("away_points") or proj.get("away_pts"),
        "possessions": proj.get("poss") or proj.get("possessions"),
        "sd_margin": cfg["sd_margin"],
        "sd_total": cfg["sd_total"],
        "label": "PURE_INDEPENDENT_BEFORE_ODDS",
        "release_ready": False,
        "approved_stake_u": 0,
        "official_counted": 0,
    }
    for k, v in list(body.items()):
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("NONFINITE_PROJECTION_FIELD")
    body["sha256"] = _digest({k: v for k, v in body.items() if k != "sha256"})
    return body


def attach_independent_receipts(projections: list[Mapping[str, Any]], cfg: Mapping[str, Any] | None = None) -> list[dict]:
    """Freeze a receipt for every projected game. Call before ingesting odds."""
    return [freeze_independent_receipt(p, cfg) for p in projections]
