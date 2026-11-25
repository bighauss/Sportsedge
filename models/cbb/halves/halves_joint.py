"""Joint (margin, total) and H1–H2 dependence for CBB halves (PAPER/0u, NON_COUNTED).

The univariate IntegerPMFs in ``halves_model`` are left unchanged. This module layers a
copula on those marginals so a game can be simulated consistently (margin with total,
first half with second half) and so joint event probabilities are not the independence
product.

Copula kinds, chosen on rolling-origin dev folds 2021–2025:
  * ``gaussian``: one correlation for (z_margin, z_total) per period; a 4x4 correlation
    for (H1 margin, H1 total, H2-pregame margin, H2-pregame total).
  * ``empirical``: a copula-density grid on the unit square (period margin/total only).

Season 2026 was not used to choose the kind or to fit the correlations. Any 2026 joint
metric is a secondary re-use of that already-scored window and is labelled as such.

Stdlib only; no network.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

try:
    from . import halves_model as HM
except ImportError:  # pragma: no cover
    import halves_model as HM

HERE = Path(__file__).resolve().parent
DEFAULT_JOINT = HERE / "coefficients_halves_joint_v1.json"
LABEL = "PAPER_0U"
COUNTING = "NON_COUNTED"

# 16-point Gauss–Legendre nodes and weights on [-1, 1]
_GL16_X = (
    -0.9894009349916499, -0.9445750230732326, -0.8656312023878318, -0.7554045774339321,
    -0.6178762444026438, -0.4580167776572274, -0.2816035507792589, -0.0950125098376374,
     0.0950125098376374,  0.2816035507792589,  0.4580167776572274,  0.6178762444026438,
     0.7554045774339321,  0.8656312023878318,  0.9445750230732326,  0.9894009349916499,
)
_GL16_W = (
    0.0271524594117541, 0.0622535239386479, 0.0951585116824928, 0.1246289712555339,
    0.1495959888165767, 0.1691565193950025, 0.1826034150449236, 0.1894506104550685,
    0.1894506104550685, 0.1826034150449236, 0.1691565193950025, 0.1495959888165767,
    0.1246289712555339, 0.0951585116824928, 0.0622535239386479, 0.0271524594117541,
)


def load_joint(path=None):
    p = Path(path) if path else DEFAULT_JOINT
    raw = p.read_bytes()
    doc = json.loads(raw)
    if doc.get("label") != LABEL or doc.get("counting") != COUNTING:
        raise HM.HalvesHold("JOINT_COEFFICIENTS_LABEL_INVALID")
    doc["_sha256"] = hashlib.sha256(raw).hexdigest()
    return doc


def _norm_ppf(p):
    p = min(max(float(p), 1e-12), 1.0 - 1e-12)
    target = 2.0 * p - 1.0
    lo, hi = -20.0, 20.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if math.erf(mid / math.sqrt(2.0)) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def bivariate_normal_cdf(h, k, rho):
    """P(X<=h, Y<=k) for standard bivariate normal with correlation rho.

    Φ2(h,k,ρ) = Φ(h)Φ(k) + (1/(2π)) ∫_0^ρ (1-t²)^(-1/2)
                exp(-(h²+k²-2hkt)/(2(1-t²))) dt
    """
    rho = min(max(float(rho), -0.999), 0.999)
    if h < -12 or k < -12:
        return 0.0
    ph, pk = HM._norm_cdf(h), HM._norm_cdf(k)
    if abs(rho) < 1e-12:
        return ph * pk
    # integrate t from 0 to rho
    a, b = 0.0, rho
    acc = 0.0
    for x, w in zip(_GL16_X, _GL16_W):
        t = 0.5 * (b - a) * x + 0.5 * (b + a)
        one = 1.0 - t * t
        if one <= 1e-16:
            continue
        expo = -((h * h + k * k - 2.0 * h * k * t) / (2.0 * one))
        acc += w * math.exp(max(expo, -700.0)) / math.sqrt(one)
    return min(max(ph * pk + 0.5 * (b - a) * acc / (2.0 * math.pi), 0.0), 1.0)


def gaussian_copula_cdf(u, v, rho):
    return bivariate_normal_cdf(_norm_ppf(u), _norm_ppf(v), rho)


def empirical_copula_cdf(u, v, grid):
    """Bilinear CDF on a uniform [0,1]x[0,1] grid of cumulative values (including 0 and 1)."""
    u = min(max(float(u), 0.0), 1.0)
    v = min(max(float(v), 0.0), 1.0)
    n = len(grid) - 1
    x, y = u * n, v * n
    i, j = min(int(x), n - 1), min(int(y), n - 1)
    sx, sy = x - i, y - j
    a, b = grid[i][j], grid[i][j + 1]
    c, d = grid[i + 1][j], grid[i + 1][j + 1]
    return (1 - sx) * (1 - sy) * a + (1 - sx) * sy * b + sx * (1 - sy) * c + sx * sy * d


def _cdf_at(pmf, k):
    """P(Y <= k) for integer k."""
    if k < pmf.lo:
        return 0.0
    if k >= pmf.hi:
        return 1.0
    return sum(pmf.p[: k - pmf.lo + 1])


def copula_cdf(kind, u, v, spec):
    if kind == "gaussian":
        return gaussian_copula_cdf(u, v, spec["rho"])
    if kind == "empirical":
        return empirical_copula_cdf(u, v, spec["cdf_grid"])
    if kind == "independent":
        return u * v
    raise HM.HalvesHold("COPULA_KIND_INVALID")


def joint_cell(pmf_m, pmf_t, m, t, kind, spec):
    """P(M=m, T=t) from the copula of the two integer marginals."""
    um, um1 = _cdf_at(pmf_m, m), _cdf_at(pmf_m, m - 1)
    ut, ut1 = _cdf_at(pmf_t, t), _cdf_at(pmf_t, t - 1)
    p = (copula_cdf(kind, um, ut, spec) - copula_cdf(kind, um1, ut, spec)
         - copula_cdf(kind, um, ut1, spec) + copula_cdf(kind, um1, ut1, spec))
    return max(0.0, p)


def attach_joint(dist, joint_doc, period=None):
    """Return a copy of a ``project_period`` result with joint copula metadata attached."""
    period = period or dist["period"]
    if period not in joint_doc["periods"]:
        raise HM.HalvesHold("JOINT_PERIOD_MISSING")
    spec = joint_doc["periods"][period]
    out = dict(dist)
    out["joint"] = {"kind": spec["kind"], "spec": spec, "label": LABEL, "counting": COUNTING,
                    "joint_sha256": joint_doc.get("_sha256"),
                    "secondary_reuse_note": joint_doc.get("secondary_reuse_note")}
    return out


def project_period_joint(*args, joint=None, **kwargs):
    """``project_period`` plus the fitted copula for that period."""
    dist = HM.project_period(*args, **kwargs)
    return attach_joint(dist, joint or load_joint(), dist["period"])


def sample_margin_total(dist, rng):
    """One (margin, total, home, away) draw from the attached joint, or independence."""
    pm, pt = dist["pmf"]["margin"], dist["pmf"]["total"]
    joint = dist.get("joint")
    u, v = rng.random(), rng.random()
    if joint and joint["kind"] != "independent":
        # Conditional Gaussian / empirical: v' = C^{-1}(v | u)
        v = _cond_invert(u, v, joint["kind"], joint["spec"])
    m = _ppf_pmf(pm, u)
    t = _ppf_pmf(pt, v)
    # parity: home and away points are integers iff m and t have the same parity
    if (m + t) % 2:
        t += 1 if rng.random() < 0.5 else -1
    return m, t, (t + m) // 2, (t - m) // 2


def _ppf_pmf(pmf, u):
    acc = 0.0
    for k, p in zip(range(pmf.lo, pmf.hi + 1), pmf.p):
        acc += p
        if u <= acc:
            return k
    return pmf.hi


def _cond_invert(u, w, kind, spec, lo=0.0, hi=1.0):
    """Solve C(u, v) = w * C(u, 1) + (1-w)*C(u,0)  i.e. the conditional CDF inverse."""
    target = w * max(copula_cdf(kind, u, 1.0, spec) - copula_cdf(kind, u, 0.0, spec), 1e-15)
    base = copula_cdf(kind, u, 0.0, spec)
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if copula_cdf(kind, u, mid, spec) - base < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def cholesky(corr):
    """Cholesky of a small positive-definite matrix; shrinks toward I if needed."""
    n = len(corr)
    a = [row[:] for row in corr]
    for _ in range(8):
        try:
            L = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for j in range(i + 1):
                    s = a[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
                    if i == j:
                        if s <= 1e-12:
                            raise ValueError
                        L[i][j] = math.sqrt(s)
                    else:
                        L[i][j] = s / L[j][j]
            return L
        except ValueError:
            for i in range(n):
                for j in range(n):
                    a[i][j] = 0.9 * a[i][j] + (0.1 if i == j else 0.0)
    raise HM.HalvesHold("CORR_NOT_PD")


def _box_muller(rng, n):
    out = []
    while len(out) < n:
        u, v = rng.random(), rng.random()
        u = min(max(u, 1e-12), 1 - 1e-12)
        r = math.sqrt(-2.0 * math.log(u))
        out.append(r * math.cos(2 * math.pi * v))
        out.append(r * math.sin(2 * math.pi * v))
    return out[:n]


def sample_correlated_uniforms(corr, rng):
    L = cholesky(corr)
    z = _box_muller(rng, len(corr))
    x = [sum(L[i][j] * z[j] for j in range(i + 1)) for i in range(len(corr))]
    return [HM._norm_cdf(v) for v in x]


def sample_h1_h2(h1, h2, joint_doc, rng):
    """Pregame joint draw of first and second half (OT-included H2 by default).

    Uses the 4x4 Gaussian copula in ``joint_doc['h1_h2']``. Halftime-adjusted H2 should
    not be mixed into this sampler (use the HT period's own residual copula instead).
    """
    if h1["period"] != "H1" or h2["period"] not in ("H2", "H2REG"):
        raise HM.HalvesHold("H1H2_PERIOD_MISMATCH")
    spec = joint_doc["h1_h2"]
    if spec["kind"] != "gaussian":
        raise HM.HalvesHold("H1H2_KIND_UNSUPPORTED")
    u = sample_correlated_uniforms(spec["corr"], rng)
    m1 = _ppf_pmf(h1["pmf"]["margin"], u[0])
    t1 = _ppf_pmf(h1["pmf"]["total"], u[1])
    m2 = _ppf_pmf(h2["pmf"]["margin"], u[2])
    t2 = _ppf_pmf(h2["pmf"]["total"], u[3])
    def pair(m, t, r):
        if (m + t) % 2:
            t += 1 if r.random() < 0.5 else -1
        return m, t, (t + m) // 2, (t - m) // 2
    a = pair(m1, t1, rng)
    b = pair(m2, t2, rng)
    return {"H1": {"margin": a[0], "total": a[1], "home": a[2], "away": a[3]},
            h2["period"]: {"margin": b[0], "total": b[1], "home": b[2], "away": b[3]}}
