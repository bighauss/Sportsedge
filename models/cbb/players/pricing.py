"""Runner-importable CBB player-prop pricing (PAPER/0u, NON_COUNTED).

    from players.pricing import price_board
    result = price_board(board_rows, context)

`context` is built by `build_context(...)` from public SDV player boxes and
the ESPN schedule. Each board row returns either a priced dict or a rejection
with a reason code. Pricing is push-aware (AT_LEAST N has no push; integer
OVER/UNDER lines carry push mass) and EV is never capped. DraftKings
milestones are one-sided, so no de-vig is possible: implied probabilities
include vig and are reported as such.
"""
import argparse
import csv
from collections import Counter
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from players import distributions as D
from players import features as F
from players import identity as I
from players.fit import fit
from players.model import predictive

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
MARKETS = {"PLAYER_POINTS_AT_LEAST": "POINTS", "PLAYER_REBOUNDS_AT_LEAST": "REBOUNDS",
           "PLAYER_ASSISTS_AT_LEAST": "ASSISTS", "PLAYER_THREES_AT_LEAST": "THREES",
           "PLAYER_PRA_AT_LEAST": "PRA", "PLAYER_PR_AT_LEAST": "PR", "PLAYER_PA_AT_LEAST": "PA",
           "PLAYER_RA_AT_LEAST": "RA"}
LABEL = {"label": "PAPER_0U", "status": "NON_COUNTED", "approved_stake_u": 0, "official_counted": 0,
         "stars": None, "model_validation": "RESEARCH_UNVALIDATED_FOR_STAKING"}


def is_player_row(r):
    return bool((r.get("player") or "").strip()) or str(r.get("market", "")).startswith("PLAYER_")


class Context:
    """Season box data, schedule, prior-season rates and fitted params for one slate date."""

    def __init__(self, schedule, apps, team_games, prior_rates, history_rows, box_path, *, combo="moment"):
        self.schedule = schedule
        self.apps, self.team_games, self.prior_rates = apps, team_games, prior_rates
        self.history_rows = history_rows
        self.box_path = box_path
        self.combo = combo
        self._params = {}
        self._rosters = {}

    def params_for(self, cutoff):
        key = cutoff.isoformat()
        if key not in self._params:
            lo = (cutoff - timedelta(days=365)).isoformat()
            train = [r for r in self.history_rows if lo < r["day"] <= key]
            self._params[key] = fit(train)
        return self._params[key]

    def rosters(self, home_id, away_id, cutoff):
        k = (home_id, away_id, cutoff)
        if k not in self._rosters:
            self._rosters[k] = I.load_rosters(self.box_path, (home_id, away_id), cutoff)
        return self._rosters[k]


def build_context(*, schedule_parquet, season_box, prior_season_box, prior_schedule_parquet, combo="moment"):
    import pyarrow.parquet as pq
    cols = ["game_id", "start_date", "status_type_name", "home_id", "away_id", "home_location",
            "away_location", "home_short_display_name", "away_short_display_name", "neutral_site",
            "venue_full_name"]
    sched = pq.read_table(schedule_parquet, columns=cols).to_pylist()
    for g in sched:
        g["game_id"], g["home_id"], g["away_id"] = str(g["game_id"]), str(g["home_id"]), str(g["away_id"])
    fin = {g["game_id"] for g in sched if g["status_type_name"] == "STATUS_FINAL"}
    pfin = {str(r["game_id"]) for r in pq.read_table(prior_schedule_parquet, columns=["game_id", "status_type_name"]).to_pylist()
            if r["status_type_name"] == "STATUS_FINAL"}
    apps, tg, _ = F.load_player_box(season_box, final_game_ids=fin)
    papps, ptg, _ = F.load_player_box(prior_season_box, final_game_ids=pfin)
    prior = F.prior_season_rates(papps)
    # History for the chronological fit: prior-season and current-season feature rows.
    hist_prior, _ = F.walk_season(papps, ptg, None)
    hist_cur, _ = F.walk_season(apps, tg, prior)
    return Context(sched, apps, tg, prior, hist_prior + hist_cur, season_box, combo=combo)


def _reject(r, code, **extra):
    return {"row": r, "priced": False, "reason_code": code, **LABEL, **extra}


