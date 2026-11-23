"""Weekly NFL scorecard (markdown, phone-readable). No CLV (owner removed it).

Usage:
  python3 ledger/nfl/scorecard.py --from 2026-11-19 --to 2026-11-25 [--pick-set challenger] [--out wk12.md]

Reads frozen runs (ledger/nfl/runs/*) captured in [from, to] and the LATEST settlement record
for each. Model vs market: uses projection/frozen.json keys
  proj_margin, proj_total (model; margin = home - away) and market_margin, market_total.
"""
import argparse, glob, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RUNS_DIR, SETTLE_DIR, fnum, read_json  # noqa: E402

EV_BUCKETS = [(-9.0, 0.0, "<0%"), (0.0, 0.02, "0-2%"), (0.02, 0.05, "2-5%"),
              (0.05, 0.10, "5-10%"), (0.10, 9.0, "10%+")]


def load_week(date_from, date_to, runs_dir=RUNS_DIR, settle_dir=SETTLE_DIR):
    out = []
    for mpath in sorted(glob.glob(os.path.join(runs_dir, "*", "manifest.json"))):
        m = read_json(mpath)
        d = m["capture_utc"][:10]
        if not (date_from <= d <= date_to):
            continue
        rd = os.path.dirname(mpath)
        proj = read_json(os.path.join(rd, "projection", "frozen.json"))
        sp = os.path.join(settle_dir, m["run_id"] + ".json")
        settle = read_json(sp)[-1] if os.path.exists(sp) else None
        out.append({"manifest": m, "projection": proj, "settlement": settle})
    return out


def _rec(rows):
    w = sum(r["result"] == "W" for r in rows)
    l = sum(r["result"] == "L" for r in rows)
    p = sum(r["result"] == "P" for r in rows)
    u = sum(r["units"] or 0 for r in rows)
    n = w + l + p
    roi = u / n if n else 0.0
    return f"{w}-{l}-{p} | {u:+.2f}u | ROI {roi:+.1%}"


def build(runs, pick_set=None, title="NFL weekly scorecard"):
    L = [f"# {title}", ""]
    settled = [r for r in runs if r["settlement"]]
    L.append(f"Runs frozen: {len(runs)} | settled: {len(settled)} | 1u flat at frozen price")
    L.append("")
    # model vs market
    em, ek, et, etk = [], [], [], []
    for r in settled:
        f, pj = r["settlement"]["finals"], r["projection"]
        am = float(f["home_score"]) - float(f["away_score"])
        at = float(f["home_score"]) + float(f["away_score"])
        for key, mk, actual, a, b in (("proj_margin", "market_margin", am, em, ek),
                                      ("proj_total", "market_total", at, et, etk)):
            pv, mv = fnum(pj.get(key)), fnum(pj.get(mk))
            if pv is not None and mv is not None:
                a.append(abs(pv - actual))
                b.append(abs(mv - actual))
    L.append("## Model vs market (MAE, finals only)")
    if em or et:
        if em:
            L.append(f"- Margin: model {sum(em)/len(em):.2f} vs market {sum(ek)/len(ek):.2f} (n={len(em)})")
        if et:
            L.append(f"- Total: model {sum(et)/len(et):.2f} vs market {sum(etk)/len(etk):.2f} (n={len(et)})")
    else:
        L.append("- no finals with projection + market numbers yet")
    L.append("")
    rows = [g for r in settled for g in r["settlement"]["graded"]
            if g["result"] in ("W", "L", "P") and (pick_set is None or g["pick_set"] == pick_set)]
    ng = sum(1 for r in settled for g in r["settlement"]["graded"]
             if g["result"] == "NG" and (pick_set is None or g["pick_set"] == pick_set))
    L.append("## Overall")
    L.append(f"- All: {_rec(rows)}")
    L.append(f"- Unheld: {_rec([g for g in rows if not g['held']])}")
    L.append(f"- Held: {_rec([g for g in rows if g['held']])}")
    if ng:
        L.append(f"- Not gradable (missing score/stat): {ng}")
    L.append("")
    L.append("## By market")
    order = ["spread", "total", "ml", "periods"]
    fams = sorted({g["family"] for g in rows}, key=lambda f: (order.index(f) if f in order else 9, f))
    for f in fams:
        L.append(f"- {f}: {_rec([g for g in rows if g['family'] == f])}")
    L.append("")
    L.append("## By blended EV")
    for lo, hi, name in EV_BUCKETS:
        b = [g for g in rows if g["ev"] is not None and lo <= g["ev"] < hi]
        if b:
            L.append(f"- {name}: {_rec(b)}")
    nb = [g for g in rows if g["ev"] is None]
    if nb:
        L.append(f"- no EV: {_rec(nb)}")
    if len(rows) < 50:
        L.append("")
        L.append(f"_Small sample (n={len(rows)}): read as results, not proof._")
    L.append("")
    L.append("## Games")
    for r in runs:
        m, s = r["manifest"], r["settlement"]
        if s:
            f = s["finals"]
            gr = [g for g in s["graded"] if g["result"] in ("W", "L", "P")
                  and (pick_set is None or g["pick_set"] == pick_set)]
            L.append(f"- {m['game']}: {f['away']} {f['away_score']} - {f['home']} {f['home_score']} | {_rec(gr)}")
        else:
            L.append(f"- {m['game']}: not settled")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="dfrom", required=True)
    ap.add_argument("--to", dest="dto", required=True)
    ap.add_argument("--pick-set")
    ap.add_argument("--out")
    ap.add_argument("--runs-dir", default=RUNS_DIR)
    ap.add_argument("--settle-dir", default=SETTLE_DIR)
    a = ap.parse_args(argv)
    md = build(load_week(a.dfrom, a.dto, a.runs_dir, a.settle_dir), a.pick_set,
               f"NFL scorecard {a.dfrom} to {a.dto}")
    if a.out:
        with open(a.out, "w") as f:
            f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
