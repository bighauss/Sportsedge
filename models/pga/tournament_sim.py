"""Research-only joint PGA field simulator. No implied live data or validated weights."""
import math
import random
from collections import defaultdict

SG_KEYS = ("sg_ott", "sg_app", "sg_arg", "sg_putt")


def validate_field(players, rounds=4):
    if not isinstance(players, list) or len(players) < 2:
        raise ValueError("FIELD_REQUIRED")
    if rounds not in (1, 2, 3, 4):
        raise ValueError("ROUNDS_INVALID")
    ids = set()
    for p in players:
        if not isinstance(p, dict) or not isinstance(p.get("player_id"), str) or not p["player_id"].strip():
            raise ValueError("PLAYER_ID_REQUIRED")
        if p["player_id"] in ids:
            raise ValueError("DUPLICATE_PLAYER")
        ids.add(p["player_id"])
        if p.get("source_status") != "PREGAME_VERIFIED":
            raise ValueError("SOURCE_NOT_VERIFIED")
        for k in SG_KEYS + ("round_sd",):
            v = p.get(k)
            if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v):
                raise ValueError("MISSING_OR_INVALID_" + k.upper())
        if p["round_sd"] <= 0:
            raise ValueError("INVALID_VARIANCE")
    return ids


def simulate(players, n=10000, seed=17, rounds=4, cut_after=2, cut_size=65,
             course_par=72, common_sd=0.0):
    """One common round draw per field; each tournament ranks the same simulated scores.

    SG inputs must be independently verified pregame; SG components are summed
    with equal physical units, not claimed fitted weights. Output is UNCALIBRATED.
    Cuts use rank-based simplified rule incl ties; no withdrawals/dead heats/playoffs.
    """
    ids = validate_field(players, rounds)
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 200000:
        raise ValueError("INVALID_SIM_COUNT")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("INVALID_SEED")
    if not isinstance(course_par, (int, float)) or not math.isfinite(course_par):
        raise ValueError("INVALID_PAR")
    if not isinstance(common_sd, (int, float)) or not math.isfinite(common_sd) or common_sd < 0:
        raise ValueError("INVALID_COMMON_SD")
    if cut_after is not None and (not isinstance(cut_after, int) or cut_after < 1 or cut_after >= rounds):
        raise ValueError("INVALID_CUT_ROUND")
    if not isinstance(cut_size, int) or cut_size < 1:
        raise ValueError("INVALID_CUT_SIZE")
    rng = random.Random(seed)
    counts = {i: defaultdict(int) for i in ids}
    totals = {i: 0.0 for i in ids}
    for _ in range(n):
        score = {p["player_id"]: 0.0 for p in players}
        made_cut = set(ids)
        for r in range(rounds):
            common = rng.gauss(0, common_sd)
            for p in players:
                pid = p["player_id"]
                if pid not in made_cut:
                    continue
                sg = sum(p[k] for k in SG_KEYS)
                score[pid] += course_par - sg + common + rng.gauss(0, p["round_sd"])
            if cut_after is not None and r + 1 == cut_after:
                ordered = sorted(score, key=lambda x: (score[x], x))
                threshold = score[ordered[min(cut_size, len(ordered))-1]]
                made_cut = {pid for pid in ordered if score[pid] <= threshold}
                for pid in made_cut:
                    counts[pid]["make_cut"] += 1
        ranked = sorted(made_cut, key=lambda x: (score[x], x))
        if ranked:
            best = score[ranked[0]]
            # Tied wins are not assigned to a single golfer; no fabricated playoff.
            winners = [pid for pid in ranked if abs(score[pid] - best) < 1e-10]
            for pid in winners:
                counts[pid]["win_tie_fraction"] += 1 / len(winners)
            for pos, pid in enumerate(ranked, 1):
                for top in (5, 10, 20):
                    if pos <= top:
                        counts[pid]["top" + str(top)] += 1
                totals[pid] += score[pid]
                counts[pid]["finished"] += 1
    return {"status": "UNCALIBRATED_PAPER_0U", "simulations": n, "seed": seed,
            "limitations": ["NO_LIVE_FEED", "NO_VALIDATED_WEIGHTS", "SIMPLIFIED_CUT",
                            "NO_WITHDRAWAL_MODEL", "NO_DEAD_HEAT_SETTLEMENT"],
            "players": {pid: {key: counts[pid][key] / n for key in
                      ("win_tie_fraction", "top5", "top10", "top20", "make_cut")}
                      for pid in sorted(ids)}}
