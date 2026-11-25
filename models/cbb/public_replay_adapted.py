"""Opt-in public-replay ratings bridge (PAPER / 0u, NON_COUNTED).

Routes the runner's public replay through the non-destructive AdjustedFit adapter instead of the
iterative d1_filter and legacy additive ratings. The legacy functions in cbb_run_it_pipeline are
not modified; this entry point swaps public_replay_project only for the duration of one run and
restores the original, so the legacy replay stays available for controlled comparison.

Fail-closed evidence rules:
* Division I membership must be supplied explicitly (never inferred from game counts).
* Home games count as home only when the caller supplies verified-venue game ids; neutral=False is
  not treated as a verified campus venue. Unknown-site games are dropped and counted.
* Ratings and the native fit_context use the identical admitted sample.
* HCA is applied exactly once: the native residual HCA applied by NM.project. The adapter's fitted
  HCA only neutralizes ratings and is reported, never added again.
* Final availability is the runner's disclosed assumption (tip + 3h <= freeze), unchanged.
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

ENGINE = "adjusted_fit_public_adapter"
HCA_POLICY = ("NATIVE_RESIDUAL_HCA_APPLIED_ONCE_BY_NM_PROJECT; "
              "ADAPTER_FIT_HCA_NEUTRALIZES_RATINGS_ONLY_NOT_ADDED_AGAIN")
EFFICIENCY_MIN, EFFICIENCY_MAX = 60.0, 160.0


def _positive_id(value):
    return isinstance(value, str) and value.isdigit() and int(value) > 0


def admit(prior, *, d1_ids, verified_home_ids):
    """Map runner prior finals to adapter games. Returns (adapter_games, by_id, census)."""
    if not d1_ids:
        raise ValueError("D1_MEMBERSHIP_EVIDENCE_REQUIRED")
    if verified_home_ids is None:
        raise ValueError("VENUE_EVIDENCE_REQUIRED")
    census = {"dropped_bad_team_id": 0, "dropped_site_unknown": 0, "dropped_home_unverified": 0}
    games, by_id = [], {}
    for g in prior:
        if not (_positive_id(g["home_id"]) and _positive_id(g["away_id"])):
            census["dropped_bad_team_id"] += 1
            continue
        if g["neutral"] is None:
            census["dropped_site_unknown"] += 1
            continue
        if g["neutral"] is True:
            site = "NEUTRAL"
        elif g["id"] in verified_home_ids:
            site = "HOME_VERIFIED"
        else:
            census["dropped_home_unverified"] += 1
            continue
        games.append({"game_id": g["id"], "date": str(g["tip_utc"])[:10], "home": g["home_id"],
                      "away": g["away_id"], "home_points": g["home_score"],
                      "away_points": g["away_score"], "possessions": g["possessions"],
                      "site": site})
        by_id[g["id"]] = g
    return games, by_id, census


def to_legacy_body(adapter_body, season, include_zero_game_teams=False):
    """Adapter ratings JSON -> the native legacy ratings body (explicit schema, enforced ranges)."""
    out = []
    for r in json.loads(adapter_body):
        team = str(r["team"])
        if not _positive_id(team):
            raise ValueError("RATINGS_BAD_TEAM_ID:" + team)
        o, d = round(float(r["offensiveRating"]), 3), round(float(r["defensiveRating"]), 3)
        if not (EFFICIENCY_MIN <= o <= EFFICIENCY_MAX and EFFICIENCY_MIN <= d <= EFFICIENCY_MAX):
            raise ValueError("RATINGS_OUT_OF_CONTRACT:" + team)
        games = int(r["n_games"])
        if games == 0 and not include_zero_game_teams:
            continue
        out.append({"season": season, "teamId": int(team), "team": team, "offensiveRating": o,
                    "defensiveRating": d, "netRating": round(o - d, 3), "games": games})
    out.sort(key=lambda r: r["teamId"])
    return json.dumps(out, sort_keys=True).encode()


def load_prev_final(path, season):
    """Prior-season final state, chronologically valid: only the season before ``season``."""
    raw = json.loads(Path(path).read_text())
    finals = {int(k): tuple(v) for k, v in raw.items() if int(k) < season}
    if season - 1 not in finals:
        raise ValueError("PRIOR_SEASON_FINAL_MISSING")
    return finals[season - 1]


def make_public_replay_project(*, d1_ids, verified_home_ids, finals_path=None, params=None):
    """Return a function with the legacy public_replay_project signature and return shape."""
    d1 = set(d1_ids) if d1_ids else None
    verified = set(verified_home_ids) if verified_home_ids is not None else None

    def project(games, slate_ids, season, freeze_utc, cfg):
        import cbb_run_it_pipeline as PIPE
        from fullgame import public_ratings_adapter as PRA
        C, NM = PIPE.C, PIPE.NM
        freeze = PIPE.parse_z(freeze_utc)
        prior = [g for g in games.values() if g["completed"] and g["possessions"]
                 and 40 <= g["possessions"] <= 110
                 and PIPE.parse_z(g["tip_utc"]) + timedelta(hours=3) <= freeze
                 and g["home_score"] != g["away_score"]]
        n_all = len(prior)
        base = {"prior_raw": n_all, "ratings_engine": ENGINE, "early_season": False}
        try:
            adapter_games, by_id, census = admit(prior, d1_ids=d1, verified_home_ids=verified)
            cutoff = freeze.date() + timedelta(days=1)
            usable, adapter_census = PRA.filter_d1_single_pass(adapter_games, d1_set=d1, as_of=cutoff)
            prev_final = load_prev_final(finals_path, season) if finals_path else None
            hca_prior = float(prev_final[3]) if prev_final is not None and len(prev_final) > 3 else 0.0
            adapter_body, diag = PRA.fit_public_adjusted_ratings(
                usable, season=season, as_of_date=cutoff, d1_set=d1, prev_final=prev_final,
                hca_prior=hca_prior, params=params)
            body = to_legacy_body(adapter_body, season)
        except (ValueError, OSError, TypeError, KeyError, IndexError) as exc:
            return {}, {**base, "reason": str(exc), "prior_after_filter": 0}, b""
        usable_ids = {g["game_id"] for g in usable}
        admitted = [g for g in prior if g["id"] in usable_ids]
        rows = [{"game_id": g["id"], "season": season, "tipoff_utc": g["tip_utc"],
                 "final_captured_utc": PIPE.utcz(PIPE.parse_z(g["tip_utc"]) + timedelta(hours=3)),
                 "home_team_id": g["home_id"], "away_team_id": g["away_id"], "neutral": g["neutral"],
                 "home_points": g["home_score"], "away_points": g["away_score"],
                 "possessions": g["possessions"]} for g in admitted]
        ctx = NM.fit_context(body, rows, season=season, freeze_utc=NM.stamp(freeze))
        out = {}
        for gid in slate_ids:
            g = games[gid]
            try:
                if g["neutral"] is None:
                    raise NM.Pass("NEUTRAL_SITE_UNKNOWN")
                p = NM.project(ctx, g["home_id"], g["away_id"], neutral=g["neutral"], _need_sd=False)
                out[gid] = C.Projection(gid, "INDEPENDENT", p["home_points"], p["away_points"], p["margin"],
                                        p["total"], cfg["sd_margin"], cfg["sd_total"],
                                        "native_formula_public_replay_adjustedfit", "PROJECTED")
            except NM.Pass as exc:
                out[gid] = C.Projection(gid, "INDEPENDENT", None, None, None, None, None, None,
                                        "native_formula_public_replay_adjustedfit", "PASS",
                                        "GAME_NOT_PROJECTED:" + str(exc))
        leak = {"prior_finals_used": len(admitted), "prior_finals_dropped_low_count_teams": n_all - len(admitted),
                "max_prior_tip_utc": max((g["tip_utc"] for g in admitted), default=None),
                "freeze_utc": PIPE.utcz(freeze),
                "prior_rule": "tip + 3h <= freeze (final availability ASSUMED, not observed)",
                "ratings_sha256": PIPE.sha_bytes(body), "league_ortg": diag["league_ortg"],
                "ratings_engine": ENGINE, "hca_policy": HCA_POLICY,
                "adapter_fit_hca_per100": diag["hca_per100"],
                "reconstruction_home_edge_per100": diag["hca_per100"],
                "admission_census": {**census, **{k: v for k, v in adapter_census.items() if k != "usable"}},
                "prior_raw": n_all, "hca": ctx["hca"], "fitted_sd": ctx["sd"],
                "league_pace": ctx["league_pace"], "prior_census": ctx["prior_game_census"]}
        return out, leak, body

    return project


def install(project_fn):
    """Swap the runner's public_replay_project; returns the original so callers can restore it."""
    import cbb_run_it_pipeline as PIPE
    original = PIPE.public_replay_project
    PIPE.public_replay_project = project_fn
    return original


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--adapted-finals", help="fullgame finals JSON (season -> state); only seasons before --season are used")
    ap.add_argument("--adapted-d1-ids", required=True, help="JSON list of Division I team ids (explicit evidence)")
    ap.add_argument("--adapted-verified-home-ids", required=True,
                    help="JSON list of game ids with verified home-campus venue")
    args, rest = ap.parse_known_args(argv)
    d1_ids = json.loads(Path(args.adapted_d1_ids).read_text())
    verified = json.loads(Path(args.adapted_verified_home_ids).read_text())
    import cbb_run_it_pipeline as PIPE
    original = install(make_public_replay_project(d1_ids=d1_ids, verified_home_ids=verified,
                                                  finals_path=args.adapted_finals))
    try:
        return PIPE.main(rest)
    finally:
        PIPE.public_replay_project = original


if __name__ == "__main__":
    sys.exit(main() or 0)
