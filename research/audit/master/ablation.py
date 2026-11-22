"""Feature-group ablation on unseen data: "take out one group of variables at a time,
rerun the backtest, compare on data the model hasn't seen".

Walk-forward: rows sorted by time, model refit on everything before each test fold.
For each group, compares holdout Brier / log loss of FULL vs WITHOUT-GROUP with a
paired bootstrap CI on the difference. A group whose removal doesn't hurt is a
SIMPLIFY_CANDIDATE. Read-only recommendation; never edits production features.

Default model: stdlib L2 logistic regression. Pass fit_fn(train, features) ->
predict(row)->prob to test any model (e.g. a wrapper around an engine challenger).
"""
from __future__ import annotations

import math
import random
from typing import Callable, Sequence

from . import stats


def _logit_fit(train, features, l2=1.0, iters=300, lr=0.1):
    if not features:
        p = sum(r["y"] for r in train) / len(train)
        return lambda r: min(max(p, 1e-6), 1 - 1e-6)
    # standardize on train only (no leakage)
    mu = {f: sum(float(r[f]) for r in train) / len(train) for f in features}
    sd = {f: (sum((float(r[f]) - mu[f]) ** 2 for r in train) / len(train)) ** .5 or 1.0 for f in features}
    X = [[(float(r[f]) - mu[f]) / sd[f] for f in features] for r in train]
    y = [r["y"] for r in train]
    w, b, n = [0.0] * len(features), 0.0, len(train)
    for _ in range(iters):
        gw, gb = [0.0] * len(features), 0.0
        for xi, yi in zip(X, y):
            z = b + sum(a * c for a, c in zip(w, xi))
            q = 1 / (1 + math.exp(-max(-30, min(30, z))))
            for j, c in enumerate(xi):
                gw[j] += (q - yi) * c
            gb += q - yi
        w = [wj - lr * (gw[j] / n + l2 * wj / n) for j, wj in enumerate(w)]
        b -= lr * gb / n

    def predict(r):
        z = b + sum(wj * (float(r[f]) - mu[f]) / sd[f] for wj, f in zip(w, features))
        return 1 / (1 + math.exp(-max(-30, min(30, z))))
    return predict


def walk_forward_preds(rows, features, fit_fn=None, folds=5, min_train=0.4, time_key="kickoff_ts"):
    fit_fn = fit_fn or _logit_fit
    rs = sorted(rows, key=lambda r: str(r.get(time_key, "")))
    n = len(rs)
    start = int(n * min_train)
    step = max(1, (n - start) // folds)
    preds = []
    for f0 in range(start, n, step):
        train, test = rs[:f0], rs[f0:f0 + step]
        if not test:
            break
        model = fit_fn(train, list(features))
        preds += [(r, model(r)) for r in test]
    return preds


def ablation(rows: Sequence[dict], groups: dict[str, Sequence[str]], fit_fn: Callable | None = None,
             folds: int = 5, iters: int = 2000, seed: int = 1, tol: float = 0.0) -> dict:
    """rows need 'y' (1/0 outcome) + feature columns + time key. groups: {name: [cols]}."""
    all_f = [f for g in groups.values() for f in g]
    full = walk_forward_preds(rows, all_f, fit_fn, folds)
    base = {id(r): p for r, p in full}
    ys = {id(r): r["y"] for r, _ in full}

    def score(preds):
        pp = [p for _, p in preds]
        oo = [r["y"] for r, _ in preds]
        return {"brier": stats.brier(pp, oo), "log_loss": stats.log_loss(pp, oo)}
    out = {"n_holdout": len(full), "full": score(full), "groups": []}
    rng = random.Random(seed)
    for name, cols in groups.items():
        reduced = walk_forward_preds(rows, [f for f in all_f if f not in cols], fit_fn, folds)
        red = {id(r): p for r, p in reduced}
        keys = [k for k in base if k in red]
        # per-row Brier difference: reduced - full (positive = removing the group hurts)
        d = [(red[k] - ys[k]) ** 2 - (base[k] - ys[k]) ** 2 for k in keys]
        mean = sum(d) / len(d)
        boots = sorted(sum(d[rng.randrange(len(d))] for _ in d) / len(d) for _ in range(iters // 10))
        ci = (boots[int(.025 * len(boots))], boots[int(.975 * len(boots)) - 1])
        verdict = ("KEEP_HELPS" if ci[0] > tol else
                   "SIMPLIFY_CANDIDATE" if mean <= tol or ci[0] <= 0 <= ci[1] else "REVIEW")
        if mean < 0 and ci[1] < 0:
            verdict = "SIMPLIFY_CANDIDATE_HURTS_HOLDOUT"
        out["groups"].append({"group": name, "columns": list(cols), "without": score(reduced),
                              "brier_change_if_removed": mean, "ci95": ci, "verdict": verdict})
    out["groups"].sort(key=lambda g: g["brier_change_if_removed"])
    out["note"] = ("Positive change = removing the group makes holdout worse (keep it). "
                   "SIMPLIFY_CANDIDATE groups add complexity without measurable holdout gain. "
                   "Recommendation only; confirm on a fresh forward window before removing.")
    return out
