"""Build a v5 board.csv for NFL from team projections + a lines CSV (canonical step 2 of 3).
Usage: python engine/nfl_build_board.py projections.csv lines.csv board.csv
projections.csv: home,away,home_proj,away_proj            (one row per game)
lines.csv:       home,away,market,line,price_a,price_b[,player,team,proj,sgp,side]
  props: player filled and team = home or away exactly (v5 needs it), else the row is rejected.
Sanity checks (rejected rows are printed, never silently passed):
  - yardage prop lines < 1.5
  - two-sided prop pairs whose de-vigged probability is outside 3%..97% (implied mean implausibly far from line)
  - props whose team is not the game's home/away
Does not touch sportsedge_v5.py or run_nfl.py."""
import csv, sys
COLS = ["sport","home","away","home_proj","away_proj","player","team","proj","market","line","price_a","price_b","sgp","side"]
YARD = ("YDS", "YARDS")
def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None
def imp(o):
    o = num(o); return None if o is None or o == 0 else (100/(o+100) if o > 0 else -o/(-o+100))
def main(pp, lp, out):
    proj = {(r["home"].strip(), r["away"].strip()): r for r in csv.DictReader(open(pp))}
    rows, bad = [], []
    for r in csv.DictReader(open(lp)):
        key = (r["home"].strip(), r["away"].strip()); mk = r["market"].strip().upper()
        if key not in proj: bad.append((r, "no projection for game")); continue
        p, player = proj[key], (r.get("player") or "").strip()
        o = {c: (r.get(c) or "").strip() for c in COLS}
        o.update(sport="NFL", market=mk, home=key[0], away=key[1],
                 home_proj=p["home_proj"], away_proj=p["away_proj"])
        if player:
            if o["team"] not in key: bad.append((r, "prop team must equal home or away")); continue
            ln = num(o["line"])
            if any(y in mk for y in YARD) and (ln is None or ln < 1.5): bad.append((r, "yardage line < 1.5")); continue
            a, b = imp(o["price_a"]), imp(o["price_b"])
            if a and b:
                pa = a/(a+b)
                if not 0.03 <= pa <= 0.97: bad.append((r, f"implausible pair (over prob {pa:.2f})")); continue
        rows.append(o)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, COLS); w.writeheader(); w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}; rejected {len(bad)}")
    for r, why in bad: print("  REJECT", r.get("player") or "", r.get("market"), r.get("line"), "->", why)
if __name__ == "__main__":
    main(*sys.argv[1:4])
