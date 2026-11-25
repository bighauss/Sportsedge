"""Count distributions for CBB player props (stdlib only, PAPER/0u research).

Negative binomial with var = mu + alpha*mu^2 (alpha<=0 -> explicit Poisson
limit), discrete CRPS, correlated combo marginals (moment-matched NB and a
Gaussian copula Monte Carlo over NB marginals), and push-aware settlement
probabilities. No caps, no sportsbook quotes here.
"""
import math
import random
from bisect import bisect_left

TAIL = 1e-12
KMAX = 400


def nb_pmf(mu, alpha, kmax=None):
    """PMF list over 0..K for mean mu and NB2 dispersion alpha (alpha<=0: Poisson)."""
    if not (isinstance(mu, (int, float)) and math.isfinite(mu) and mu >= 0):
        raise ValueError("INVALID_MEAN")
    if not (isinstance(alpha, (int, float)) and math.isfinite(alpha)):
        raise ValueError("INVALID_DISPERSION")
    if mu == 0:
        return [1.0]
    out = []
    if alpha <= 1e-9:
        logp = -mu
        step = lambda j: math.log(mu) - math.log(j)
    else:
        r = 1.0 / alpha
        logp = r * -math.log1p(mu / r)
        logq = math.log(mu) - math.log(r + mu)
        step = lambda j: math.log(r + j - 1) - math.log(j) + logq
    total = 0.0
    k = 0
    limit = kmax if kmax is not None else KMAX
    while True:
        p = math.exp(logp)
        out.append(p)
        total += p
        if k >= limit or (k > mu and 1.0 - total < TAIL):
            break
        k += 1
        logp += step(k)
    s = math.fsum(out)
    return [p / s for p in out] if kmax is None else out


def cdf_list(pmf):
    acc, out = 0.0, []
    for p in pmf:
        acc += p
        out.append(min(1.0, acc))
    return out


def crps_discrete(pmf, y):
    """CRPS for an integer outcome: sum_k (F(k) - 1{y<=k})^2 over the support."""
    if type(y) is not int or y < 0:
        raise ValueError("INVALID_OUTCOME")
    F = cdf_list(pmf)
    top = max(len(F), y + 1)
    s = 0.0
    for k in range(top):
        f = F[k] if k < len(F) else 1.0
        s += (f - (1.0 if y <= k else 0.0)) ** 2
    return s


def prob_at_least(pmf, n):
    if n <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - math.fsum(pmf[:n])))


def settle_probs(pmf, kind, line):
    """(p_win, p_push, p_lose) for one side. kind: AT_LEAST (integer N), OVER, UNDER."""
    if kind == "AT_LEAST":
        if float(line) != int(line) or line < 0:
            raise ValueError("AT_LEAST_REQUIRES_NONNEGATIVE_INTEGER")
        w = prob_at_least(pmf, int(line))
        return w, 0.0, 1.0 - w
    if kind not in ("OVER", "UNDER"):
        raise ValueError("UNKNOWN_SETTLEMENT_KIND")
    if not math.isfinite(line) or line < 0 or (line * 2) % 1:
        raise ValueError("LINE_MUST_BE_INTEGER_OR_HALF")
    if float(line).is_integer():
        n = int(line)
        push = pmf[n] if n < len(pmf) else 0.0
        over = max(0.0, 1.0 - math.fsum(pmf[: n + 1]))
    else:
        push = 0.0
        over = max(0.0, 1.0 - math.fsum(pmf[: math.floor(line) + 1]))
    under = max(0.0, 1.0 - over - push)
    return (over, push, under) if kind == "OVER" else (under, push, over)


def moment_alpha(mean, var):
    """NB2 alpha matching (mean, var); 0.0 (Poisson limit) when not overdispersed."""
    if mean <= 0:
        return 0.0
    return max(0.0, (var - mean) / (mean * mean))


def combo_moments(mus, alphas, rho):
    """Mean/var of a sum of correlated NB counts; rho[(i,j)] correlation of components."""
    v = [m + a * m * m for m, a in zip(mus, alphas)]
    mean = math.fsum(mus)
    var = math.fsum(v)
    for i in range(len(mus)):
        for j in range(i + 1, len(mus)):
            var += 2.0 * rho.get((i, j), rho.get((j, i), 0.0)) * math.sqrt(v[i] * v[j])
    return mean, max(var, 1e-9)


def combo_pmf_moment(mus, alphas, rho):
    m, v = combo_moments(mus, alphas, rho)
    return nb_pmf(m, moment_alpha(m, v))


def _cholesky(R):
    n = len(R)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = R[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                if s <= 0:
                    raise ValueError("CORRELATION_NOT_POSITIVE_DEFINITE")
                L[i][j] = math.sqrt(s)
            else:
                L[i][j] = s / L[j][j]
    return L


def _phi(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def combo_pmf_copula(mus, alphas, R, *, draws=20000, seed=519):
    """Gaussian-copula joint of NB marginals; returns PMF of the component sum.

    Deterministic for a fixed seed. R is a full correlation matrix (list of lists)
    on the latent normal scale.
    """
    L = _cholesky(R)
    cdfs = [cdf_list(nb_pmf(m, a)) for m, a in zip(mus, alphas)]
    rng = random.Random(seed)
    counts = {}
    n = len(mus)
    for _ in range(draws):
        z = [rng.gauss(0.0, 1.0) for _ in range(n)]
        total = 0
        for i in range(n):
            x = sum(L[i][k] * z[k] for k in range(i + 1))
            u = _phi(x)
            F = cdfs[i]
            k = bisect_left(F, u)
            total += min(k, len(F) - 1)
        counts[total] = counts.get(total, 0) + 1
    top = max(counts)
    return [counts.get(k, 0) / draws for k in range(top + 1)]


def american_to_decimal(price):
    p = float(price)
    if not math.isfinite(p) or -100 < p < 100:
        raise ValueError("INVALID_AMERICAN_PRICE")
    return 1.0 + (p / 100.0 if p > 0 else 100.0 / -p)


def fair_american(p):
    if not 0 < p < 1:
        return None
    return -100.0 * p / (1 - p) if p >= 0.5 else 100.0 * (1 - p) / p


def expected_value(p_win, p_push, p_lose, price):
    """EV per 1u stake, push refunds stake. Deliberately uncapped."""
    d = american_to_decimal(price)
    return p_win * (d - 1.0) - p_lose
