"""Independent four-cell scoring research; unchanged native baseline, PAPER / 0u."""
import hashlib
import json
import math
from datetime import datetime, timezone
from .evidence_io import atomic_publish

VARIANTS = ("additive_product", "additive_arithmetic", "multiplicative_product", "multiplicative_arithmetic")

def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

def compare(ctx, home, away, *, neutral):
    import cbbd_native_score_model as native
    if type(neutral) is not bool:
        raise native.Pass("EXPLICIT_VENUE_REQUIRED")
    baseline = native.project(ctx, home, away, neutral=neutral, _need_sd=False)
    r, league = ctx["ratings"], ctx["league_mean_ortg"]
    efficiencies = (native._effs(ctx, home, away), (r[home]["off"] * r[away]["def"] / league, r[away]["off"] * r[home]["def"] / league))
    paces = (baseline["possessions"], (ctx["team_pace"][home][0] + ctx["team_pace"][away][0]) / 2)
    rows = {}
    for i, (eh, ea) in enumerate(efficiencies):
        for j, poss in enumerate(paces):
            h = eh * poss / 100 + baseline["hca_applied"] / 2
            a = ea * poss / 100 - baseline["hca_applied"] / 2
            if any(not math.isfinite(x) or x < 0 for x in (h, a, poss)):
                raise native.Pass("INVALID_CHALLENGER_OUTPUT")
            rows[VARIANTS[2*i+j]] = dict(home_points=h, away_points=a, margin=h-a, total=h+a, possessions=poss, hca_applied=baseline["hca_applied"])
    for k in ("home_points", "away_points", "margin", "total", "possessions"):
        if not math.isclose(rows[VARIANTS[0]][k], baseline[k], rel_tol=1e-12, abs_tol=1e-10):
            raise native.Pass("BASELINE_PARITY_FAILED")
    return rows

def freeze(ctx, game, path, *, parent_card_sha256, source_receipts, clock=None):
    """Private atomic record bound to parent card and source receipt digests."""
    import cbbd_native_score_model as native
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    tip = native.utc(game["tipoff_utc"], "tipoff_utc")
    start = native.utc(ctx["freeze_utc"], "freeze_utc")
    if now.tzinfo is None or not start <= now < tip:
        raise native.Pass("NOT_PRETIP_OR_CONTEXT_FROM_FUTURE")
    if not _sha(parent_card_sha256) or not isinstance(source_receipts, dict) or not {"ratings", "prior_games"}.issubset(source_receipts) or any(not _sha(v) for v in source_receipts.values()):
        raise native.Pass("SOURCE_OR_PARENT_BINDING_REQUIRED")
    gid = native.canonical_id(game["game_id"])
    h, a = game["home_team_id"], game["away_team_id"]
    if gid != game["game_id"] or h == a or any(native.canonical_id(x) != x for x in (h, a)):
        raise native.Pass("INVALID_EVENT_IDENTITIES")
    if type(game["season"]) is not int or game["season"] != ctx["season"] or native.season_of(tip) != ctx["season"]:
        raise native.Pass("SEASON_MISMATCH")
    out = dict(schema="CBB_FACTORIAL_RESEARCH_V1", game=dict(game), freeze_utc=ctx["freeze_utc"], built_utc=native.stamp(now), forecasts=compare(ctx, h, a, neutral=game["neutral"]), parent_card_sha256=parent_card_sha256, source_receipts=dict(sorted(source_receipts.items())), binding="SHA256_BINDING_NOT_PROVIDER_ATTESTATION", native_sha256=native.MODEL_CODE_SHA256, adapter_sha256=hashlib.sha256(open(__file__, "rb").read()).hexdigest(), context_sha256=hashlib.sha256(json.dumps(ctx, sort_keys=True, allow_nan=False).encode()).hexdigest(), source_authenticity="NOT_ESTABLISHED", official_counted=0, approved_stake_u=0)
    raw = (json.dumps(out, sort_keys=True, allow_nan=False) + "\n").encode()
    def before_publish():
        current = (clock or (lambda: datetime.now(timezone.utc)))()
        if current.tzinfo is None or not start <= current < tip:
            raise native.Pass("TIP_PASSED_DURING_BUILD_OR_CLOCK_REGRESSED")
    atomic_publish(path, raw, before_publish=before_publish)
    return out
