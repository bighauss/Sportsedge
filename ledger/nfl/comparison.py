"""Read-only paired Brier report on the NFL freeze/settle ledger. Stdlib only."""
import argparse
import math
import os

FIELDS = ("model_p", "market_p", "blend_p")
IDENTITY = ("market", "family", "pick", "player", "line", "price")


class ProbabilityBindingError(ValueError):
    """Settlement probability or identity does not match its frozen prediction."""


def probability(value):
    if isinstance(value, bool):
        return None
    try:
        p = float(value)
    except (ValueError, TypeError):
        return None
    return p if math.isfinite(p) and 0 <= p <= 1 else None


def _same(left, right):
    if left is None or right is None:
        return left is None and right is None
    return left == right


def _expected(raw, index):
    from common import fnum, market_family, normalize_row, price_of
    row = normalize_row(raw)
    try:
        price = price_of(row)
    except ValueError as exc:
        raise ProbabilityBindingError("settlement graded an unpriced frozen row") from exc
    row_id = row.get("row_id")
    if row_id not in (None, ""):
        if not str(row_id).isdecimal() or int(row_id) != index:
            raise ProbabilityBindingError("frozen row_id does not match its row position")
        row_id = int(row_id)
    else:
        row_id = None
    market = row.get("market")
    return {"row_id": row_id, "quote_id": row.get("quote_id") or None,
            "market": market, "family": market_family(market), "pick": row.get("pick"),
            "player": row.get("player") or None, "line": fnum(row.get("line")), "price": price,
            "model_p": fnum(row.get("model_p")), "market_p": fnum(row.get("market_p")),
            "blend_p": fnum(row.get("blend_p"))}


def bind_frozen_probabilities(run, labels):
    """Reject scored rows whose settlement values differ from the frozen picks."""
    from common import read_csv
    from freeze import verify
    run_dir = run.get("run_dir")
    if not run_dir:
        raise ProbabilityBindingError("frozen run directory required")
    if verify(run_dir):
        raise ProbabilityBindingError("frozen run failed verification")
    settlement = run["settlement"]
    for label in labels:
        rows = read_csv(os.path.join(run_dir, label, "picks_nfl.csv"))
        for graded in settlement["graded"]:
            if graded["pick_set"] != label:
                continue
            index = graded.get("row")
            if type(index) is not int or not 0 <= index < len(rows):
                raise ProbabilityBindingError("settlement row is outside the frozen picks")
            expected = _expected(rows[index], index)
            for key, wanted in expected.items():
                if not _same(graded.get(key), wanted):
                    raise ProbabilityBindingError(
                        f"{label} row {index} {key} does not match frozen prediction")


def compare(runs, left, right):
    if left == right:
        raise ValueError("choose distinct pick sets")
    counts = dict(matched=0, unmatched=0, excluded_runs=0, missing_identity=0,
                  push_or_ng=0)
    states = {label: dict(selected=0, unselected=0, unknown=0) for label in (left, right)}
    losses = {field: [] for field in FIELDS}
    seen_runs = set()
    for run in runs:
        m, s = run["manifest"], run.get("settlement")
        if m["run_id"] in seen_runs:
            raise ValueError("duplicate run")
        seen_runs.add(m["run_id"])
        if (run.get("quarantined") or not s or s.get("quarantined")
                or s.get("run_integrity_ok") is not True):
            counts["excluded_runs"] += 1
            continue
        if s.get("run_id") != m["run_id"] or s.get("game") != m["game"]:
            raise ValueError("settlement identity mismatch")
        bind_frozen_probabilities(run, (left, right))
        indexed = {left: {}, right: {}}
        for row in s["graded"]:
            label = row["pick_set"]
            if label not in indexed:
                continue
            if row.get("approved_stake_u") != 0:
                raise ValueError("missing or nonzero approved stake")
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
            if any(x.get(k) != y.get(k) for k in IDENTITY):
                raise ValueError("conflicting quote contract")
            if x["result"] != y["result"]:
                raise ValueError("conflicting settlement results")
            counts["matched"] += 1
            if x["result"] not in ("W", "L"):
                counts["push_or_ng"] += 1
                continue
            actual = int(x["result"] == "W")
            for field in FIELDS:
                px, py = probability(x.get(field)), probability(y.get(field))
                if px is not None and py is not None:
                    losses[field].append(((px - actual) ** 2, (py - actual) ** 2))
    scores = {}
    for field, values in losses.items():
        n = len(values)
        scores[field] = dict(n=n, missing_or_invalid=counts["matched"] - counts["push_or_ng"] - n,
            left=sum(v[0] for v in values) / n if n else None,
            right=sum(v[1] for v in values) / n if n else None)
    return dict(left=left, right=right, counts=counts, selection=states, scores=scores,
                probabilities="reconciled_to_frozen_picks")


def render(report):
    lines = ["# NFL paired ledger comparison", "",
        "Research only. Approved stake 0. No real betting performance or promotion claim.",
        "Scored probabilities are reconciled to the original frozen picks before use.",
        "A settlement whose probability or identity differs is rejected, not scored.",
        "Within-run quote matching only; row_id is local to each pick set, not a cross-model key.",
        "Brier uses matched W/L rows. Pushes and NG are excluded; lower is better.",
        "Counts are quote rows, not independent games. Repeated event captures may recur.",
        "Integrity is not source authentication. No confidence intervals or CLV.", "",
        f"Left: {report['left']} | Right: {report['right']}",
        f"Coverage: {report['counts']}", f"Selection states: {report['selection']}", "",
        "| Field | Paired n | Missing/invalid | Left Brier | Right Brier | Left minus right |",
        "|---|---:|---:|---:|---:|---:|"]
    for field, s in report["scores"].items():
        if s["n"]:
            lines.append(f"| {field} | {s['n']} | {s['missing_or_invalid']} | {s['left']:.6f} | {s['right']:.6f} | {s['left']-s['right']:+.6f} |")
        else:
            lines.append(f"| {field} | 0 | {s['missing_or_invalid']} | N/A | N/A | N/A |")
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
    a = ap.parse_args()
    runs = load_week(a.date_from, a.date_to, a.runs_dir, a.settle_dir)
    for run in runs:
        run["run_dir"] = os.path.join(a.runs_dir, run["manifest"]["run_id"])
        if verify(run["run_dir"]):
            run["quarantined"] = True
    print(render(compare(runs, a.left, a.right)), end="")


if __name__ == "__main__":
    main()
