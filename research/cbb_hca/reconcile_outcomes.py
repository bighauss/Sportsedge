"""Chronological forecast-final reconciliation. SHA binding is not source attestation."""
from datetime import datetime
from collections import Counter

def utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("UTC_Z_REQUIRED")
    return datetime.fromisoformat(value[:-1] + "+00:00")

def sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

def reconcile(forecasts, finals):
    forecasts, finals = list(forecasts), list(finals)
    f_ids = Counter(x.get("game", {}).get("game_id") if isinstance(x, dict) else None for x in forecasts)
    y_ids = Counter(x.get("game_id") if isinstance(x, dict) else None for x in finals)
    eligible, holds, finals_by = [], [], {}
    for i, y in enumerate(finals):
        gid = y.get("game_id") if isinstance(y, dict) else None
        if not isinstance(gid, str) or y_ids[gid] != 1:
            holds.append(dict(kind="final", index=i, game_id=gid, reason="DUPLICATE_OR_INVALID_FINAL"))
        else:
            finals_by[gid] = y
    for i, f in enumerate(forecasts):
        gid = f.get("game", {}).get("game_id") if isinstance(f, dict) else None
        try:
            if not isinstance(f, dict) or not isinstance(gid, str) or f_ids[gid] != 1:
                raise ValueError("DUPLICATE_OR_INVALID_FORECAST")
            y = finals_by.get(gid)
            if y is None:
                raise ValueError("FINAL_MISSING")
            receipts = f.get("source_receipts")
            if not sha(f.get("parent_card_sha256")) or not isinstance(receipts, dict) or set(receipts) < {"ratings", "prior_games"} or any(not sha(v) for v in receipts.values()):
                raise ValueError("SOURCE_OR_PARENT_BINDING_MISSING")
            if not sha(y.get("source_sha256")):
                raise ValueError("FINAL_SOURCE_SHA_MISSING")
            g = f["game"]
            freeze, tip, built, observed = utc(f["freeze_utc"]), utc(g["tipoff_utc"]), utc(f["built_utc"]), utc(y["final_observed_utc"])
            if not freeze <= built < tip < observed:
                raise ValueError("INVALID_CHRONOLOGY")
            if y.get("settlement") != "FG_INCL_OT":
                raise ValueError("SETTLEMENT_UNSUPPORTED")
            if any(g.get(k) != y.get(k) for k in ("season", "home_team_id", "away_team_id")):
                raise ValueError("IDENTITY_MISMATCH")
            hp, ap, poss = y["home_points"], y["away_points"], y["possessions"]
            if type(hp) is not int or type(ap) is not int or hp == ap or not 0 <= hp <= 250 or not 0 <= ap <= 250:
                raise ValueError("FINAL_SCORE_INVALID_OR_TIED")
            if type(poss) not in (int, float) or not poss > 0:
                raise ValueError("POSSESSIONS_INVALID")
            forecasts_out = f["forecasts"]
            if set(forecasts_out) != {"additive_product", "additive_arithmetic", "multiplicative_product", "multiplicative_arithmetic"}:
                raise ValueError("FOUR_FORECASTS_REQUIRED")
            eligible.append(dict(event_id=gid, freeze_utc=f["freeze_utc"], tipoff_utc=g["tipoff_utc"], final_observed_utc=y["final_observed_utc"], parent_card_sha256=f["parent_card_sha256"], forecast_receipts=dict(receipts), final_sha256=y["source_sha256"], actual=dict(home_points=hp, away_points=ap, possessions=float(poss)), forecasts=forecasts_out, projected_margin=forecasts_out["additive_product"]["margin"], actual_margin=hp - ap, settlement="FG_INCL_OT"))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            holds.append(dict(kind="pair", index=i, game_id=gid, reason=str(exc)))
    return dict(status="CHRONOLOGY_CHECKED_SOURCE_AUTHENTICITY_NOT_ESTABLISHED", eligible=eligible, holds=holds, official_counted=0, approved_stake_u=0)
