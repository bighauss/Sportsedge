#!/usr/bin/env python3
"""Grade frozen CFB RUN IT card rows (PAPER / 0u) and evaluate them against the same-time market.

Appends one GAME_GRADED entry per frozen row (losses and pushes kept) to the existing
hash-chained cfb_ledger, keyed by (card_sha256, row_index). Frozen rows are never edited.
Results come only from CFBD finals matched by the exact CFBD game ID; props only from CFBD
per-game player stats matched by the exact CFBD playerId. Anything that cannot be graded from
those sources is recorded UNGRADED with a reason, never guessed.
"""
from __future__ import annotations
import argparse, json, math, os, re, sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from models.cfb import cfb_ledger as ledger            # noqa: E402

STAT = {"rush_yds": ("rushing", "YDS"), "pass_yds": ("passing", "YDS"),
        "rec_yds": ("receiving", "YDS"), "receptions": ("receiving", "REC")}

def dec(am): am = float(am); return 1 + (am / 100 if am > 0 else 100 / -am)

def player_stats(players_payload):
    """CFBD /games/players -> {(game_id, playerId): {"rushing.YDS": v, ...}}."""
    out = {}
    for g in players_payload or []:
        gid = str(g.get("id"))
        for t in g.get("teams", []):
            for cat in t.get("categories", []):
                for typ in cat.get("types", []):
                    for a in typ.get("athletes", []):
                        try: v = float(a.get("stat"))
                        except (TypeError, ValueError): continue
                        out.setdefault((gid, str(a.get("id"))), {})[f"{cat.get('name')}.{typ.get('name')}"] = v
    return out

def _ou(pick, value, line):
    if value == line: return "P"
    over = pick.startswith("Over") or " Over " in pick
    return "W" if (value > line) == over else "L"

def result(row, g, pstats):
    """W / L / P, or (None, reason)."""
    H, A = g["homeTeam"], g["awayTeam"]; hp, ap = g.get("homePoints"), g.get("awayPoints")
    if hp is None or ap is None or not g.get("completed"): return None, "NO_FINAL"
    m, pick = row["market"], row["pick"]
    if m == "ML":
        if hp == ap: return "P", None
        return ("W" if (pick == H) == (hp > ap) else "L"), None
    if m in ("Spread", "1H Spread"):
        if m == "1H Spread":
            hl, al = g.get("homeLineScores") or [], g.get("awayLineScores") or []
            if len(hl) < 2 or len(al) < 2: return None, "NO_HALF_SCORES"
            hp, ap = sum(hl[:2]), sum(al[:2])
        team, line = pick.rsplit(" ", 1); line = float(line)
        mg = (hp - ap) if team == H else (ap - hp) if team == A else None
        if mg is None: return None, "PICK_TEAM_UNMATCHED"
        return ("P" if mg + line == 0 else "W" if mg + line > 0 else "L"), None
    if m == "Total": return _ou(pick, hp + ap, float(row["line"])), None
    if m == "1H Total":
        hl, al = g.get("homeLineScores") or [], g.get("awayLineScores") or []
        if len(hl) < 2 or len(al) < 2: return None, "NO_HALF_SCORES"
        return _ou(pick, sum(hl[:2]) + sum(al[:2]), float(row["line"])), None
    if m.endswith(" TT"):
        team = m[:-3]
        pts = hp if team == H else ap if team == A else None
        if pts is None: return None, "TT_TEAM_UNMATCHED"
        return _ou(pick, pts, float(row["line"])), None
    if m.startswith("Prop "):
        mk = m[5:]; pid = row.get("player_id")
        if not pid: return None, "PROP_NO_PROVIDER_ID"
        st = pstats.get((str(g["id"]), str(pid)))
        if st is None: return None, "PROP_PLAYER_NO_GAME_STATS"
        cat, typ = STAT.get(mk, (None, None))
        v = st.get(f"{cat}.{typ}")
        if v is None: return None, "PROP_STAT_MISSING"
        pick = f" {row.get('pick', '')} "
        if (" Over " in pick) == (" Under " in pick):
            return None, "PROP_SIDE_UNKNOWN"
        return _ou("Over" if " Over " in pick else "Under", v, float(row["line"])), None
    return None, "MARKET_UNSUPPORTED"

