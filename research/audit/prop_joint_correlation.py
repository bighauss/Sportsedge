#!/usr/bin/env python3
"""Read-only SportsEdge point-in-time player-prop joint calibration audit.

Pure Python standard library. Does not edit predictions, models, or source files.

Input: a CSV of individually frozen probabilities, real player-level settlements,
and (optionally) a CSV of already-frozen joint probabilities. See companion README.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

REQ = ("event_id", "sport", "event_start_utc", "snapshot_id", "asof_utc",
       "leg_id", "player_id", "team_id", "stat", "side", "period", "line",
       "predicted_p", "result", "result_source")
JOINT_REQ = ("event_id", "snapshot_id", "leg_id_a", "leg_id_b", "asof_utc", "joint_p")
VALID_RESULTS = {"WIN": 1, "LOSS": 0}
VALID_SOURCES = {"OFFICIAL_PLAYER_BOX_SCORE", "VERIFIED_PLAYER_BOX_SCORE",
                 "INDEPENDENT_PLAYER_STAT_RESULT", "BOOK_PLAYER_SETTLEMENT"}
UNSETTLED = {"PUSH", "VOID", "UNSETTLED", "MISSING"}
STAT_COMPONENTS = {
    "PRA": {"PTS", "REB", "AST"},
    "PTS_REB_AST": {"PTS", "REB", "AST"},
    "PR": {"PTS", "REB"}, "PA": {"PTS", "AST"}, "RA": {"REB", "AST"},
    "RUSH_REC_YDS": {"RUSH_YDS", "REC_YDS"},
}


def timestamp(raw):
    x = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if x.tzinfo is None:
        raise ValueError("timestamp must contain timezone")
    return x.astimezone(dt.timezone.utc)


def read_rows(path, required):
    # An ambiguous header or ragged row must fail the whole intake: DictReader
    # alone silently overwrites duplicate keys and stores surplus cells at None.
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, strict=True)
        try:
            original_header = next(reader)
        except StopIteration as ex:
            raise ValueError(f"{path}: EMPTY_CSV") from ex
        header = [name.strip() for name in original_header]
        canonical = [name.casefold() for name in header]
        if not header or any(not name for name in header) or len(set(canonical)) != len(canonical):
            raise ValueError(f"{path}: DUPLICATE_OR_BLANK_COLUMN")
        missing = [c for c in required if c not in header]
        if missing:
            raise ValueError(f"{path}: MISSING_REQUIRED_COLUMNS {missing}")
        rows = []
        for line, cells in enumerate(reader, 2):
            if len(cells) != len(header) or not any(cell.strip() for cell in cells):
                raise ValueError(f"{path}: RAGGED_OR_EMPTY_ROW line={line}")
            rows.append((line, dict(zip(header, cells))))
        return rows


def valid_prediction(lineno, d):
    for c in REQ:
        if not (d.get(c) or "").strip():
            raise ValueError(f"missing {c}")
    start, asof = timestamp(d["event_start_utc"]), timestamp(d["asof_utc"])
    if not asof < start:
        raise ValueError("NON_PREGAME_OR_AT_START")
    p, line = float(d["predicted_p"]), float(d["line"])
    if not math.isfinite(p) or p < 0 or p > 1:
        raise ValueError("PROBABILITY_OUT_OF_RANGE")
    if not math.isfinite(line):
        raise ValueError("INVALID_LINE")
    mode = d.get("model_mode", "").strip().upper()
    if mode not in {"PROJECTION", "INDEPENDENT_MODEL", "FROZEN_PROJECTION"}:
        raise ValueError("NON_INDEPENDENT_MODEL_MODE")
    side = d["side"].strip().upper()
    if side not in {"OVER", "UNDER", "YES", "NO"}:
        raise ValueError("UNSUPPORTED_SIDE")
    result = d["result"].strip().upper()
    if result not in VALID_RESULTS and result not in UNSETTLED:
        raise ValueError("INVALID_RESULT")
    if result in UNSETTLED:
        raise ValueError("NOT_SETTLED_PLAYER_LEVEL")
    # A provider result must be a true player-level outcome, not a team-stat proxy.
    source = d["result_source"].strip().upper()
    if source not in VALID_SOURCES:
        raise ValueError("NOT_INDEPENDENT_PLAYER_SETTLEMENT")
    return {
        **d, "asof": asof, "start": start, "p": p, "y": VALID_RESULTS[result],
        "line_num": line, "side": side, "stat": d["stat"].strip().upper(),
        "sport": d["sport"].strip().upper(), "period": d["period"].strip().upper(),
    }


def natural_key(a):
    return (a["player_id"], a["stat"], a["period"], a["side"], a["line_num"])


def classify(a, b):
    if a["player_id"] == b["player_id"]:
        if a["stat"] == b["stat"]:
            if a["side"] != b["side"] and a["line_num"] == b["line_num"]:
                return "STRUCTURAL_OPPOSITE_OUTCOMES"
            if a["side"] == b["side"] and a["line_num"] != b["line_num"]:
                return "STRUCTURAL_NESTED_LADDER"
            return "STRUCTURAL_SAME_PLAYER_STAT_THRESHOLD"
        if (a["stat"] in STAT_COMPONENTS and b["stat"] in STAT_COMPONENTS[a["stat"]]) or (b["stat"] in STAT_COMPONENTS and a["stat"] in STAT_COMPONENTS[b["stat"]]):
            return "SAME_PLAYER_COMPOSITE_OVERLAP"
        return "SAME_PLAYER_DIFFERENT_STATS"
    if a["team_id"] == b["team_id"]:
        return "SAME_TEAM_DIFFERENT_PLAYERS"
    return "OPPOSING_TEAM_PLAYERS"


def relation_name(a, b, relation):
    leg_desc = sorted((f"{a['stat']}:{a['side']}:{a['period']}",
                       f"{b['stat']}:{b['side']}:{b['period']}"))
    return a["sport"] + "|" + relation + "|" + "|".join(leg_desc)


def confidence_interval_cluster(rows, field, iterations, seed):
    if not rows:
        return None
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["event_id"]].append(r[field])
    keys = sorted(grouped)
    # Suppress nominal 95% confidence intervals below the preregistered
    # independent-event evidence floor; five-game bootstrap tails mislead.
    if len(keys) < 30:
        return None
    rng = random.Random(seed)
    draws = []
    for _ in range(iterations):
        sampled = rng.choices(keys, k=len(keys))
        vals = [v for k in sampled for v in grouped[k]]
        draws.append(statistics.fmean(vals))
    draws.sort()
    return [round(draws[int(0.025 * (len(draws) - 1))], 6),
            round(draws[int(0.975 * (len(draws) - 1))], 6)]


def round_or_none(x, n=6):
    return None if x is None else round(x, n)


def write_csv(path, rows, cols):
    with open(path, "x", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def audit(pred_csv, joint_csv, output_dir, iterations=2000, seed=20261120):
    # Never write potentially private settled player results into the repo or
    # overwrite earlier research evidence with a fresh run.
    repo_root = Path(__file__).resolve().parents[2]
    resolved_output = Path(output_dir).resolve()
    if resolved_output == repo_root or repo_root in resolved_output.parents:
        raise ValueError("PRIVATE_AUDIT_OUTPUT_REQUIRED")
    source = read_rows(pred_csv, REQ)
    output_dir.mkdir(parents=True, exist_ok=False)
    excluded, accepted = [], []
    for n, row in source:
        try:
            accepted.append(valid_prediction(n, row))
        except (ValueError, OverflowError, TypeError) as ex:
            excluded.append({"source": "predictions", "line": n, "reason": str(ex),
                             "event_id": row.get("event_id", ""), "leg_id": row.get("leg_id", "")})

    snapshots = defaultdict(list)
    for r in accepted:
        snapshots[(r["event_id"], r["snapshot_id"])].append(r)
    eligible_snapshots = {}
    for key, legs in snapshots.items():
        times = {r["asof"] for r in legs}
        starts = {r["start"] for r in legs}
        sports = {r["sport"] for r in legs}
        keys = [natural_key(r) for r in legs]
        ids = [r["leg_id"] for r in legs]
        teams_by_player = defaultdict(set)
        for r in legs:
            teams_by_player[r["player_id"]].add(r["team_id"])
        issue = ("INCONSISTENT_SNAPSHOT_CLOCK" if len(times) != 1 else
                 "INCONSISTENT_START_OR_SPORT" if len(starts) != 1 or len(sports) != 1 else
                 "DUPLICATE_LEG_ID_OR_MARKET" if len(keys) != len(set(keys)) or len(ids) != len(set(ids)) else
                 "PLAYER_CROSS_TEAM_IN_SAME_EVENT" if any(len(t) > 1 for t in teams_by_player.values()) else None)
        if issue:
            for r in legs:
                excluded.append({"source": "predictions", "line": "", "reason": issue,
                                 "event_id": r["event_id"], "leg_id": r["leg_id"]})
            continue
        eligible_snapshots[key] = legs
    # A provider event ID may not silently alias multiple start times or sports
    # across snapshots; quarantine all snapshots for that ID.
    event_identity = defaultdict(set)
    for (event_id, _snap), legs in eligible_snapshots.items():
        event_identity[event_id].add((legs[0]["sport"], legs[0]["start"]))
    for (event_id, snap), legs in list(eligible_snapshots.items()):
        if len(event_identity[event_id]) > 1:
            for r in legs:
                excluded.append({"source": "predictions", "line": "",
                                 "reason": "EVENT_ID_REUSED_FOR_DIFFERENT_GAME",
                                 "event_id": event_id, "leg_id": r["leg_id"]})
            del eligible_snapshots[(event_id, snap)]

    # Final player/team identity and settled outcomes must be invariant across
    # every saved pregame snapshot of the same event. Quarantine the complete
    # event rather than silently choosing the first conflicting record.
    event_player_teams = defaultdict(lambda: defaultdict(set))
    event_market_outcomes = defaultdict(lambda: defaultdict(set))
    for (event_id, _snap), legs in eligible_snapshots.items():
        for r in legs:
            event_player_teams[event_id][r["player_id"]].add(r["team_id"])
            event_market_outcomes[event_id][natural_key(r)].add(r["y"])
    contaminated_events = {}
    for event_id in event_player_teams:
        if any(len(teams) > 1 for teams in event_player_teams[event_id].values()):
            contaminated_events[event_id] = "PLAYER_TEAM_CHANGED_ACROSS_SNAPSHOTS"
        elif any(len(ys) > 1 for ys in event_market_outcomes[event_id].values()):
            contaminated_events[event_id] = "PLAYER_GRADE_CHANGED_ACROSS_SNAPSHOTS"
    for (event_id, snap), legs in list(eligible_snapshots.items()):
        if event_id in contaminated_events:
            for r in legs:
                excluded.append({"source": "predictions", "line": "",
                                 "reason": contaminated_events[event_id],
                                 "event_id": event_id, "leg_id": r["leg_id"]})
            del eligible_snapshots[(event_id, snap)]

    joints = {}
    if joint_csv:
        original_joint_rows = read_rows(joint_csv, JOINT_REQ)
        # Count every declared canonical pair BEFORE parsing numeric probabilities
        # or times: an invalid-first copy must not permit a valid later copy to
        # become an apparently unique frozen forecast.
        declared_pairs = Counter()
        for _line, row in original_joint_rows:
            if all((row.get(field) or "").strip() for field in
                   ("event_id", "snapshot_id", "leg_id_a", "leg_id_b")):
                key = (row["event_id"], row["snapshot_id"],
                       tuple(sorted((row["leg_id_a"], row["leg_id_b"]))))
                declared_pairs[key] += 1
        for n, r in original_joint_rows:
            try:
                for field in JOINT_REQ:
                    if not (r.get(field) or "").strip():
                        raise ValueError("MISSING_" + field)
                key = (r["event_id"], r["snapshot_id"],
                       tuple(sorted((r["leg_id_a"], r["leg_id_b"]))))
                if r["leg_id_a"] == r["leg_id_b"]:
                    raise ValueError("DUPLICATE_OR_SELF_PAIR")
                if declared_pairs[key] > 1:
                    raise ValueError("DUPLICATE_FROZEN_JOINT_PAIR_ALL_COPIES")
                p = float(r["joint_p"])
                if not math.isfinite(p) or not 0 <= p <= 1:
                    raise ValueError("JOINT_P_OUT_OF_RANGE")
                joints[key] = (p, timestamp(r["asof_utc"]))
            except (ValueError, TypeError) as ex:
                excluded.append({"source": "joint", "line": n, "reason": str(ex),
                                 "event_id": r.get("event_id", ""), "leg_id": r.get("leg_id_a", "")})

    # One earliest as-of matched copy of each unordered pair per game.
    allpairs = {}
    for (event_id, snapshot_id), legs in eligible_snapshots.items():
        for a, b in itertools.combinations(legs, 2):
            pair_natural = tuple(sorted([str(natural_key(a)), str(natural_key(b))]))
            unique_key = (event_id, pair_natural)
            relation = classify(a, b)
            pair_key = (event_id, snapshot_id, tuple(sorted([a["leg_id"], b["leg_id"]])))
            joint = joints.get(pair_key)
            joint_p = None
            if joint:
                if joint[1] != a["asof"]:
                    excluded.append({"source": "joint", "line": "", "reason": "JOINT_SNAPSHOT_TIME_MISMATCH",
                                     "event_id": event_id, "leg_id": "|".join(pair_key[2])})
                elif max(0., a["p"] + b["p"] - 1.) - 1e-10 <= joint[0] <= min(a["p"], b["p"]) + 1e-10:
                    joint_p = joint[0]
                else:
                    excluded.append({"source": "joint", "line": "", "reason": "JOINT_FRECHET_BOUNDS_VIOLATION",
                                     "event_id": event_id, "leg_id": "|".join(pair_key[2])})
            if relation.startswith("STRUCTURAL"):
                # Structural complement/nested outcomes are tracked, not learned correlations.
                field = "STRUCTURAL_LOGIC_ONLY"
            else:
                field = "EMPIRICAL_CANDIDATE"
            y = a["y"] * b["y"]
            independent_p = a["p"] * b["p"]
            record = {
                "event_id": event_id, "snapshot_id": snapshot_id, "asof_utc": a["asof"].isoformat(),
                "leg_id_a": a["leg_id"], "leg_id_b": b["leg_id"],
                "relation": relation_name(a, b, relation), "kind": field,
                "p_a": a["p"], "p_b": b["p"], "y_a": a["y"], "y_b": b["y"],
                "y_joint": y, "p_ind": independent_p, "p_joint_frozen": joint_p,
                "delta": y-independent_p,
                "brier_ind": (independent_p-y)**2,
                "brier_frozen_joint": None if joint_p is None else (joint_p-y)**2,
                "brier_advantage": None if joint_p is None else (independent_p-y)**2 - (joint_p-y)**2,
            }
            if unique_key not in allpairs or record["asof_utc"] < allpairs[unique_key]["asof_utc"]:
                allpairs[unique_key] = record

    pair_rows = sorted(allpairs.values(), key=lambda x: (x["relation"],x["event_id"],x["asof_utc"]))
    by_relation = defaultdict(list)
    for row in pair_rows:
        by_relation[row["relation"]].append(row)

    reports = []
    for relationship, pairs in sorted(by_relation.items()):
        n, events = len(pairs), len(set(x["event_id"] for x in pairs))
        joint_subset = [x for x in pairs if x["p_joint_frozen"] is not None]
        obs = statistics.fmean(x["y_joint"] for x in pairs)
        exp = statistics.fmean(x["p_ind"] for x in pairs)
        dif = obs - exp
        ci = confidence_interval_cluster(pairs, "delta", iterations, seed)
        cb = confidence_interval_cluster(joint_subset,"brier_advantage",iterations,seed+1)
        if pairs[0]["kind"] == "STRUCTURAL_LOGIC_ONLY":
            flag = "STRUCTURAL_NOT_STATISTICAL_EVIDENCE"
        elif n < 30 or events < 10:
            flag = "SMALL_SAMPLE_EXPLORATORY"
        elif n < 100 or events < 30:
            flag = "PRELIMINARY_REQUIRES_MORE_EVENTS"
        elif ci and (ci[0] > 0 or ci[1] < 0):
            flag = "EXPLORATORY_DEVIATION_REQUIRES_UNSEEN_REPLICATION"
        else:
            flag = "NO_CLEAR_DEVIATION_OR_UNDERPOWERED"
        reports.append({
            "relationship": relationship, "pair_rows": n, "independent_events": events,
            "observed_cothit_rate": round_or_none(obs),
            "expected_cothit_independence": round_or_none(exp),
            "observed_minus_independence": round_or_none(dif),
            "delta_event_cluster_bootstrap_95ci": str(ci) if ci else "N/A_LT_30_EVENTS",
            "marginal_a_pred_mean": round_or_none(statistics.fmean(x["p_a"] for x in pairs)),
            "marginal_a_hit_rate": round_or_none(statistics.fmean(x["y_a"] for x in pairs)),
            "marginal_b_pred_mean": round_or_none(statistics.fmean(x["p_b"] for x in pairs)),
            "marginal_b_hit_rate": round_or_none(statistics.fmean(x["y_b"] for x in pairs)),
            "independence_brier_all_pairs": round_or_none(statistics.fmean(x["brier_ind"] for x in pairs)),
            "frozen_joint_rows": len(joint_subset),
            "independence_brier_joint_matched_subset": round_or_none(statistics.fmean(x["brier_ind"] for x in joint_subset)) if joint_subset else None,
            "frozen_joint_brier_matched_subset": round_or_none(statistics.fmean(x["brier_frozen_joint"] for x in joint_subset)) if joint_subset else None,
            "matched_brier_improvement_ind_minus_joint": round_or_none(statistics.fmean(x["brier_advantage"] for x in joint_subset)) if joint_subset else None,
            "matched_brier_improvement_event_cluster_bootstrap_95ci": str(cb) if cb else "N/A_LT_30_JOINT_EVENTS_OR_NO_JOINT",
            "flag": flag,
        })

    fields = ["relationship", "pair_rows", "independent_events", "observed_cothit_rate",
              "expected_cothit_independence", "observed_minus_independence",
              "delta_event_cluster_bootstrap_95ci", "marginal_a_pred_mean", "marginal_a_hit_rate",
              "marginal_b_pred_mean", "marginal_b_hit_rate", "independence_brier_all_pairs",
              "frozen_joint_rows", "independence_brier_joint_matched_subset",
              "frozen_joint_brier_matched_subset", "matched_brier_improvement_ind_minus_joint",
              "matched_brier_improvement_event_cluster_bootstrap_95ci", "flag"]
    write_csv(output_dir / "relationships.csv", reports, fields)
    pf = ["event_id","snapshot_id","asof_utc","leg_id_a","leg_id_b","relation","kind","p_a","p_b",
          "y_a","y_b","y_joint","p_ind","p_joint_frozen","delta","brier_ind","brier_frozen_joint","brier_advantage"]
    write_csv(output_dir / "pair_rows.csv", pair_rows, pf)
    matched_joint_keys = {(r["event_id"], r["snapshot_id"],
                           tuple(sorted((r["leg_id_a"], r["leg_id_b"]))))
                          for r in pair_rows if r["p_joint_frozen"] is not None}
    for key in sorted(set(joints) - matched_joint_keys):
        excluded.append({"source": "joint", "line": "", "reason": "UNMATCHED_OR_INVALID_JOINT_PAIR",
                         "event_id": key[0], "leg_id": "|".join(key[2])})
    # Re-write exclusions to include unmatched frozen joint records.
    write_csv(output_dir / "excluded.csv", excluded, ["source", "line", "reason", "event_id", "leg_id"])
    summary = {"input_rows": len(source), "accepted_rows_before_snapshot_checks": len(accepted),
               "snapshot_groups_valid": len(eligible_snapshots), "pair_rows": len(pair_rows),
               "distinct_events_with_pairs": len(set(p["event_id"] for p in pair_rows)),
               "frozen_joint_matched_pair_rows": sum(p["p_joint_frozen"] is not None for p in pair_rows),
               "excluded_records_or_reasons": len(excluded), "exclusion_counts": dict(Counter(e["reason"] for e in excluded)),
               "relationship_groups": len(reports), "note": "Exploratory analysis, not an out-of-sample validated betting edge. Do not infer causation from dependence; sources not independently authenticated by this script. Event-cluster CI accounts for multiple pairs from same event, not season/team drift or multiple-testing selection."}
    with (output_dir / "coverage.json").open("x", encoding="utf-8") as report:
        report.write(json.dumps(summary, indent=2) + "\n")
    return summary


def self_test():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temp:
        d = Path(temp)
        header = list(REQ) + ["model_mode"]
        rows = []
        for i,(ya,yb) in enumerate([(1,1),(1,0),(0,1),(0,0)]):
            for who,y in [("A",ya),("B",yb)]:
                rows.append(dict(event_id=str(i),sport="NBA",event_start_utc="2026-11-20T20:00:00Z",
                                 snapshot_id="s",asof_utc="2026-11-20T18:00:00Z",leg_id=who,
                                 player_id=who,team_id="TEAM",stat="PTS" if who=="A" else "AST",side="OVER",
                                 period="FG",line="10.5",predicted_p="0.5",result="WIN" if y else "LOSS",
                                 result_source="OFFICIAL_PLAYER_BOX_SCORE", model_mode="PROJECTION"))
        with (d/"input.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=header);w.writeheader();w.writerows(rows)
        result=audit(d/"input.csv",None,d/"out",iterations=100)
        assert result["pair_rows"]==4 and result["frozen_joint_matched_pair_rows"]==0, result
        group=list(csv.DictReader((d/"out"/"relationships.csv").open()))[0]
        assert float(group["observed_cothit_rate"])==0.25
        assert float(group["expected_cothit_independence"])==0.25
        assert abs(float(group["independence_brier_all_pairs"])-0.1875)<1e-8
        print("SELF-TEST PASS: cohit 1/4, independence 0.25, Brier 0.1875")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--predictions",type=Path)
    ap.add_argument("--joint-predictions",type=Path)
    ap.add_argument("--out",type=Path,default=Path("prop_corr_audit_output"))
    ap.add_argument("--bootstrap",type=int,default=2000)
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        self_test();return
    if not args.predictions:
        ap.error("--predictions is required unless --self-test is used")
    if args.bootstrap<100:
        ap.error("--bootstrap must be >=100")
    print(json.dumps(audit(args.predictions,args.joint_predictions,args.out,args.bootstrap),indent=2))

if __name__=="__main__":
    main()