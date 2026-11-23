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


def market_family(market):
    """spread|total|ml for full game; 'periods' for 1H_/1Q_/2H_ etc; 'prop:<stat>' for props."""
    m = (market or "").strip().lower()
    if m.startswith("prop"):
        stat = m.split("_", 1)[1] if "_" in m else m.split(":", 1)[-1]
        return "prop:" + stat
    if "_" in m:
        return "periods"
    return {"moneyline": "ml", "h2h": "ml", "spreads": "spread", "totals": "total"}.get(m, m)
