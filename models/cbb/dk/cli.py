"""CLI for the DK board integration.

  python -m models.cbb.dk.cli crosswalk --date 2026-11-25      # evidence -> crosswalk CSVs
  python -m models.cbb.dk.cli reconcile --date 2026-11-25 [--as-of 2026-11-25T12:36:15Z] [--out-dir DIR]

Defaults point at the committed Nov 25 inputs. Original boards are only read.
Exit code 0 on success; the outputs are a derived board, a runner board, a rejection ledger
and a JSON report (see docs/cbb/dk_interface.md).
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from models.cbb.dk import evidence as EV, reconcile as R, schema as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
LINES = ROOT / "models/cbb/lines"
DK = ROOT / "models/cbb/dk"

# Board spelling -> ESPN 'location' where they differ. Each was checked by hand against the
# ESPN scoreboard for the same tip minute AND the same opponent (unique hit); no fuzzy matching.
ESPN_LOCATION_ALIASES = {
    "Saint Bonaventure": "St. Bonaventure", "Appalachian State": "App State", "New Orleans": "LSU New Orleans",
    "Southern University": "Southern", "Alcorn": "Alcorn State", "Albany NY": "UAlbany",
    "Saint Thomas MN": "St. Thomas", "USC Upstate": "South Carolina Upstate",
    "CSU Bakersfield": "Cal State Bakersfield", "Mississippi Valley": "Mississippi Valley State",
    "CSUN": "Cal State Northridge", "Prairie View": "Prairie View A&M", "Saint Peters": "Saint Peter's",
    "Miami OH": "Miami (OH)", "FIU": "Florida International", "UConn": "UConn", "Hawaii": "Hawai'i",
}


def paths(date):
    d = date
    return {
        "pdf_original": LINES / f"board_{d}_0636CT_pdf_capture.csv",
        "pdf_corrected": LINES / f"board_{d}_0636CT_pdf_capture_h1_corrected.csv",
        "transcript": LINES / f"board_{d}_0900CT_operator_transcript.csv",
        "transcript_md": ROOT / f"research/cbb/boards/{d}_0900CT_muse_transcript.md",
        "pages": DK / f"evidence/{d}/dk_event_pages.jsonl",
        "sitemap": DK / f"evidence/{d}/dk_sitemap_matches.json",
        "espn": DK / f"evidence/{d}/espn_scoreboard_extract.json",
        "event_xw": LINES / f"dk_event_crosswalk_{d}.csv",
        "team_xw": LINES / f"dk_team_crosswalk_{d}.csv",
        "out": DK / f"derived/{d}",
    }


def games_of(rows):
    seen = []
    for r in rows:
        k = (r["away"], r["home"], r["tip_utc"])
        if k not in seen:
            seen.append(k)
    return seen


EVENT_XW_COLS = ["board_away", "board_home", "board_tip_utc", "dk_event_id", "dk_event_name", "dk_away_participant_id",
                 "dk_home_participant_id", "dk_league_id", "dk_start_utc", "dk_event_status_at_retrieval", "request_url",
                 "final_url", "retrieved_utc", "html_sha256", "discovery", "state", "reason"]
TEAM_XW_COLS = ["board_name", "dk_participant_name", "dk_participant_id", "espn_team_id", "espn_location",
                "espn_display_name", "cbbd_norm_key", "cbbd_verified", "method"]


def cmd_crosswalk(a):
    p = paths(a.date)
    rows = R.read_csv(p["pdf_corrected"]) + R.read_csv(p["transcript"])
    games = games_of(rows)
    pages = EV.load_jsonl(p["pages"])
    sm = json.loads(p["sitemap"].read_text())
    exw = R.build_event_crosswalk(games, pages, frozenset(m["event_id"] for m in sm["matches"]))
    R.write_csv(p["event_xw"], EVENT_XW_COLS, exw)
    espn = json.loads(p["espn"].read_text())["events"]
    match = R.match_espn(games, espn, ESPN_LOCATION_ALIASES)
    try:
        sys.path.insert(0, str(ROOT / "models/cbb"))
        import cbb_run_it as RUN  # read-only use of the runner's normaliser and dated aliases
        def cbbd_key(n):
            k = RUN.norm(n); return RUN.DATED_BOARD_ALIASES.get(k, k)
    except Exception:  # pragma: no cover
        def cbbd_key(n):
            return R.norm(n)
    team = {}
    for x in exw:
        g = (x["board_away"], x["board_home"], x["board_tip_utc"]); e = match.get(g)
        for side, name in (("away", x["board_away"]), ("home", x["board_home"])):
            et = e[side] if e else {}
            pid = x["dk_away_participant_id"] if side == "away" else x["dk_home_participant_id"]
            prev = team.get(name)
            rec = {"board_name": name, "dk_participant_name": name if pid else "", "dk_participant_id": pid,
                   "espn_team_id": et.get("espn_team_id", ""), "espn_location": et.get("location", ""),
                   "espn_display_name": et.get("displayName", ""), "cbbd_norm_key": cbbd_key(name), "cbbd_verified": 0,
                   "method": ";".join(filter(None, [
                       "DK_EVENT_PAGE_EXACT_NAME" if pid else "",
                       ("ESPN_EXPLICIT_ALIAS_SAME_TIP_SAME_OPPONENT" if name in ESPN_LOCATION_ALIASES else "ESPN_EXACT_NAME_SAME_TIP") if e else "ESPN_UNMATCHED"]))}
            if prev and prev["dk_participant_id"] and not rec["dk_participant_id"]:
                continue
            team[name] = rec
    R.write_csv(p["team_xw"], TEAM_XW_COLS, sorted(team.values(), key=lambda r: r["board_name"]))
    c = Counter(x["state"] for x in exw)
    print(json.dumps({"games": len(games), "event_states": c, "espn_matched": sum(1 for v in match.values() if v)}))
    return 0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cmd_reconcile(a):
    p = paths(a.date)
    out = Path(a.out_dir) if a.out_dir else p["out"]
    rows, truncated = R.load_captures(p["pdf_original"], p["pdf_corrected"], p["transcript"])
    exw = R.read_csv(p["event_xw"]); txw = R.read_csv(p["team_xw"])
    espn = json.loads(p["espn"].read_text())["events"]
    games = games_of(rows)
    espn_by = R.match_espn(games, espn, ESPN_LOCATION_ALIASES)
    md_ok = p["transcript_md"].exists() and R.transcript_explicit_totals_order(
        p["transcript_md"].read_text(encoding="utf-8"), R.read_csv(p["transcript"]))
    as_of = EV.parse_utc(a.as_of) if a.as_of else None
    hold = frozenset(g for g in games if (g[0], g[1]) in {tuple(h.split("@")) for h in a.issue57_hold})
    derived, ledger, info = R.reconcile(rows, truncated, exw, espn_by, txw, as_of_utc=as_of,
                                        transcript_totals_verified=md_ok,
                                        require_authenticated=a.require_authenticated, issue57_hold_games=hold)
    out.mkdir(parents=True, exist_ok=True)
    R.write_csv(out / "derived_board.csv", S.DerivedRow.columns(), [d.as_dict() for d in derived])
    rb = R.runner_board(derived)
    R.write_csv(out / "runner_board.csv", R.RUNNER_COLUMNS, rb)
    R.write_csv(out / "rejection_ledger.csv", S.LEDGER_COLUMNS, ledger)
    disp = Counter(d.disposition for d in derived)
    codes = Counter(c for d in derived for c in d.reason_codes.split(";") if c)
    by_cap = {}
    for d in derived:
        by_cap.setdefault(d.capture_id, Counter())[d.disposition] += 1
    report = {
        "schema": S.SCHEMA_VERSION, "date": a.date, "as_of_utc": a.as_of or None,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {k: {"path": str(p[k].relative_to(ROOT)), "sha256": sha(p[k])}
                   for k in ("pdf_original", "pdf_corrected", "transcript", "transcript_md", "pages", "sitemap", "espn", "event_xw", "team_xw")
                   if p[k].exists()},
        "rows_in": len(rows), "original_truncated_rows": len(truncated),
        "dispositions": disp, "by_capture": by_cap, "reason_code_counts": codes,
        "runner_board_rows": len(rb),
        "event_ids": {"games": len(games),
                      "verified": sum(1 for x in exw if x["state"] == S.EID_VERIFIED),
                      "missing": [{"game": f"{x['board_away']} @ {x['board_home']}", "tip_utc": x["board_tip_utc"], "reason": x["reason"]}
                                  for x in exw if x["state"] != S.EID_VERIFIED],
                      "rows_with_verified_id": sum(1 for d in derived if d.dk_event_id),
                      "pdf_rows_with_verified_id": sum(1 for d in derived if d.dk_event_id and d.capture_id == "pdf_0636CT"),
                      "pdf_rows_with_board_id_on_main": sum(1 for r in rows if r["capture_id"] == "pdf_0636CT" and (r.get("dk_event_id") or "").strip())},
        "espn_matched_games": sum(1 for v in espn_by.values() if v),
        "neutral_games": sorted(f"{g[0]} @ {g[1]}" for g, e in espn_by.items() if e and e["neutral_site"]),
        "identity_checks": {k: {" | ".join([c, *g[:2], per]): v for (c, g, per), v in d.items()} for k, d in info.items()},
        "transcript_totals_order_verified_from_markdown": md_ok,
        "espn_current_feed_orientation": R.espn_orientation_check(derived, espn_by),
        "cross_capture_saint_bonaventure_belmont": R.cross_capture_diff(rows, ("Saint Bonaventure", "Belmont")),
        "authenticated_rows": sum(d.authenticated for d in derived),
        "authenticated_quote_rows": 0,
        "event_id_verification_is_not_quote_authentication": True,
        "espn_odds_role": "AUXILIARY_RESEARCH_COMPARATOR_ONLY",
        "owner_rulings": {
            "st_bonaventure_belmont_orientation": (
                "ACCEPTED_FOR_RETROSPECTIVE_RESEARCH: board line and price_a are HOME, "
                "so SPREAD +4.5 / ML +170-205 means Saint Bonaventure -4.5 / -205 and Belmont +4.5 / +170."
            ),
            "st_bonaventure_belmont_hold": (
                "ISSUE57_ORIENTATION_HOLD is retained on every row of this game. "
                "The game is excluded from runner_board and must never enter a pregame card."
            ),
            "event_verification_vs_quotes": (
                "A verified DK event ID confirms public event identity (league, participants, tip). "
                "It does not authenticate quote prices, market IDs or capture provenance. "
                "Authenticated quote rows on this board: 0."
            ),
            "espn_odds": (
                "ESPN scoreboard odds (provider label as given by ESPN) are an auxiliary "
                "research comparator only: never an admitted odds source, never used for pricing, "
                "never treated as quote authentication."
            ),
        },
        "label": "PAPER_0U", "official_counted": 0, "approved_stake_u": 0,
    }
    (out / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True, default=dict) + "\n", encoding="utf-8")
    print(json.dumps({"rows_in": len(rows), "dispositions": disp, "runner_board_rows": len(rb),
                      "verified_games": report["event_ids"]["verified"], "games": len(games)}, default=dict))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m models.cbb.dk.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crosswalk"); c.add_argument("--date", default="2026-11-25")
    r = sub.add_parser("reconcile"); r.add_argument("--date", default="2026-11-25")
    r.add_argument("--as-of", default=None, help="UTC run time; games tipped by then are STARTED_BEFORE_AS_OF")
    r.add_argument("--out-dir", default=None)
    r.add_argument("--require-authenticated", action="store_true")
    r.add_argument("--issue57-hold", nargs="*", default=["Saint Bonaventure@Belmont"],
                   help="away@home games withheld under issue #57 (default: the 9 AM game)")
    a = ap.parse_args(argv)
    return cmd_crosswalk(a) if a.cmd == "crosswalk" else cmd_reconcile(a)


if __name__ == "__main__":
    sys.exit(main())
