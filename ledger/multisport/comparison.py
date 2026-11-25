"""Shared seven-sport comparison and quantitative validation engine. Stdlib only.

Fixes survivorship fallback (dedupes latest pregame per event BEFORE filtering
quarantined/unsettled runs), enforces parsed UTC capture < start timestamps,
fails closed on ambiguous equal-time captures and on inconsistent event start
times, aligns cluster bootstrap CIs with both equal-event and row-weighted
estimates, and discloses small-cluster warnings (n_events < 30). ROI is
reported two ways: decided-rows-only hypothetical_roi_1u, and all-quote
roi_all_quotes_1u where pushes settle at 0.0 and PGA dead heats settle at
their fractional book payout; rows excluded from the paired probability
sample are counted in exclusion_audit and sample_census.
"""
import math
import random
from datetime import datetime, timezone

try:
    from .adapters import SPORTS, dead_heat_win_fraction, grade_row, is_push_capable, market_family
except ImportError:
    from adapters import SPORTS, dead_heat_win_fraction, grade_row, is_push_capable, market_family

FIELDS = ("model_p", "market_p", "blend_p")
VALID_PROB_DEFS = ("conditional_no_push", "unconditional_win")
COVERAGE_REASONS = ("NOT_OFFERED", "NOT_CAPTURED", "NO_MODEL", "NO_PROVENANCE", "UNSUPPORTED", "LIVE_OR_CLOSED")
EPS = 1e-6
MODEL_WEIGHT_GRID = (0, 25, 50, 60, 75, 80, 90, 95, 100)


class IntegrityError(ValueError):
    """Frozen/settled record failed reconciliation or temporal integrity."""


class PushSemanticsError(ValueError):
    """Push-capable market lacks compatible conditional probability semantics."""


def _parse_utc(ts):
    if not ts or not isinstance(ts, str):
        raise IntegrityError(f"missing or invalid UTC timestamp: {ts!r}")
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise IntegrityError(f"timestamp missing timezone offset: {ts!r}")
    return dt.astimezone(timezone.utc)


