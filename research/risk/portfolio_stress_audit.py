#!/usr/bin/env python3
"""SportsEdge research-only portfolio correlation and stress diagnostics.

This module never modifies bets, original predictions or model weights.
A passing schema check does NOT authenticate sportsbook source timestamps,
original odds, qualifying universes or independent settlement sources.

Input: CSV with one claimed original qualifying selection per row. The original
complete selection universe must be independently attested elsewhere.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import math
import random
import re
import statistics
from pathlib import Path
from zoneinfo import ZoneInfo

SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
RESULTS = frozenset(("WIN", "LOSS", "PUSH", "VOID", "PENDING"))
FIELDS = (
    "bet_id", "event_id", "sport", "market_key", "market", "direction",
    "model_version", "rules_version", "model_sha256", "rules_sha256",
    "universe_sha256", "universe_complete_claim", "quote_sha256",
    "rules_effective_utc", "model_asof_utc", "quote_observed_utc",
    "quote_captured_utc", "selected_utc", "kickoff_utc", "book",
    "price_american", "stake_units", "stake_basis", "evaluation_split", "result",
    "settled_utc", "settlement_source_a", "settlement_source_b",
)
STAKE_BASES = frozenset(("PAPER_FLAT", "EXECUTED_CLAIM"))
UTC = dt.timezone.utc
CT = ZoneInfo("America/Chicago")


def instant(value):
    if not isinstance(value, str) or not value:
        raise ValueError("MISSING_TIMESTAMP")
    try:
        x = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if x.tzinfo is None or x.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return x.astimezone(UTC)


def finite(value, name, *, low=None, high=None):
    try:
        x = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("INVALID_" + name) from exc
    if not math.isfinite(x) or (low is not None and x < low) or (high is not None and x > high):
        raise ValueError("INVALID_" + name)
    return x


def american_payout(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"[+-]?\d+", value):
            raise ValueError
        odds = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_AMERICAN_PRICE") from exc
    if -100 < odds < 100 or abs(odds) > 100000:
        raise ValueError("INVALID_AMERICAN_PRICE")
    return odds / 100 if odds > 0 else 100 / -odds


def valid_row(row, *, max_quote_age_minutes=120):
    for key in FIELDS:
        if key in ("settled_utc", "settlement_source_a", "settlement_source_b") and row.get("result") == "PENDING":
            continue
        if not str(row.get(key) or "").strip():
            raise ValueError("MISSING_" + key.upper())
    if row["result"] not in RESULTS:
        raise ValueError("UNKNOWN_RESULT")
    if row["universe_complete_claim"] != "TRUE":
        raise ValueError("CANDIDATE_UNIVERSE_NOT_CLAIMED_COMPLETE")
    for key in ("model_sha256", "rules_sha256", "universe_sha256", "quote_sha256"):
        if not SHA256.fullmatch(row[key]):
            raise ValueError("INVALID_" + key.upper())
    if row["stake_basis"] not in STAKE_BASES:
        raise ValueError("UNKNOWN_STAKE_BASIS")
    if row["evaluation_split"] != "OOS":
        raise ValueError("NOT_OUT_OF_SAMPLE")
    stake = finite(row["stake_units"], "STAKE_UNITS", low=1e-12)
    payout = american_payout(row["price_american"])
    commission = finite(row.get("commission_rate") or "0", "COMMISSION_RATE", low=0, high=1)
    rule = instant(row["rules_effective_utc"])
    model = instant(row["model_asof_utc"])
    observed = instant(row["quote_observed_utc"])
    captured = instant(row["quote_captured_utc"])
    selected = instant(row["selected_utc"])
    kickoff = instant(row["kickoff_utc"])
    if rule > selected or model > selected:
        raise ValueError("RETROACTIVE_RULE_OR_MODEL")
    if not observed <= captured <= selected < kickoff:
        raise ValueError("LOOKAHEAD_QUOTE_OR_SELECTION")
    if (selected - observed).total_seconds() > max_quote_age_minutes * 60:
        raise ValueError("STALE_QUOTE")
    result = row["result"]
    settled = None
    if result != "PENDING":
        settled = instant(row["settled_utc"])
        if settled <= kickoff:
            raise ValueError("FINAL_BEFORE_KICKOFF")
        if row["settlement_source_a"].strip().casefold() == row["settlement_source_b"].strip().casefold():
            raise ValueError("SAME_CLAIMED_SETTLEMENT_SOURCE")
    # Raw taken-price arithmetic; NO source/execution authentication implied.
    net = (stake * payout * (1 - commission) if result == "WIN"
           else -stake if result == "LOSS"
           else 0.0 if result in ("PUSH", "VOID") else None)
    risk = 0.0 if result == "VOID" else stake
    return {
        "bet_id": row["bet_id"], "event_id": row["event_id"], "sport": row["sport"],
        "market": row["market"], "market_key": row["market_key"],
        "direction": row["direction"], "book": row["book"],
        "model_version": row["model_version"], "rules_version": row["rules_version"],
        "player_id": row.get("player_id") or "", "quarterback_id": row.get("quarterback_id") or "",
        "theme_id": row.get("theme_id") or "", "stake_basis": row["stake_basis"],
        "selected_at": selected.isoformat(),
        "selected_day_ct": selected.astimezone(CT).date().isoformat(),
        "selected_month_ct": selected.astimezone(CT).strftime("%Y-%m"),
        "settled_at": settled.isoformat() if settled else None,
        "result": result, "payout": payout, "commission": commission,
        "stake": stake, "risk": risk, "net": net,
    }


def status_summary(rows):
    resolved = [x for x in rows if x["net"] is not None]
    denom = sum(x["risk"] for x in resolved)
    return {
        "n": len(rows), "settled": len(resolved),
        "wins": sum(x["result"] == "WIN" for x in resolved),
        "losses": sum(x["result"] == "LOSS" for x in resolved),
        "pushes": sum(x["result"] == "PUSH" for x in resolved),
        "voids": sum(x["result"] == "VOID" for x in resolved),
        "pending": sum(x["result"] == "PENDING" for x in rows),
        "risked_units": round(denom, 8),
        "net_units": round(sum(x["net"] for x in resolved), 8),
        "roi": (sum(x["net"] for x in resolved) / denom) if denom else None,
    }


def peak_to_trough(rows):
    """Settled-order hypothetical drawdown; overlapping stakes not bankrolled."""
    series = sorted((x for x in rows if x["net"] is not None),
                    key=lambda x: (x["settled_at"], x["event_id"], x["bet_id"]))
    cumulative = peak = worst = 0.0
    losing = max_losing = 0
    for x in series:
        cumulative += x["net"]
        peak = max(peak, cumulative)
        worst = max(worst, peak - cumulative)
        if x["result"] == "LOSS":
            losing += 1
            max_losing = max(max_losing, losing)
        elif x["result"] == "WIN":
            losing = 0
    return {"hypothetical_max_drawdown_units": round(worst, 8),
            "longest_consecutive_loss_rows": max_losing,
            "warning": "Result order is settled-time with deterministic ties; not an actual bankroll cash-flow path."}


def event_theme_groups(rows, *, connect_themes=False):
    """Game blocks; optionally join games linked by the SAME explicit risk theme.

    Does not infer correlation from vague market names. Larger connected blocks
    are deliberately conservative and may leave too few blocks for inference.
    """
    by_event = collections.defaultdict(list)
    for row in rows:
        if row["net"] is not None and row["risk"] > 0:
            # Provider event identifiers may overlap between sports. Both the
            # sport and event ID must be part of the statistical game block.
            by_event[(row["sport"], row["event_id"])].append(row)
    events = sorted(by_event)
    if not connect_themes:
        return [by_event[k] for k in events]
    parent = {event: event for event in events}
    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def join(a, b):
        pa, pb = root(a), root(b)
        if pa != pb:
            parent[max(pa, pb)] = min(pa, pb)
    theme_anchor = {}
    for event in events:
        for row in by_event[event]:
            theme = row.get("theme_id")
            if not theme:
                continue
            if theme in theme_anchor:
                join(event, theme_anchor[theme])
            else:
                theme_anchor[theme] = event
    components = collections.defaultdict(list)
    for event in events:
        components[root(event)].extend(by_event[event])
    return [components[k] for k in sorted(components)]


def block_bootstrap(rows, *, iterations=2000, seed=42, connect_themes=False):
    """Resamples game/theme blocks, not individual props. No null p-value."""
    event_count = len(set((row["sport"], row["event_id"]) for row in rows
                          if row["net"] is not None and row["risk"] > 0))
    groups = event_theme_groups(rows, connect_themes=connect_themes)
    block_label = "event_or_connected_theme" if connect_themes else "event"
    if len(groups) < 30:
        return {"status": "INSUFFICIENT_30_INDEPENDENT_BLOCKS", "events": event_count,
                "blocks": len(groups), "block_method": block_label,
                "roi_ci95": None, "drawdown_ci95": None}
    if iterations < 100:
        raise ValueError("BOOTSTRAP_ITERATIONS_TOO_SMALL")
    rng = random.Random(seed)
    rois, drawdowns = [], []
    for _ in range(iterations):
        simulated = [groups[rng.randrange(len(groups))] for _ in groups]
        risk = sum(x["risk"] for group in simulated for x in group)
        net = sum(x["net"] for group in simulated for x in group)
        if risk <= 0:
            raise ValueError("BOOTSTRAP_NO_RISK")
        rois.append(net / risk)
        current = high = dd = 0.0
        for group in simulated:
            current += sum(x["net"] for x in group)
            high = max(high, current)
            dd = max(dd, high - current)
        drawdowns.append(dd)
    rois.sort(); drawdowns.sort()
    def interval(values):
        return [values[int(.025 * (len(values) - 1))], values[int(.975 * (len(values) - 1))]]
    return {
        "status": "PAPER_GAME_CLUSTER_BOOTSTRAP", "events": event_count,
        "blocks": len(groups), "block_method": block_label,
        "iterations": iterations, "roi_ci95": interval(rois),
        "drawdown_ci95": interval(drawdowns),
        "resample_fraction_roi_nonpositive": sum(x <= 0 for x in rois) / iterations,
        "warning": "This fraction is NOT a null-hypothesis p-value; exchangeability and source authenticity remain unverified.",
    }


def stress_haircut(rows, haircut):
    """Reduction in net winning payout, NOT a claim of executable odds slippage."""
    finite(haircut, "HAIRCUT", low=0, high=1)
    eligible = [x for x in rows if x["net"] is not None]
    denom = sum(x["risk"] for x in eligible)
    net = sum(x["stake"] * x["payout"] * (1-x["commission"]) * (1-haircut)
              if x["result"] == "WIN" else x["net"] for x in eligible)
    return {"winning_payout_haircut": haircut, "net_units": round(net, 8),
            "roi": net / denom if denom else None}


def overlap(rows):
    """Descriptive exposure only, NOT an empirical pairwise correlation estimate."""
    by_event = collections.defaultdict(list)
    by_theme = collections.defaultdict(list)
    by_day = collections.defaultdict(list)
    for x in rows:
        by_event[(x["sport"], x["event_id"])].append(x)
        by_day[x["selected_day_ct"]].append(x)
        if x["theme_id"]:
            by_theme[x["theme_id"]].append(x)
    exposure = {sport + ":" + event: round(sum(x["stake"] for x in v), 8)
                for (sport, event), v in sorted(by_event.items())}
    themes = {theme: {"count": len(v), "total_staked_units": round(sum(x["stake"] for x in v), 8),
                      "events": len(set((x["sport"], x["event_id"]) for x in v))}
              for theme, v in sorted(by_theme.items()) if len(v) > 1}
    day = {d: round(sum(x["stake"] for x in v), 8) for d, v in sorted(by_day.items())}
    total = sum(exposure.values())
    effective_concentration = total * total / sum(v*v for v in exposure.values()) if total else None
    return {"distinct_events": len(by_event),
            "max_same_event_selections": max((len(x) for x in by_event.values()), default=0),
            "event_stake_units": exposure, "theme_overlap": themes,
            "decision_day_stakes_ct": day,
            "concentration_equivalent_events": effective_concentration,
            "warning": "Concentration-equivalent events is NOT a statistical effective sample size or a measured covariance."}


def group_results(rows, field):
    groups = collections.defaultdict(list)
    for x in rows:
        groups[x[field] or "UNKNOWN"].append(x)
    return {k: {"performance": status_summary(v), "event_count": len(set((x["sport"], x["event_id"]) for x in v)),
                "insufficient_30_events": len(set((x["sport"], x["event_id"]) for x in v)) < 30}
            for k, v in sorted(groups.items())}


def audit(input_rows, *, iterations=2000):
    input_rows = list(input_rows)
    id_counts = collections.Counter(str(r.get("bet_id") or "").strip() for r in input_rows)
    # Canonical market_key must include exact event/period/line/selection/player.
    identity_counts = collections.Counter((r.get("event_id"),r.get("market_key"),r.get("direction")) for r in input_rows)
    accepted, blocked = [], []
    for number, r in enumerate(input_rows, 2):
        flags = []
        if id_counts[str(r.get("bet_id") or "").strip()] > 1:
            flags.append("DUPLICATE_BET_ID_ALL_COPIES")
        if identity_counts[(r.get("event_id"),r.get("market_key"),r.get("direction"))] > 1:
            flags.append("DUPLICATE_CANONICAL_SELECTION_ALL_COPIES")
        try:
            parsed = valid_row(r)
        except (ValueError, TypeError, KeyError) as exc:
            flags.append(str(exc))
            parsed = None
        if flags:
            blocked.append({"source_row": number, "bet_id": r.get("bet_id"), "reasons": sorted(set(flags))})
        else:
            accepted.append(parsed)
    # Never aggregate paper and claimed executed stakes as a single ROI.
    stake_basis = collections.Counter(x["stake_basis"] for x in accepted)
    mixed_basis = len(stake_basis) > 1
    basis_summary = {basis: status_summary([x for x in accepted if x["stake_basis"] == basis])
                     for basis in sorted(stake_basis)}
    settled = [x for x in accepted if x["net"] is not None]
    game_returns = collections.defaultdict(float)
    for x in settled:
        game_returns[(x["sport"],x["event_id"])] += x["net"]
    variance = statistics.variance(game_returns.values()) if len(game_returns) >= 30 else None
    return {
        "status": "PAPER_STRUCTURAL_RESEARCH_NOT_PROVIDER_AUTHENTICATED",
        "input_rows": len(input_rows), "accepted": len(accepted), "blocked": blocked,
        "stake_basis_counts": dict(stake_basis), "mixed_stake_basis": mixed_basis,
        "performance_by_stake_basis": basis_summary,
        "performance": None if mixed_basis else status_summary(accepted),
        "settled_game_net_units_sample_variance": None if mixed_basis else variance,
        "exposure": overlap(accepted),
        "max_drawdown": None if mixed_basis else peak_to_trough(accepted),
        "stress": None if mixed_basis else {"payout_haircut_0pct": stress_haircut(accepted, 0),
                   "payout_haircut_5pct": stress_haircut(accepted, .05),
                   "payout_haircut_10pct": stress_haircut(accepted, .10)},
        "game_bootstrap": {"status":"MIXED_STAKE_BASIS_CANNOT_POOL"} if mixed_basis else block_bootstrap(accepted, iterations=iterations),
        "connected_theme_bootstrap": {"status":"MIXED_STAKE_BASIS_CANNOT_POOL"} if mixed_basis else block_bootstrap(accepted, iterations=iterations,connect_themes=True),
        "by_model_version": group_results(accepted, "model_version"),
        "by_rules_version": group_results(accepted, "rules_version"),
        "by_market": group_results(accepted, "market"),
        "by_direction": group_results(accepted, "direction"),
        "by_sport": group_results(accepted, "sport"),
        "by_month": group_results(accepted, "selected_month_ct"),
        "by_player": group_results(accepted, "player_id"),
        "by_theme": group_results(accepted, "theme_id"),
        "safety": [
            "Local SHA256 formats and self-declared timestamps do not authenticate providers or pregame availability.",
            "An asserted universe_complete_claim does NOT prove complete inclusion of losing or unqualified candidates.",
            "No actual historical ROI, statistical edge, covariance or official wagers are certified by this module.",
            "Correlation is flagged by shared event/theme, not inferred from a few co-occurring bet outcomes.",
            "Explicit theme-connected blocks can link games and may invalidate an otherwise optimistic game-only CI.",
            "Pending bets are excluded from performance while retained in population; no selection may be erased.",
            "Paper and executed-claim stake bases cannot be pooled into one return or bootstrap.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--bootstrap", type=int, default=2000)
    args = parser.parse_args(argv)
    with open(args.private_csv, encoding="utf-8-sig", newline="") as f:
        records = list(csv.DictReader(f))
    report = audit(records, iterations=args.bootstrap)
    raw = Path(args.private_csv).read_bytes()
    report["original_local_file_sha256"] = hashlib.sha256(raw).hexdigest()
    # Never overwrite historical report; private output path is caller-controlled.
    with Path(args.output).open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"PAPER only: accepted {report['accepted']}, blocked {len(report['blocked'])}; no betting certification")


if __name__ == "__main__":
    main()