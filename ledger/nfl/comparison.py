"""Read-only NFL freeze/settle comparison and quantitative validation. Stdlib only.

Research diagnostics only; approved stake 0. No model promotion or real betting
performance is implied. Never fabricates missing probabilities, finals, or CLV.
"""
import argparse
import math
import os
import random

FIELDS = ("model_p", "market_p", "blend_p")
IDENTITY = ("market", "family", "pick", "player", "line", "price")
VALID_PROB_DEFS = ("conditional_no_push", "unconditional_win")
EPS = 1e-6


class ProbabilityBindingError(ValueError):
    """Settlement row, probability, identity, or outcome disagrees with frozen source."""


class PushSemanticsError(ValueError):
    """Push-capable market lacks compatible conditional probability semantics."""


def probability(value):
    """Return finite float in [0, 1], or None if missing/invalid."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        p = float(value)
    except (ValueError, TypeError):
        return None
    return p if math.isfinite(p) and 0.0 <= p <= 1.0 else None


def _is_missing(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_strict_prob(raw, label, index, field):
    if _is_missing(raw):
        return None
    p = probability(raw)
    if p is None:
        raise ProbabilityBindingError(
            f"{label} row {index} {field} is invalid or nonfinite: {raw!r}")
    return p


def _same(left, right):
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, float) and isinstance(right, float):
        if not (math.isfinite(left) and math.isfinite(right)):
            return False
        return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
    return left == right


def is_push_capable(row):
    """True when a market can settle as a push (NFL ML tie or integer line)."""
    fam = (row.get("family") or "").lower()
    mkt = (row.get("market") or "").lower()
    if fam == "ml" or mkt.endswith("_ml") or mkt == "ml":
        return True
    line = row.get("line")
    if line is None:
        return False
    try:
        val = float(line)
    except (TypeError, ValueError):
        return False
    return math.isfinite(val) and val.is_integer()


def resolve_conditional_prob(row, field, default_prob_definition=None):
    """Return P(W | W or L) for binary scoring, enforcing push semantics."""
    p = _parse_strict_prob(row.get(field), row.get("pick_set", "?"),
                           row.get("row", -1), field)
    if p is None:
        return None
    if not is_push_capable(row):
        return p
    pdef = row.get("prob_definition") or default_prob_definition
    if pdef not in VALID_PROB_DEFS:
        raise PushSemanticsError(
            f"push-capable market {row.get('market')!r} (line={row.get('line')}) "
            f"requires explicit prob_definition in {VALID_PROB_DEFS}, got {pdef!r}")
    if pdef == "conditional_no_push":
        return p
    push_p = _parse_strict_prob(row.get("push_p"), row.get("pick_set", "?"),
                                row.get("row", -1), "push_p")
    if push_p is None or push_p >= 1.0 or p + push_p > 1.0 + 1e-9:
        raise PushSemanticsError(
            f"unconditional_win on push-capable market {row.get('market')!r} "
            f"requires valid push_p with p + push_p <= 1 (p={p}, push_p={push_p})")
    return min(1.0, max(0.0, p / (1.0 - push_p)))


def _expected_from_frozen(raw, index, label):
    from common import fnum, is_held, market_family, normalize_row, price_of
    from settle import _selected
    row = normalize_row(raw)
    price = price_of(row)
    row_id = row.get("row_id")
    if row_id not in (None, ""):
        if not str(row_id).isdecimal() or int(row_id) != index:
            raise ProbabilityBindingError(
                f"{label} row {index} frozen row_id={row_id!r} != {index}")
        row_id = int(row_id)
    else:
        row_id = None
    market = row.get("market")
    return {
        "row_id": row_id,
        "quote_id": row.get("quote_id") or None,
        "market": market,
        "family": market_family(market),
        "pick": row.get("pick"),
        "player": row.get("player") or None,
        "line": fnum(row.get("line")),
        "price": price,
        "on_card": _selected(row),
        "held": is_held(row.get("held")),
        "model_p": _parse_strict_prob(row.get("model_p"), label, index, "model_p"),
        "market_p": _parse_strict_prob(row.get("market_p"), label, index, "market_p"),
        "blend_p": _parse_strict_prob(row.get("blend_p"), label, index, "blend_p"),
        "prob_definition": (row.get("prob_definition") or "").strip() or None,
        "push_p": _parse_strict_prob(row.get("push_p"), label, index, "push_p"),
        "_normalized": row,
    }


def _finals_match(actual, authenticated):
    if actual is None or authenticated is None:
        return False
    for key in ("away", "home"):
        if str(actual.get(key, "")).upper() != str(authenticated.get(key, "")).upper():
            return False
    for key in ("away_score", "home_score"):
        if float(actual[key]) != float(authenticated[key]):
            return False
    auth_periods = authenticated.get("periods") or {}
    act_periods = actual.get("periods") or {}
    for per, scores in auth_periods.items():
        if per not in act_periods or [float(x) for x in act_periods[per]] != [float(x) for x in scores]:
            return False
    return True


def bind_frozen_run(run, labels, authenticated_finals=None, stats_by_run=None):
    """Reconcile every priced frozen row, probability, identity, and outcome."""
    from common import price_of, read_csv
    from freeze import verify
    from settle import check_finals_identity, grade_row

    run_dir = run.get("run_dir")
    if not run_dir:
        raise ProbabilityBindingError("frozen run directory required")
    if verify(run_dir):
        raise ProbabilityBindingError("frozen run failed verification")

    manifest = run["manifest"]
    settlement = run["settlement"]
    if not settlement.get("source"):
        raise ProbabilityBindingError("settlement missing result source")
    finals = settlement.get("finals")
    if not isinstance(finals, dict):
        raise ProbabilityBindingError("settlement missing finals")
    try:
        check_finals_identity(manifest, finals)
    except Exception as exc:
        raise ProbabilityBindingError(str(exc)) from exc

    if authenticated_finals is not None:
        rid = manifest["run_id"]
        if rid not in authenticated_finals:
            raise ProbabilityBindingError(f"no authenticated finals for run {rid}")
        if not _finals_match(finals, authenticated_finals[rid]):
            raise ProbabilityBindingError(f"settlement finals disagree with authenticated finals for {rid}")

    stats = (stats_by_run or {}).get(manifest["run_id"])
    check_keys = ("row_id", "quote_id", "market", "family", "pick", "player",
                  "line", "price", "on_card", "held", "model_p", "market_p", "blend_p")

    enriched = {}
    for label in labels:
        if label not in manifest.get("pick_sets", []):
            raise ProbabilityBindingError(f"pick set {label!r} not in manifest")
        raw_rows = read_csv(os.path.join(run_dir, label, "picks_nfl.csv"))
        expected_by_index = {}
        for i, raw in enumerate(raw_rows):
            try:
                price_of(raw)
            except ValueError:
                continue
            expected_by_index[i] = _expected_from_frozen(raw, i, label)

        seen_indices = set()
        for graded in settlement["graded"]:
            if graded["pick_set"] != label:
                continue
            if graded.get("approved_stake_u") != 0:
                raise ProbabilityBindingError(f"{label} row has nonzero/missing approved_stake_u")
            index = graded.get("row")
            if type(index) is not int or index not in expected_by_index:
                raise ProbabilityBindingError(
                    f"{label} settlement has unexpected or unpriced row index {index!r}")
            if index in seen_indices:
                raise ProbabilityBindingError(f"{label} duplicate settlement row index {index}")
            seen_indices.add(index)
            exp = expected_by_index[index]
            for field in FIELDS:
                _parse_strict_prob(graded.get(field), label, index, field)
            for key in check_keys:
                if not _same(graded.get(key), exp[key]):
                    raise ProbabilityBindingError(
                        f"{label} row {index} {key} does not match frozen prediction")
            if not exp["family"].startswith("prop:") or stats is not None:
                expected_res, _ = grade_row(exp["_normalized"], finals, stats or {})
                if graded.get("result") != expected_res:
                    raise ProbabilityBindingError(
                        f"{label} row {index} result {graded.get('result')!r} != regraded {expected_res!r}")
            merged = dict(graded)
            if merged.get("prob_definition") is None and exp["prob_definition"] is not None:
                merged["prob_definition"] = exp["prob_definition"]
            if merged.get("push_p") is None and exp["push_p"] is not None:
                merged["push_p"] = exp["push_p"]
            enriched[(label, index)] = merged

        missing_indices = set(expected_by_index) - seen_indices
        if missing_indices:
            raise ProbabilityBindingError(
                f"{label} settlement missing priced frozen rows: {sorted(missing_indices)}")
    return enriched


def _brier(p, y):
    return (p - y) ** 2


def _log_loss(p, y):
    pc = min(1.0 - EPS, max(EPS, p))
    return -(y * math.log(pc) + (1.0 - y) * math.log(1.0 - pc))


def _calibration_bins(pairs, num_bins=5):
    """pairs: list of (p, y). Returns reliability bins and ECE."""
    if not pairs:
        return {"bins": [], "ece": None}
    bins = []
    n_total = len(pairs)
    ece = 0.0
    for i in range(num_bins):
        lo = i / num_bins
        hi = (i + 1) / num_bins
        if i == num_bins - 1:
            sub = [(p, y) for p, y in pairs if lo <= p <= hi]
        else:
            sub = [(p, y) for p, y in pairs if lo <= p < hi]
        if not sub:
            continue
        mp = sum(p for p, _ in sub) / len(sub)
        er = sum(y for _, y in sub) / len(sub)
        gap = abs(mp - er)
        ece += (len(sub) / n_total) * gap
        bins.append({"range": f"[{lo:.1f},{hi:.1f}{']' if i == num_bins - 1 else ')'}",
                     "n": len(sub), "mean_p": mp, "emp_rate": er, "abs_gap": gap})
    return {"bins": bins, "ece": ece}


def _game_clustered_ci(game_values, n_boot=1000, seed=42):
    """Percentile 95% CI via deterministic block bootstrap over game clusters."""
    games = sorted(game_values)
    g = len(games)
    if g < 2:
        return None
    means_by_game = [sum(game_values[k]) / len(game_values[k]) for k in games]
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        sample = [means_by_game[rng.randrange(g)] for _ in range(g)]
        boots.append(sum(sample) / g)
    boots.sort()
    return [boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot)]]


def _dedupe_runs(runs, capture_policy):
    """Return eligible runs, optionally keeping only the latest valid pregame run per game."""
    valid = []
    excluded = 0
    seen_runs = set()
    for run in runs:
        m, s = run["manifest"], run.get("settlement")
        if m["run_id"] in seen_runs:
            raise ValueError("duplicate run")
        seen_runs.add(m["run_id"])
        if (run.get("quarantined") or not s or s.get("quarantined")
                or s.get("run_integrity_ok") is not True):
            excluded += 1
            continue
        if s.get("run_id") != m["run_id"] or s.get("game") != m["game"]:
            raise ValueError("settlement identity mismatch")
        valid.append(run)
    if capture_policy == "all_captures":
        return valid, excluded, 0
    if capture_policy != "latest_pregame":
        raise ValueError(f"unknown capture_policy: {capture_policy!r}")
    by_game = {}
    superseded = 0
    for run in valid:
        m = run["manifest"]
        if m.get("pregame") is False:
            excluded += 1
            continue
        game = m["game"]
        prev = by_game.get(game)
        if prev is None:
            by_game[game] = run
        elif m["capture_utc"] >= prev["manifest"]["capture_utc"]:
            by_game[game] = run
            superseded += 1
        else:
            superseded += 1
    return [by_game[g] for g in sorted(by_game)], excluded, superseded


def _summarize_metric_rows(obs, n_boot=1000, seed=42):
    """obs: list of dicts with game, left_p, right_p, y, units, clv."""
    if not obs:
        return {"n": 0, "n_games": 0, "left": None, "right": None,
                "delta_brier": None, "delta_brier_ci95": None,
                "delta_log_loss": None, "delta_log_loss_ci95": None,
                "left_log_loss": None, "right_log_loss": None,
                "game_weighted_left_brier": None, "game_weighted_right_brier": None,
                "left_calibration": {"bins": [], "ece": None},
                "right_calibration": {"bins": [], "ece": None},
                "hypothetical_roi_1u": None, "clv": None}
    n = len(obs)
    games = sorted({o["game"] for o in obs})
    lb = [_brier(o["left_p"], o["y"]) for o in obs]
    rb = [_brier(o["right_p"], o["y"]) for o in obs]
    lll = [_log_loss(o["left_p"], o["y"]) for o in obs]
    rll = [_log_loss(o["right_p"], o["y"]) for o in obs]
    by_game_lb, by_game_rb, by_game_db, by_game_dll = {}, {}, {}, {}
    for o, a, b, c, d in zip(obs, lb, rb, lll, rll):
        g = o["game"]
        by_game_lb.setdefault(g, []).append(a)
        by_game_rb.setdefault(g, []).append(b)
        by_game_db.setdefault(g, []).append(a - b)
        by_game_dll.setdefault(g, []).append(c - d)
    gw_lb = sum(sum(v) / len(v) for v in by_game_lb.values()) / len(games)
    gw_rb = sum(sum(v) / len(v) for v in by_game_rb.values()) / len(games)
    units = [o["units"] for o in obs if o.get("units") is not None]
    roi = sum(units) / len(units) if units else None
    clvs = [o["clv"] for o in obs if o.get("clv") is not None]
    clv_out = ({"mean": sum(clvs) / len(clvs), "n": len(clvs), "status": "AUTHENTICATED_CLOSING_QUOTES"}
               if clvs else {"mean": None, "n": 0, "status": "NOT_AVAILABLE_NO_AUTHENTICATED_CLOSING_QUOTES"})
    return {
        "n": n,
        "n_games": len(games),
        "left": sum(lb) / n,
        "right": sum(rb) / n,
        "delta_brier": (sum(lb) - sum(rb)) / n,
        "delta_brier_ci95": _game_clustered_ci(by_game_db, n_boot=n_boot, seed=seed),
        "left_log_loss": sum(lll) / n,
        "right_log_loss": sum(rll) / n,
        "delta_log_loss": (sum(lll) - sum(rll)) / n,
        "delta_log_loss_ci95": _game_clustered_ci(by_game_dll, n_boot=n_boot, seed=seed),
        "game_weighted_left_brier": gw_lb,
        "game_weighted_right_brier": gw_rb,
        "left_calibration": _calibration_bins([(o["left_p"], o["y"]) for o in obs]),
        "right_calibration": _calibration_bins([(o["right_p"], o["y"]) for o in obs]),
        "hypothetical_roi_1u": roi,
        "clv": clv_out,
    }


def compare(runs, left, right, *, default_prob_definition=None,
            capture_policy="latest_pregame", authenticated_finals=None,
            stats_by_run=None, closing_quotes=None, n_boot=1000, seed=42):
    """Paired comparison of two frozen pick sets with full P0+P1 diagnostics."""
    if left == right:
        raise ValueError("choose distinct pick sets")
    eligible_runs, excluded_runs, superseded_runs = _dedupe_runs(runs, capture_policy)
    counts = dict(matched=0, unmatched=0, excluded_runs=excluded_runs,
                  superseded_runs=superseded_runs, missing_identity=0, push_or_ng=0)
    states = {label: dict(selected=0, unselected=0, unknown=0) for label in (left, right)}
    obs_by_field = {field: [] for field in FIELDS}
    family_obs = {field: {} for field in FIELDS}

    for run in eligible_runs:
        m = run["manifest"]
        enriched = bind_frozen_run(run, (left, right),
                                   authenticated_finals=authenticated_finals,
                                   stats_by_run=stats_by_run)
        indexed = {left: {}, right: {}}
        for (label, _idx), row in enriched.items():
            selected = row.get("on_card")
            if selected is not None and type(selected) is not bool:
                raise ValueError("malformed selection state")
            states[label]["unknown" if selected is None else "selected" if selected else "unselected"] += 1
            qid = row.get("quote_id")
            rid = row.get("row_id")
            if not qid or type(rid) is not int or rid < 0:
                counts["missing_identity"] += 1
                continue
            if qid in indexed[label]:
                raise ValueError("duplicate quote identity")
            indexed[label][qid] = row

        a, b = indexed[left], indexed[right]
        counts["unmatched"] += len(set(a) ^ set(b))
        for qid in sorted(set(a) & set(b)):
            x, y = a[qid], b[qid]
            if any(not _same(x.get(k), y.get(k)) for k in IDENTITY):
                raise ValueError("conflicting quote contract")
            if x["result"] != y["result"]:
                raise ValueError("conflicting settlement results")
            if is_push_capable(x):
                dx = x.get("prob_definition") or default_prob_definition
                dy = y.get("prob_definition") or default_prob_definition
                if dx != dy:
                    raise PushSemanticsError(
                        f"incompatible prob_definition on {qid}: {dx!r} vs {dy!r}")
            counts["matched"] += 1
            if x["result"] not in ("W", "L"):
                counts["push_or_ng"] += 1
                continue
            actual = int(x["result"] == "W")
            close_p = (closing_quotes or {}).get((m["run_id"], qid))
            clv = (float(close_p) - x["market_p"]) if (close_p is not None and x.get("market_p") is not None) else None
            for field in FIELDS:
                px = resolve_conditional_prob(x, field, default_prob_definition)
                py = resolve_conditional_prob(y, field, default_prob_definition)
                if px is not None and py is not None:
                    rec = {"game": m["game"], "family": x["family"], "left_p": px,
                           "right_p": py, "y": actual, "units": x.get("units"), "clv": clv}
                    obs_by_field[field].append(rec)
                    family_obs[field].setdefault(x["family"], []).append(rec)

    scores = {}
    by_family = {}
    for field in FIELDS:
        obs = obs_by_field[field]
        summary = _summarize_metric_rows(obs, n_boot=n_boot, seed=seed)
        summary["missing_or_invalid"] = counts["matched"] - counts["push_or_ng"] - summary["n"]
        scores[field] = summary
        by_family[field] = {
            fam: _summarize_metric_rows(rows, n_boot=n_boot, seed=seed)
            for fam, rows in sorted(family_obs[field].items())
        }

    return dict(left=left, right=right, capture_policy=capture_policy,
                counts=counts, selection=states, scores=scores, by_family=by_family,
                probabilities="reconciled_to_frozen_picks")


def compare_prospective_candidates(runs, pick_set, *, default_prob_definition=None,
                                   capture_policy="latest_pregame",
                                   authenticated_finals=None, stats_by_run=None,
                                   closing_quotes=None, n_boot=1000, seed=42):
    """Evaluate fixed-weight candidates on the exact same eligible sample.

    Candidates (no retrospective weight optimization):
      - market_only: 100% market / 0% model
      - blend_90_10: 90% market / 10% model
      - current_model: frozen blend_p
      - independent_model: 0% market / 100% model
    """
    eligible_runs, excluded_runs, superseded_runs = _dedupe_runs(runs, capture_policy)
    cand_names = ("market_only", "blend_90_10", "current_model", "independent_model")
    rows_by_cand = {c: [] for c in cand_names}
    family_by_cand = {c: {} for c in cand_names}
    skipped = 0

    for run in eligible_runs:
        m = run["manifest"]
        enriched = bind_frozen_run(run, (pick_set,),
                                   authenticated_finals=authenticated_finals,
                                   stats_by_run=stats_by_run)
        for (_label, _idx), row in sorted(enriched.items()):
            if row["result"] not in ("W", "L"):
                skipped += 1
                continue
            mp = resolve_conditional_prob(row, "model_p", default_prob_definition)
            kp = resolve_conditional_prob(row, "market_p", default_prob_definition)
            bp = resolve_conditional_prob(row, "blend_p", default_prob_definition)
            if mp is None or kp is None or bp is None:
                skipped += 1
                continue
            actual = int(row["result"] == "W")
            qid = row.get("quote_id")
            close_p = (closing_quotes or {}).get((m["run_id"], qid)) if qid else None
            clv = (float(close_p) - kp) if close_p is not None else None
            probs = {
                "market_only": kp,
                "blend_90_10": 0.9 * kp + 0.1 * mp,
                "current_model": bp,
                "independent_model": mp,
            }
            for cname, pval in probs.items():
                rec = {"game": m["game"], "family": row["family"],
                       "left_p": pval, "right_p": kp, "y": actual,
                       "units": row.get("units"), "clv": clv}
                rows_by_cand[cname].append(rec)
                family_by_cand[cname].setdefault(row["family"], []).append(rec)

    results = {}
    for cname in cand_names:
        summary = _summarize_metric_rows(rows_by_cand[cname], n_boot=n_boot, seed=seed)
        results[cname] = {
            "n": summary["n"],
            "n_games": summary["n_games"],
            "brier": summary["left"],
            "game_weighted_brier": summary["game_weighted_left_brier"],
            "delta_brier_vs_market": summary["delta_brier"],
            "delta_brier_vs_market_ci95": summary["delta_brier_ci95"],
            "log_loss": summary["left_log_loss"],
            "delta_log_loss_vs_market": summary["delta_log_loss"],
            "delta_log_loss_vs_market_ci95": summary["delta_log_loss_ci95"],
            "calibration": summary["left_calibration"],
            "hypothetical_roi_1u": summary["hypothetical_roi_1u"],
            "clv": summary["clv"],
            "by_family": {
                fam: {
                    "n": s["n"], "n_games": s["n_games"], "brier": s["left"],
                    "log_loss": s["left_log_loss"], "ece": s["left_calibration"]["ece"],
                    "hypothetical_roi_1u": s["hypothetical_roi_1u"],
                }
                for fam, s in (
                    (f, _summarize_metric_rows(r, n_boot=n_boot, seed=seed))
                    for f, r in sorted(family_by_cand[cname].items())
                )
            },
        }
    return {
        "pick_set": pick_set,
        "capture_policy": capture_policy,
        "excluded_runs": excluded_runs,
        "superseded_runs": superseded_runs,
        "skipped_rows": skipped,
        "candidates": results,
    }


def render(report):
    lines = [
        "# NFL paired ledger comparison", "",
        "Research only. Approved stake 0. No real betting performance or promotion claim.",
        "Scored probabilities and outcomes are reconciled to frozen picks and finals.",
        f"Capture policy: {report.get('capture_policy', 'latest_pregame')}.",
        "Brier and log loss use matched W/L rows with explicit push semantics; lower is better.",
        "Game-clustered 95% CIs require at least 2 distinct games.", "",
        f"Left: {report['left']} | Right: {report['right']}",
        f"Coverage: {report['counts']}",
        f"Selection states: {report['selection']}", "",
        "| Field | Paired n | Games | Left Brier | Right Brier | Delta Brier (95% CI) | Left LL | Right LL | Hypothetical 1u ROI |",
        "|---|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    for field, s in report["scores"].items():
        if s["n"]:
            ci = (f"[{s['delta_brier_ci95'][0]:+.4f}, {s['delta_brier_ci95'][1]:+.4f}]"
                  if s["delta_brier_ci95"] is not None else "n_games<2")
            roi = f"{s['hypothetical_roi_1u']:+.1%}" if s["hypothetical_roi_1u"] is not None else "N/A"
            lines.append(
                f"| {field} | {s['n']} | {s['n_games']} | {s['left']:.6f} | {s['right']:.6f} | "
                f"{s['delta_brier']:+.6f} ({ci}) | {s['left_log_loss']:.6f} | {s['right_log_loss']:.6f} | {roi} |")
        else:
            lines.append(f"| {field} | 0 | 0 | N/A | N/A | N/A | N/A | N/A | N/A |")
    return "\n".join(lines) + "\n"


def main():
    from common import RUNS_DIR, SETTLE_DIR
    from freeze import verify
    from scorecard import load_week
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--left", required=True)
    ap.add_argument("--right", required=True)
    ap.add_argument("--runs-dir", default=RUNS_DIR)
    ap.add_argument("--settle-dir", default=SETTLE_DIR)
    ap.add_argument("--prob-definition", choices=VALID_PROB_DEFS)
    ap.add_argument("--capture-policy", choices=("latest_pregame", "all_captures"),
                    default="latest_pregame")
    a = ap.parse_args()
    runs = load_week(a.date_from, a.date_to, a.runs_dir, a.settle_dir)
    for run in runs:
        run["run_dir"] = os.path.join(a.runs_dir, run["manifest"]["run_id"])
        if verify(run["run_dir"]):
            run["quarantined"] = True
    print(render(compare(runs, a.left, a.right,
                         default_prob_definition=a.prob_definition,
                         capture_policy=a.capture_policy)), end="")


if __name__ == "__main__":
    main()
