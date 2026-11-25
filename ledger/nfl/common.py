"""Shared helpers. Reuses ledger/prediction_log.py (profit + no-vig) instead of duplicating."""
import csv, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.dirname(HERE)
if LEDGER not in sys.path:
    sys.path.insert(0, LEDGER)
from prediction_log import _profit, novig_two_way  # noqa: E402,F401

RUNS_DIR = os.path.join(HERE, "runs")
SETTLE_DIR = os.path.join(HERE, "settlements")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def read_json(path):
    with open(path) as f:
        return json.load(f)


def price_of(row):
    for k in ("price", "price_american", "odds", "american"):
        if row.get(k) not in (None, ""):
            return float(row[k])
    raise ValueError(f"row has no price: {row}")


def fnum(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "y", "held")


def is_held(v):
    """run_nfl writes the hold REASON (empty = not held); older rows use 1/true/held."""
    t = str(v if v is not None else "").strip().lower()
    return t not in ("", "0", "false", "no", "n", "none")


def market_family(market):
    """spread|total|ml for full game; 'periods' for 1H_/1Q_/2H_ etc; 'prop:<stat>' for props."""
    m = (market or "").strip().lower()
    if m.startswith("prop"):
        stat = m.split("_", 1)[1] if "_" in m else m.split(":", 1)[-1]
        return "prop:" + stat
    if m in ("home_tt", "away_tt"):
        return "team_total"
    if "_" in m:
        return "periods"
    return {"moneyline": "ml", "h2h": "ml", "spreads": "spread", "totals": "total"}.get(m, m)


# ---- engine/run_nfl.py (PR #472) output adapter ----------------------------------------
# run_nfl rows carry no market/line columns: market comes from bet_type ("<MARKET>|<side>|<sgp>")
# and line/side/team from the v5 pick label. Mapping (v5 market -> ledger market):
#   SPREAD/TOTAL/ML -> spread/total/ml; <P>_SPREAD etc -> <p>_spread (P in 1Q..4Q,1H,2H);
#   HOME_TT/AWAY_TT (+ periods) -> [<p>_]home_tt / away_tt; player stat props -> prop_<stat>;
#   ATD/TD2 -> prop_atd / prop_td2 (yes/no, line 0.5 / 1.5).
# Unsupported (graded NG with reason): FTD, OT, BTTS, REG_*, HOME_BY_*/AWAY_BY_*, SGP.
UNSUPPORTED = ("FTD", "OT", "BTTS", "REG_HOME", "REG_AWAY", "REG_DRAW", "SGP")
PERIOD_PREFIXES = ("1Q", "2Q", "3Q", "4Q", "1H", "2H")


def normalize_row(row):
    """Return a copy of row with ledger fields (market, pick, line, team) filled.
    Rows that already carry `market` are returned unchanged."""
    if row.get("market") or not row.get("bet_type"):
        return dict(row)
    r = dict(row)
    parts = row["bet_type"].split("|")
    vm, side = parts[0].upper(), int(parts[1]) if len(parts) > 1 and parts[1] else 0
    label = (row.get("pick") or "").split()
    pre, base = "", vm
    if "_" in vm and vm.split("_", 1)[0] in PERIOD_PREFIXES:
        pre, base = vm.split("_", 1)
        if label and label[0].upper() == pre:
            label = label[1:]
    lp = (pre.lower() + "_") if pre else ""
    r["v5_market"] = vm
    if base in UNSUPPORTED or base.startswith(("HOME_BY_", "AWAY_BY_")):
        r["market"] = "unsupported_" + vm.lower()
        return r
    if row.get("player"):
        if base in ("ATD", "TD2"):
            r["market"] = "prop_" + base.lower()
            r["pick"] = "no" if side == 1 else "yes"
            r["line"] = 0.5 if base == "ATD" else 1.5
            return r
        r["market"] = "prop_" + base.lower()
        try:
            i = [t.lower() for t in label].index("over" if side == 0 else "under")
            r["pick"], r["line"] = label[i].lower(), float(label[i + 1])
        except (ValueError, IndexError):
            r["market"] = "unparsed_" + vm.lower()
        return r
    if base == "ML":
        r["market"], r["pick"] = lp + "ml", label[0] if label else ""
        return r
    if base == "SPREAD":
        r["market"], r["pick"], r["line"] = lp + "spread", label[0], float(label[-1])
        return r
    if base == "TOTAL":
        r["market"], r["pick"], r["line"] = lp + "total", label[-2].lower(), float(label[-1])
        return r
    if base in ("HOME_TT", "AWAY_TT"):
        r["market"] = lp + base.lower()
        r["pick"], r["line"] = label[-2].lower(), float(label[-1])
        return r
    r["market"] = "unparsed_" + vm.lower()
    return r


def projection_numbers(proj):
    """Scorecard projection keys from either the ledger layout or the CIN@WAS package
    layout {"game": [game, away_proj, home_proj, model_total, market_total, market_home_margin]}."""
    if "proj_margin" in proj:
        return proj
    g = proj.get("game")
    if isinstance(g, list) and len(g) >= 6:
        _, ap, hp, t, mt, mm = g[:6]
        return {"proj_margin": hp - ap, "proj_total": t, "market_total": mt, "market_margin": mm}
    return {}