def probability(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        p = float(value)
    except (ValueError, TypeError):
        return None
    return p if math.isfinite(p) and 0.0 <= p <= 1.0 else None


def _strict_prob(value, context):
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    p = probability(value)
    if p is None:
        raise IntegrityError(f"invalid or nonfinite probability in {context}: {value!r}")
    return p


def _profit_1u(price, result):
    try:
        p = float(price)
    except (TypeError, ValueError, OverflowError) as exc:
        raise IntegrityError(f"invalid American price {price!r}") from exc
    if not math.isfinite(p) or not p.is_integer() or abs(p) < 100:
        raise IntegrityError(f"invalid American price {price!r}")
    if result == "P":
        return 0.0
    if result == "L":
        return -1.0
    if result == "W":
        return p / 100.0 if p > 0 else 100.0 / -p
    return None


def select_latest_pregame_runs(runs):
    """Select latest pregame run per (sport, event_id) BEFORE filtering quarantined/unsettled.

    Prevents survivorship fallback to an earlier capture when the latest capture
    was quarantined or unsettled. Also enforces parsed capture_utc < start_utc.
    """
    by_event = {}
    starts = {}
    superseded = 0
    postgame_excluded = 0
    seen_ids = set()
    seen_captures = {}

    for run in runs:
        m = run["manifest"]
        rid = m["run_id"]
        if rid in seen_ids:
            raise IntegrityError(f"duplicate run_id {rid!r}")
        seen_ids.add(rid)
        sport = m["sport"].upper()
        if sport not in SPORTS:
            raise IntegrityError(f"unsupported sport {sport!r}")
        cap_dt = _parse_utc(m["capture_utc"])
        start_dt = _parse_utc(m["start_utc"])
        if cap_dt >= start_dt:
            postgame_excluded += 1
            continue
        key = (sport, m["event_id"])
        if key in starts and starts[key] != start_dt:
            raise IntegrityError(
                f"inconsistent start_utc for {sport} event {m['event_id']!r}: "
                f"{starts[key].isoformat()} vs {start_dt.isoformat()}")
        starts[key] = start_dt
        capture_key = (key, cap_dt)
        if capture_key in seen_captures:
            raise IntegrityError(
                f"ambiguous equal-time captures for {sport} event {m['event_id']!r} "
                f"at {cap_dt.isoformat()}: {seen_captures[capture_key]!r} vs {rid!r}")
        seen_captures[capture_key] = rid
        prev = by_event.get(key)
        if prev is None:
            by_event[key] = (cap_dt, run)
        elif cap_dt > prev[0]:
            by_event[key] = (cap_dt, run)
            superseded += 1
        else:
            superseded += 1

    eligible = []
    quarantined_or_unsettled = 0
    for key in sorted(by_event):
        _, run = by_event[key]
        s = run.get("settlement")
        if (run.get("quarantined") or not s or s.get("quarantined")
                or s.get("run_integrity_ok") is not True):
            quarantined_or_unsettled += 1
            continue
        eligible.append(run)

    return eligible, {
        "superseded_pregame_runs": superseded,
        "postgame_excluded": postgame_excluded,
        "quarantined_or_unsettled": quarantined_or_unsettled,
    }


def _reconcile_run(run, pick_set, authenticated_finals=None):
    m = run["manifest"]
    s = run["settlement"]
    sport = m["sport"].upper()
    if s.get("run_id") != m["run_id"] or s.get("event_id") != m["event_id"]:
        raise IntegrityError("settlement run_id/event_id mismatch")
    finals = s.get("finals")
    if not isinstance(finals, dict) or not s.get("source"):
        raise IntegrityError("settlement missing finals or source")
    if authenticated_finals is not None:
        if m["run_id"] not in authenticated_finals:
            raise IntegrityError(f"missing authenticated finals for {m['run_id']}")
        if finals != authenticated_finals[m["run_id"]]:
            raise IntegrityError(f"finals mismatch against authenticated finals for {m['run_id']}")

    frozen_rows = run["frozen_picks"][pick_set]
    graded_rows = [g for g in s["graded"] if g["pick_set"] == pick_set]
    if len(graded_rows) != len(frozen_rows):
        raise IntegrityError(f"{pick_set} graded count {len(graded_rows)} != frozen count {len(frozen_rows)}")

    stats = s.get("stats") or {}
    out = []
    seen_indices = set()
    for g in graded_rows:
        idx = g.get("row")
        if type(idx) is not int or not (0 <= idx < len(frozen_rows)) or idx in seen_indices:
            raise IntegrityError(f"{pick_set} invalid or duplicate row index {idx!r}")
        seen_indices.add(idx)
        fr = frozen_rows[idx]
        if g.get("approved_stake_u", 0) != 0 or fr.get("approved_stake_u", 0) != 0:
            raise IntegrityError("nonzero approved_stake_u refused")
        for key in ("quote_id", "market", "pick", "player", "line", "price"):
            if g.get(key) != fr.get(key):
                raise IntegrityError(f"{pick_set} row {idx} {key} mismatch")
        for field in FIELDS:
            fp = _strict_prob(fr.get(field), f"{pick_set}[{idx}].{field}")
            gp = _strict_prob(g.get(field), f"settlement.{pick_set}[{idx}].{field}")
            if fp != gp:
                raise IntegrityError(f"{pick_set} row {idx} {field} altered in settlement")
        regraded, _ = grade_row(sport, fr, finals, stats)
        if g.get("result") != regraded:
            raise IntegrityError(f"{pick_set} row {idx} result {g.get('result')!r} != regraded {regraded!r}")
        merged = dict(g)
        merged["family"] = market_family(sport, fr["market"])
        merged["prob_definition"] = fr.get("prob_definition")
        merged["push_p"] = fr.get("push_p")
        out.append(merged)
    return out


def _cond_prob(sport, row, field, default_prob_definition=None):
    p = _strict_prob(row.get(field), field)
    if p is None:
        return None
    if not is_push_capable(sport, row):
        return p
    pdef = row.get("prob_definition") or default_prob_definition
    if pdef not in VALID_PROB_DEFS:
        raise PushSemanticsError(f"{sport} push-capable market {row['market']!r} missing valid prob_definition")
    if pdef == "conditional_no_push":
        return p
    push_p = _strict_prob(row.get("push_p"), "push_p")
    if push_p is None or push_p >= 1.0 or p + push_p > 1.0 + 1e-9:
        raise PushSemanticsError(f"invalid push_p={push_p} for unconditional_win p={p}")
    return min(1.0, max(0.0, p / (1.0 - push_p)))


def _cluster_bootstrap(by_event, mode="equal_event", n_boot=1000, seed=42):
    events = sorted(by_event)
    g = len(events)
    if g < 2:
        return None
    rng = random.Random(seed)
    boots = []
    if mode == "equal_event":
        vals = [sum(by_event[e]) / len(by_event[e]) for e in events]
        for _ in range(n_boot):
            boots.append(sum(vals[rng.randrange(g)] for _ in range(g)) / g)
    else:
        sums = [sum(by_event[e]) for e in events]
        cnts = [len(by_event[e]) for e in events]
        for _ in range(n_boot):
            idxs = [rng.randrange(g) for _ in range(g)]
            boots.append(sum(sums[i] for i in idxs) / sum(cnts[i] for i in idxs))
    boots.sort()
    return [boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot)]]


