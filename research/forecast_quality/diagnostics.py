"""Research-only binary forecast diagnostics; pushes are explicitly excluded."""
import math

def evaluate(rows):
    """Rows: unique id, probability, outcome (0, 1 or 'push'), baseline.
    Reject incomplete or duplicate rows; compare on the same denominator.
    """
    seen = set()
    bins = {}
    sums = [0.0] * 4
    n = pushes = 0
    for row in rows:
        key = row["id"]
        if not key or key in seen:
            raise ValueError("missing or duplicate id")
        seen.add(key)
        p, q, y = row["probability"], row["baseline"], row["outcome"]
        for v in (p, q):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1:
                raise ValueError("invalid probability")
        if y == "push":
            pushes += 1
            continue
        if type(y) is not int or y not in (0, 1):
            raise ValueError("invalid outcome")
        n += 1
        def loss(v):
            return -math.log(max(1e-15, v if y else 1-v))
        for i, v in enumerate(((p-y)**2, (q-y)**2, loss(p), loss(q))):
            sums[i] += v
        b = bins.setdefault(min(9, int(p*10)), [0, 0.0, 0])
        b[0] += 1
        b[1] += p
        b[2] += y
    return {"attempted": len(seen), "scored": n, "pushes": pushes,
            "brier": sums[0]/n if n else None,
            "baseline_brier": sums[1]/n if n else None,
            "log_loss": sums[2]/n if n else None,
            "baseline_log_loss": sums[3]/n if n else None,
            "bins": {k: {"n": b[0], "mean_p": b[1]/b[0], "actual": b[2]/b[0]} for k,b in sorted(bins.items())}}