def price_row(r, ctx, engines):
    fam = MARKETS.get(r.get("market"))
    if fam is None:
        return _reject(r, "UNSUPPORTED_PLAYER_MARKET")
    if (r.get("period") or "FG") != "FG":
        return _reject(r, "UNSUPPORTED_PERIOD")
    try:
        line = float(r["line"])
    except (TypeError, ValueError, KeyError):
        return _reject(r, "INVALID_LINE")
    if line != int(line) or line < 1:
        return _reject(r, "INVALID_MILESTONE_LINE")
    try:
        D.american_to_decimal(r.get("price_a"))
    except (TypeError, ValueError):
        return _reject(r, "MISSING_OR_INVALID_PRICE")
    try:
        tip = I.parse_utc(r["tip_utc"])
        cap = I.parse_utc(r["captured_utc"])
    except (ValueError, KeyError, TypeError):
        return _reject(r, "MISSING_OR_INVALID_TIMESTAMP")
    if cap >= tip:
        return _reject(r, "LIVE_OR_POST_TIP_CAPTURE")
    g, why = I.resolve_event(r["away"], r["home"], r["tip_utc"], ctx.schedule)
    if g is None:
        return _reject(r, why)
    day = tip.astimezone(ET).date()
    cutoff = day - timedelta(days=F.LAG_DAYS)
    pid, tid, method = I.resolve_player(r["player"], g["home_id"], g["away_id"],
                                        ctx.rosters(g["home_id"], g["away_id"], cutoff))
    if pid is None:
        return _reject(r, method, espn_game_id=g["game_id"])
    oid = g["away_id"] if tid == g["home_id"] else g["home_id"]
    eng = engines.get(cutoff)
    if eng is None:
        eng = engines[cutoff] = F.Engine(ctx.apps, ctx.team_games, ctx.prior_rates)
    feat, hold = eng.features(pid, tid, oid, day, cutoff=cutoff)
    if hold:
        return _reject(r, hold, espn_game_id=g["game_id"], athlete_id=pid)
    if feat["missed_last_team_game"]:
        return _reject(r, "AVAILABILITY_UNVERIFIED_MISSED_LAST_TEAM_GAME", espn_game_id=g["game_id"],
                       athlete_id=pid)
    params = ctx.params_for(cutoff)
    pred = predictive(feat, params, combo=ctx.combo)[fam]
    pw, pp, pl = D.settle_probs(pred["pmf"], "AT_LEAST", int(line))
    price = float(r["price_a"])
    dec = D.american_to_decimal(price)
    return {"row": r, "priced": True, "reason_code": None, **LABEL,
            "family": fam, "settlement": "AT_LEAST", "line": int(line), "side": "YES",
            "espn_game_id": g["game_id"], "dk_event_id": r.get("dk_event_id") or None,
            "dk_event_id_verified": False, "event_identity": "ESPN_SCHEDULE_EXACT_NAMES_AND_TIP",
            "athlete_id": pid, "team_id": tid, "opponent_id": oid, "player_resolution": method,
            "tip_ct": tip.astimezone(CT).strftime("%Y-%m-%d %I:%M %p CT"),
            "proj_minutes": feat["proj_minutes"], "proj_mean": pred["mean"],
            "p_win": pw, "p_push": pp, "p_lose": pl,
            "fair_american": D.fair_american(pw / (pw + pl)) if pw + pl > 0 else None,
            "dk_price": price, "implied_p_with_vig": 1.0 / dec,
            "no_vig_p": None, "no_vig_reason": "ONE_SIDED_MILESTONE_NO_OPPOSITE_QUOTE",
            "ev_per_unit_uncapped": D.expected_value(pw, pp, pl, price),
            "features_cutoff_et_date": cutoff.isoformat(), "params_train_last_day": params["train_last_day"],
            "combo_method": ctx.combo if fam in F.COMBOS else None,
            "availability": "PARTICIPATION_ASSUMED_UNVERIFIED_NO_INJURY_FEED"}


def price_board(rows, ctx):
    engines = {}
    out = [price_row(r, ctx, engines) for r in rows if is_player_row(r)]
    return {"rows": out, "priced": sum(o["priced"] for o in out),
            "rejected": sum(not o["priced"] for o in out),
            "reason_codes": dict(Counter(o["reason_code"] for o in out if not o["priced"])), **LABEL}


FIELDS = ("source_board", "away", "home", "tip_ct", "player", "market", "line", "dk_price", "captured_utc",
          "dk_event_id", "espn_game_id", "athlete_id", "team_id", "player_resolution", "priced",
          "reason_code", "proj_minutes", "proj_mean", "p_win", "p_push", "fair_american",
          "implied_p_with_vig", "ev_per_unit_uncapped", "combo_method", "label", "status",
          "approved_stake_u", "official_counted")


def flat(o, board):
    r = o["row"]
    d = {"source_board": board, **{k: r.get(k, "") for k in ("away", "home", "player", "market", "line", "captured_utc")}}
    for k in FIELDS:
        if k not in d:
            v = o.get(k, r.get(k, ""))
            d[k] = "" if v is None else (round(v, 6) if isinstance(v, float) else v)
    if not o["priced"]:
        d["dk_price"] = r.get("price_a", "")
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--board", type=Path, nargs="+", required=True)
    ap.add_argument("--schedule", type=Path, required=True)
    ap.add_argument("--season-box", type=Path, required=True)
    ap.add_argument("--prior-box", type=Path, required=True)
    ap.add_argument("--prior-schedule", type=Path, required=True)
    ap.add_argument("--combo", default="moment", choices=("moment", "independent", "copula"))
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args(argv)
    ctx = build_context(schedule_parquet=a.schedule, season_box=a.season_box, prior_season_box=a.prior_box,
                        prior_schedule_parquet=a.prior_schedule, combo=a.combo)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    summary = {**LABEL, "boards": {}, "inputs": {(str(p) if p in a.board else p.name): hashlib.sha256(p.read_bytes()).hexdigest()
                                                 for p in (*a.board, a.schedule, a.season_box, a.prior_box, a.prior_schedule)}}
    flat_rows = []
    for b in a.board:
        rows = list(csv.DictReader(b.open(newline="", encoding="utf-8")))
        res = price_board(rows, ctx)
        summary["boards"][b.name] = {"player_rows": len(res["rows"]), "priced": res["priced"],
                                     "rejected": res["rejected"], "reason_codes": res["reason_codes"]}
        flat_rows += [flat(o, b.name) for o in res["rows"]]
    keys = sorted({k for p in ctx._params.values() for k in [p["train_last_day"]]})
    summary["params"] = {k: v for k, v in ctx._params.items()}
    summary["param_train_last_days"] = keys
    with (a.out_dir / "player_props_priced.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(flat_rows)
    (a.out_dir / "player_props_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k == "boards"}, indent=1))


if __name__ == "__main__":   # PYTHONPATH=.:models/cbb python -m players.pricing ...
    main()
