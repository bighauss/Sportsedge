"""Market-implied probability engine. Research only; PAPER / 0u.
Quote identity checks are not source authentication.
"""
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import NormalDist

METHODS = ("multiplicative", "additive", "power", "shin")


def finite(x):
    if isinstance(x, bool):
        raise ValueError("boolean numeric input")
    x = float(x)
    if not math.isfinite(x):
        raise ValueError("nonfinite input")
    return x


def american_to_decimal(a):
    a = finite(a)
    if abs(a) < 100:
        raise ValueError("invalid American odds")
    return 1 + (a / 100 if a > 0 else 100 / -a)


def decimal_to_american(d):
    d = finite(d)
    if d <= 1:
        raise ValueError("decimal odds must exceed 1")
    return (d - 1)*100 if d >= 2 else -100/(d - 1)


def implied(d):
    decimal_to_american(d)
    return 1/float(d)


def overround(decs):
    return sum(map(implied, decs)) - 1


def _bisect(f, lo, hi, it=200):
    lo, hi = finite(lo), finite(hi)
    if lo >= hi or type(it) is not int or it < 1:
        raise ValueError("invalid root search")
    a, b = finite(f(lo)), finite(f(hi))
    if abs(a) <= 1e-12:
        return lo
    if abs(b) <= 1e-12:
        return hi
    if (a > 0) == (b > 0):
        raise ValueError("root not bracketed")
    for _ in range(it):
        mid = (lo + hi)/2
        v = finite(f(mid))
        if abs(v) <= 1e-12:
            return mid
        if (v > 0) == (a > 0):
            lo, a = mid, v
        else:
            hi = mid
    raise ValueError("root did not converge")


@dataclass
class FairResult:
    status: str
    method: str
    fair: object = None
    overround: object = None
    reason: str = ""


def devig(prices, method="power", fmt="american"):
    if method not in METHODS:
        raise ValueError("unknown method")
    if len(prices) < 2 or any(p is None for p in prices):
        return FairResult("NO_PRICE", method, reason="missing opposing price")
    try:
        if fmt not in ("american", "decimal"):
            raise ValueError("unknown odds format")
        ds = [american_to_decimal(p) if fmt == "american" else finite(p) for p in prices]
        q = [implied(d) for d in ds]
        s = sum(q)
        if s < .98:
            raise ValueError("negative overround; freshness not established by prices")
        if method == "multiplicative" or (method == "shin" and s <= 1):
            p = [x/s for x in q]
        elif method == "additive":
            p = [x-(s-1)/len(q) for x in q]
        elif method == "power":
            k = _bisect(lambda k: sum(x**k for x in q)-1, 1e-6, 50)
            p = [x**k for x in q]
        else:
            def probs(z):
                return [2*x*x/s/(math.sqrt(z*z+4*(1-z)*x*x/s)+z) for x in q]
            z = _bisect(lambda z: sum(probs(z))-1, 0, .999999)
            p = probs(z)
        if any(not math.isfinite(x) or not 0 < x < 1 for x in p) or abs(sum(p)-1) > 1e-9:
            raise ValueError("invalid or unconverged fair vector")
        return FairResult("OK", method, p, s-1)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as exc:
        return FairResult("INVALID", method, reason=str(exc))


def devig_all(prices, fmt="american"):
    return {m: devig(prices, m, fmt) for m in METHODS}


def _push(p_win, p_push):
    w, p = finite(p_win), finite(p_push)
    if not 0 <= w <= 1 or not 0 <= p <= 1 or w+p > 1:
        raise ValueError("invalid outcome probabilities")
    return w, p


def fair_win_given_push(p_win, p_push):
    w, p = _push(p_win, p_push)
    if w == 0 or p == 1:
        raise ValueError("unidentifiable fair odds")
    return (1-p)/w


def ev_per_unit(p_win, dec_offered, p_push=0):
    w, p = _push(p_win, p_push)
    implied(dec_offered)
    return w*(float(dec_offered)-1)-(1-w-p)


def utc(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class BookQuote:
    book: str
    prices: object
    weight: float = 1
    copies: object = None
    event_id: str = ""
    player_id: object = None
    market: str = ""
    period: str = ""
    line: object = None
    outcomes: tuple = ()
    capture_utc: str = ""
    start_utc: str = ""
    rules: str = ""
    sport: str = ""
    fmt: str = "american"


def consensus(quotes, method="power", exclude=("draftkings",), *, as_of=None, max_age_seconds=None):
    # DraftKings exclusion is mandatory, even if callers override exclude.
    ex = {b.strip().casefold() for b in exclude} | {"draftkings"}
    used = [q for q in quotes if q.book.strip().casefold() not in ex and q.copies is None]
    if not used:
        return FairResult("NO_PRICE", method, reason="no independent book")
    try:
        now, age = utc(as_of), finite(max_age_seconds)
        if age <= 0:
            raise ValueError("positive freshness limit required")
        contract, seen, fairs = None, set(), []
        for q in used:
            if not all(isinstance(x, str) and x.strip() for x in (q.book,q.event_id,q.market,q.period,q.rules,q.sport)):
                raise ValueError("incomplete quote identity")
            if q.player_id is not None and (not isinstance(q.player_id,str) or not q.player_id.strip()):
                raise ValueError("invalid player identity")
            if q.market.startswith("prop") and q.player_id is None:
                raise ValueError("prop requires player identity")
            line = finite(q.line) if q.line is not None else None
            labels = tuple(q.outcomes)
            if len(labels) != len(q.prices) or len(labels) < 2 or any(not isinstance(x,str) or not x.strip() for x in labels) or len(set(labels)) != len(labels):
                raise ValueError("invalid outcome vector")
            cap, start = utc(q.capture_utc), utc(q.start_utc)
            if not cap <= now < start or (now-cap).total_seconds() > age:
                raise ValueError("stale, future, or live quote")
            identity = (q.sport,q.event_id,q.player_id,q.market,q.period,line,labels,q.rules,start)
            if contract is not None and identity != contract:
                raise ValueError("incompatible quote contracts")
            contract = identity
            book = q.book.strip().casefold()
            if book in seen:
                raise ValueError("duplicate sportsbook")
            seen.add(book)
            w = finite(q.weight)
            if w <= 0:
                raise ValueError("positive sportsbook weight required")
            r = devig(q.prices, method, q.fmt)
            if r.status != "OK":
                return r
            fairs.append((w,r.fair))
        scale = max(w for w,_ in fairs)
        weights = [w/scale for w,_ in fairs]
        total = sum(weights)
        logs = [sum(w*math.log(f[i]) for w,(_,f) in zip(weights,fairs))/total for i in range(len(fairs[0][1]))]
        peak = max(logs)
        es = [math.exp(v-peak) for v in logs]
        return FairResult("OK", "consensus/"+method, [v/sum(es) for v in es], reason=f"books={len(fairs)}")
    except (ValueError,TypeError,AttributeError,OverflowError) as exc:
        return FairResult("INVALID", method, reason=str(exc))


def implied_team_scores(spread_home, total):
    margin, total = -finite(spread_home), finite(total)
    if total < abs(margin):
        raise ValueError("negative implied team score")
    return (total+margin)/2, (total-margin)/2


def implied_margin_sd(spread_home, p_home_fair_ml):
    mu, p = -finite(spread_home), finite(p_home_fair_ml)
    if mu == 0 or not 0 < p < 1:
        raise ValueError("unidentifiable margin dispersion")
    z = NormalDist().inv_cdf(p)
    if z == 0 or (mu > 0) != (z > 0):
        raise ValueError("spread and ML disagree")
    return mu/z