def grade(ledger_path, finals, players_payload, receipts, now=None):
    entries = ledger.verify(ledger_path)
    done = {(e.get("card_sha256"), e.get("row_index")) for e in entries
            if e.get("type") == "GAME_GRADED" and e.get("source") == "cfb_run_it"}
    by_id = defaultdict(list)
    for g in finals: by_id[str(g.get("id"))].append(g)
    pstats = player_stats(players_payload)
    census = Counter()
    for e in entries:
        if e.get("type") != "CARD_FROZEN" or e.get("source") != "cfb_run_it": continue
        for i, r in enumerate(e["rows"]):
            if (e["card_sha256"], i) in done: census["already_graded"] += 1; continue
            gs = by_id.get(str(r.get("cfbd_game_id")), [])
            if len(gs) != 1: census["pending_or_ambiguous_final"] += 1; continue
            res, why = result(r, gs[0], pstats)
            if res is None and why == "NO_FINAL": census["pending_no_final"] += 1; continue
            units = None
            if res == "W": units = dec(r["odds"]) - 1
            elif res == "L": units = -1.0
            elif res == "P": units = 0.0
            ledger.append(ledger_path, {
                "type": "GAME_GRADED", "source": "cfb_run_it", "card_sha256": e["card_sha256"], "row_index": i,
                "game_id": str(r["cfbd_game_id"]), "market": r["market"], "pick": r["pick"], "line": r.get("line"),
                "odds": r["odds"], "p_model": r["p_model"], "p_market": r["p_market"], "p_blend": r["p_blend"],
                "result": res, "ungraded_reason": why, "paper_units_1u": units,
                "final": {"home": gs[0]["homeTeam"], "away": gs[0]["awayTeam"],
                          "home_points": gs[0].get("homePoints"), "away_points": gs[0].get("awayPoints")},
                "source_receipts": receipts}, now=now)
            census["graded" if res else "ungraded:" + why] += 1
    return dict(census)

def _ll(p, y):
    p = min(1 - 1e-9, max(1e-9, p)); return -math.log(p if y else 1 - p)

def evaluate(ledger_path):
    g = [e for e in ledger.verify(ledger_path) if e.get("type") == "GAME_GRADED" and e.get("source") == "cfb_run_it"]
    dec_ = [e for e in g if e["result"] in ("W", "L")]
    def block(rows):
        if not rows: return {"n": 0}
        y = [1 if e["result"] == "W" else 0 for e in rows]
        return {"n": len(rows), "wins": sum(y), "hit_rate": mean(y),
                "paper_units": round(sum(e["paper_units_1u"] for e in rows), 3),
                "roi": round(sum(e["paper_units_1u"] for e in rows) / len(rows), 4),
                "brier": {k: round(mean((e[k] - yy) ** 2 for e, yy in zip(rows, y)), 4) for k in ("p_model", "p_blend", "p_market")},
                "log_loss": {k: round(mean(_ll(e[k], yy) for e, yy in zip(rows, y)), 4) for k in ("p_model", "p_blend", "p_market")}}
    fam = defaultdict(list)
    for e in dec_: fam["Prop" if e["market"].startswith("Prop") else e["market"]].append(e)
    return {"label": "PAPER_0U_GRADED_RESULTS", "graded_rows": len(g), "pushes": sum(e["result"] == "P" for e in g),
            "ungraded": dict(Counter(e["ungraded_reason"] for e in g if e["result"] is None)),
            "all_decided": block(dec_), "by_market": {k: block(v) for k, v in sorted(fam.items())},
            "note": "Brier/log loss compare the frozen probabilities with the same-time market probability on the "
                    "plays the card selected; lower is better. Selection bias: only +EV-flagged rows are graded."}

def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--ledger", required=True); a.add_argument("--finals"); a.add_argument("--players")
    a.add_argument("--receipts"); a.add_argument("--report", required=True)
    x = a.parse_args(argv)
    try:
        census = {}
        if x.finals:
            census = grade(x.ledger, json.loads(Path(x.finals).read_bytes()),
                           json.loads(Path(x.players).read_bytes()) if x.players else [],
                           json.loads(Path(x.receipts).read_text()) if x.receipts else [])
        rep = {"census": census, **evaluate(x.ledger)}
    except (ledger.LedgerRefused, ValueError, KeyError) as e:
        print(f"BLOCKED {type(e).__name__}: {e}", file=sys.stderr); return 2
    Path(x.report).write_text(json.dumps(rep, indent=1, sort_keys=True))
    print(json.dumps(rep, indent=1, sort_keys=True)); return 0

if __name__ == "__main__":
    raise SystemExit(main())