def _calibration(pairs, num_bins=5):
    if not pairs:
        return {"bins": [], "ece": None}
    bins, ece, n = [], 0.0, len(pairs)
    for i in range(num_bins):
        lo, hi = i / num_bins, (i + 1) / num_bins
        sub = [(p, y) for p, y in pairs if (lo <= p <= hi if i == num_bins - 1 else lo <= p < hi)]
        if not sub:
            continue
        mp = sum(p for p, _ in sub) / len(sub)
        er = sum(y for _, y in sub) / len(sub)
        gap = abs(mp - er)
        ece += (len(sub) / n) * gap
        bins.append({"range": f"[{lo:.1f},{hi:.1f}{']' if i == num_bins - 1 else ')'}",
                     "n": len(sub), "mean_p": mp, "emp_rate": er, "abs_gap": gap})
    return {"bins": bins, "ece": ece}


def evaluate_multisport(runs, pick_set, *, default_prob_definition=None,
                        authenticated_finals=None, closing_quotes=None,
                        n_boot=1000, seed=42, include_nine_weights=False):
    """Evaluate on identical eligible rows; optional grid uses supplied market anchor.\n\n    Market provenance is not established by this comparison. Grid metrics\n    are conditional on non-push outcomes, not candidate-specific bets/ROI.\n    """
    if type(include_nine_weights) is not bool:
        raise ValueError("include_nine_weights must be boolean")
    eligible, run_audit = select_latest_pregame_runs(runs)
    cand_names = ("market_only", "blend_90_10", "current_model", "independent_model")
    if include_nine_weights:
        cand_names += tuple(f"model_{w:03d}_market_{100-w:03d}" for w in MODEL_WEIGHT_GRID)
    obs = {c: [] for c in cand_names}
    roi_obs = []
    exclusions = {"push_rows": 0, "dead_heat_rows": 0,
                  "ungraded_rows": 0, "missing_probability_rows": 0}
    coverage_gaps = {}

    for run in eligible:
        m = run["manifest"]
        sport = m["sport"].upper()
        for fam, reason in (m.get("coverage_inventory") or {}).items():
            if reason in COVERAGE_REASONS:
                coverage_gaps.setdefault(sport, {})[fam] = reason
        reconciled = _reconcile_run(run, pick_set, authenticated_finals=authenticated_finals)
        for row in reconciled:
            event_key = f"{sport}:{m['event_id']}"
            if row["result"] == "P":
                frac = dead_heat_win_fraction(row, run["settlement"]["finals"])
                if frac is not None:
                    units = frac * _profit_1u(row["price"], "W") - (1.0 - frac)
                    exclusions["dead_heat_rows"] += 1
                else:
                    units = _profit_1u(row["price"], "P")
                    exclusions["push_rows"] += 1
                roi_obs.append({"sport": sport, "event_id": event_key,
                                "family": row["family"], "units": units})
                continue
            if row["result"] not in ("W", "L"):
                exclusions["ungraded_rows"] += 1
                continue
            units = _profit_1u(row["price"], row["result"])
            roi_obs.append({"sport": sport, "event_id": event_key,
                            "family": row["family"], "units": units})
            mp = _cond_prob(sport, row, "model_p", default_prob_definition)
            kp = _cond_prob(sport, row, "market_p", default_prob_definition)
            bp = _cond_prob(sport, row, "blend_p", default_prob_definition)
            if mp is None or kp is None or bp is None:
                exclusions["missing_probability_rows"] += 1
                continue
            y = int(row["result"] == "W")
            close_p = _strict_prob((closing_quotes or {}).get((m["run_id"], row.get("quote_id"))),
                                   "caller_supplied_closing_probability")
            clv = (close_p - kp) if close_p is not None else None
            probs = {
                "market_only": kp,
                "blend_90_10": 0.9 * kp + 0.1 * mp,
                "current_model": bp,
                "independent_model": mp,
            }
            if include_nine_weights:
                probs.update({f"model_{w:03d}_market_{100-w:03d}": (w * mp + (100-w)*kp)/100 for w in MODEL_WEIGHT_GRID})
            for cname, pval in probs.items():
                obs[cname].append({
                    "sport": sport, "event_id": f"{sport}:{m['event_id']}",
                    "family": row["family"], "p": pval, "market_p": kp,
                    "y": y, "units": units, "clv": clv,
                })

    def _agg(rows):
        if not rows:
            return {"n": 0, "n_events": 0, "brier": None, "log_loss": None, "ece": None,
                    "delta_brier_vs_market_row_weighted": None,
                    "delta_brier_row_ci95": None,
                    "delta_brier_vs_market_event_weighted": None,
                    "delta_brier_event_ci95": None,
                    "small_cluster_warning": True,
                    "hypothetical_roi_1u": None,
                    "clv": {"mean": None, "n": 0, "status": "NOT_AVAILABLE_NO_AUTHENTICATED_CLOSING_QUOTES"}}
        n = len(rows)
        b_list = [(r["p"] - r["y"]) ** 2 for r in rows]
        m_list = [(r["market_p"] - r["y"]) ** 2 for r in rows]
        ll_list = [-(r["y"] * math.log(min(1 - EPS, max(EPS, r["p"]))) +
                     (1 - r["y"]) * math.log(min(1 - EPS, max(EPS, 1 - r["p"])))) for r in rows]
        by_ev = {}
        for r, b, m in zip(rows, b_list, m_list):
            by_ev.setdefault(r["event_id"], []).append(b - m)
        n_ev = len(by_ev)
        ev_delta = sum(sum(v) / len(v) for v in by_ev.values()) / n_ev
        row_delta = sum(b - m for b, m in zip(b_list, m_list)) / n
        cal = _calibration([(r["p"], r["y"]) for r in rows])
        clvs = [r["clv"] for r in rows if r["clv"] is not None]
        clv_out = ({"mean": sum(clvs) / len(clvs), "n": len(clvs), "status": "CALLER_SUPPLIED_CLOSING_PROBABILITIES_UNVERIFIED"}
                   if clvs else {"mean": None, "n": 0, "status": "NOT_AVAILABLE_NO_AUTHENTICATED_CLOSING_QUOTES"})
        return {
            "n": n, "n_events": n_ev,
            "brier": sum(b_list) / n, "log_loss": sum(ll_list) / n,
            "calibration": cal,
            "delta_brier_vs_market_row_weighted": row_delta,
            "delta_brier_row_ci95": _cluster_bootstrap(by_ev, "row_weighted", n_boot, seed),
            "delta_brier_vs_market_event_weighted": ev_delta,
            "delta_brier_event_ci95": _cluster_bootstrap(by_ev, "equal_event", n_boot, seed),
            "small_cluster_warning": n_ev < 30,
            "hypothetical_roi_1u": sum(r["units"] for r in rows) / n,
            "clv": clv_out,
        }

    def _roi_agg(rows):
        """All-quote ROI: every settled quote counts, pushes at 0.0 and dead
        heats at their fractional book settlement. Kept separate from the
        decided-rows-only hypothetical_roi_1u inside _agg."""
        if not rows:
            return {"n_settled_quotes": 0, "roi_all_quotes_1u": None}
        return {"n_settled_quotes": len(rows),
                "roi_all_quotes_1u": sum(r["units"] for r in rows) / len(rows)}

    candidates = {}
    for cname in cand_names:
        rows = obs[cname]
        by_sport = {}
        for sp in sorted({r["sport"] for r in rows} | {r["sport"] for r in roi_obs}):
            sp_rows = [r for r in rows if r["sport"] == sp]
            sp_roi = [r for r in roi_obs if r["sport"] == sp]
            fam_all = sorted({r["family"] for r in sp_rows} | {r["family"] for r in sp_roi})
            by_sport[sp] = {
                "overall": {**_agg(sp_rows), **_roi_agg(sp_roi)},
                "by_family": {
                    fam: {**_agg([r for r in sp_rows if r["family"] == fam]),
                          **_roi_agg([r for r in sp_roi if r["family"] == fam])}
                    for fam in fam_all
                },
            }
        candidates[cname] = {"overall": {**_agg(rows), **_roi_agg(roi_obs)},
                             "by_sport": by_sport}

    eligible_events = {f"{run['manifest']['sport'].upper()}:{run['manifest']['event_id']}"
                       for run in eligible}
    paired_events = {r["event_id"] for r in obs["independent_model"]}
    return {
        "pick_set": pick_set,
        "weight_grid": {"model_percent": list(MODEL_WEIGHT_GRID) if include_nine_weights else [],
                        "market_anchor": "CALLER_SUPPLIED_MARKET_PROBABILITY_PROVENANCE_UNVERIFIED",
                        "probability_basis": "CONDITIONAL_NON_PUSH",
                        "roi_scope": "SAME_FROZEN_SELECTIONS_NOT_WEIGHT_SPECIFIC"} if include_nine_weights else None,
        "run_audit": run_audit,
        "exclusion_audit": exclusions,
        "sample_census": {
            "eligible_events": len(eligible_events),
            "paired_metric_events": len(paired_events),
            "events_without_paired_rows": sorted(eligible_events - paired_events),
        },
        "coverage_gaps": coverage_gaps,
        "candidates": candidates,
    }
