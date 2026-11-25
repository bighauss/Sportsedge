"""Tests for the DK board integration (offline; synthetic + committed Nov 25 evidence).

Run from the repo root:  python -m unittest -v models.cbb.dk.test_dk_reconcile
"""
from __future__ import annotations
import csv, hashlib, io, json, subprocess, sys, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from models.cbb.dk import evidence as EV, reconcile as R, schema as S  # noqa: E402

HDR = "sport,away,home,market,line,price_a,price_b,period,player,tip_utc,captured_utc,dk_event_id,source_pdf_time_ct,note"


def page_html(eid, away, home, start, league="92483"):
    state = {"pageData": {str(eid): {"data": {
        "sportId": "2", "leagueId": league, "leagueName": "College Basketball (M)", "eventName": f"{away} @ {home}",
        "eventStatus": "NOT_STARTED", "startEventDate": start, "eventSeoId": "x",
        "participants": [{"id": "1", "name": home, "venueRole": "Home"}, {"id": "2", "name": away, "venueRole": "Away"}]}}}}
    return f"<html><script>window.__INITIAL_STATE__ = {json.dumps(state)};</script></html>".encode()


def rec(eid, away, home, start, league="92483", http="200"):
    html = page_html(eid, away, home, start, league)
    return EV.page_record(eid, f"https://sportsbook.draftkings.com/event/{eid}", "u", http, "2026-11-25T17:00:00Z", html)


def write(tmp, name, text):
    p = Path(tmp) / name; p.write_text(text, encoding="utf-8"); return p


class EvidenceParsing(unittest.TestCase):
    def test_parse_event_page(self):
        p = EV.parse_event_page(page_html(9, "A", "B", "2026-11-25T16:00:00.0000000Z"), 9)
        self.assertEqual(p["leagueId"], "92483")
        self.assertEqual(EV.participants_by_role(p)["Away"]["name"], "A")
        self.assertIsNone(EV.parse_event_page(b"<html>no state</html>", 9))
        self.assertIsNone(EV.parse_event_page(page_html(9, "A", "B", "x"), 10))

    def test_parse_utc_seven_digit_fraction(self):
        self.assertEqual(EV.parse_utc("2026-11-25T16:01:08.0000000Z"), datetime(2026, 11, 25, 16, 1, 8, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            EV.parse_utc("2026-11-25T16:01:08")


class EventCrosswalk(unittest.TestCase):
    G = [("A", "B", "2026-11-25T16:00:00Z")]

    def test_verified_exact(self):
        x = R.build_event_crosswalk(self.G, [rec(1, "A", "B", "2026-11-25T16:05:00.0000000Z")])[0]
        self.assertEqual((x["state"], x["dk_event_id"]), (S.EID_VERIFIED, "1"))

    def test_reversed_roles_not_verified(self):
        x = R.build_event_crosswalk(self.G, [rec(1, "B", "A", "2026-11-25T16:00:00Z")])[0]
        self.assertEqual(x["state"], S.EID_MISSING)

    def test_tip_outside_tolerance(self):
        x = R.build_event_crosswalk(self.G, [rec(1, "A", "B", "2026-11-25T17:00:00Z")])[0]
        self.assertEqual(x["state"], S.EID_MISSING); self.assertIn("TIP_MISMATCH", x["reason"])

    def test_wrong_league(self):
        x = R.build_event_crosswalk(self.G, [rec(1, "A", "B", "2026-11-25T16:00:00Z", league="36647")])[0]
        self.assertIn("NOT_NCAAB_MEN", x["reason"])

    def test_two_candidates_is_missing(self):
        x = R.build_event_crosswalk(self.G, [rec(1, "A", "B", "2026-11-25T16:00:00Z"), rec(2, "A", "B", "2026-11-25T16:00:00Z")])[0]
        self.assertEqual(x["state"], S.EID_MISSING)

    def test_404_never_binds(self):
        r = EV.page_record(1, "u", "u", "404", "t", page_html(1, "A", "B", "2026-11-25T16:00:00Z"))
        self.assertNotIn("page", r)
        self.assertEqual(R.build_event_crosswalk(self.G, [r])[0]["state"], S.EID_MISSING)


class Reconcile(unittest.TestCase):
    def run_board(self, lines, transcript_lines=(), as_of=None, hold=frozenset(), corrected=None):
        with tempfile.TemporaryDirectory() as t:
            o = write(t, "o.csv", HDR + "\n" + "\n".join(lines) + "\n")
            c = write(t, "c.csv", HDR + "\n" + "\n".join(corrected or lines) + "\n")
            tr = write(t, "t.csv", "sport,away,home,market,line,price_a,price_b,period,player,dk_event_id,tip_utc,captured_utc,source,note\n"
                       + "\n".join(transcript_lines) + "\n")
            rows, trunc = R.load_captures(o, c, tr)
        xw = R.build_event_crosswalk([("A", "B", "2026-11-25T16:00:00Z")], [rec(7, "A", "B", "2026-11-25T16:00:00Z")])
        return R.reconcile(rows, trunc, xw, {}, [], as_of_utc=as_of, issue57_hold_games=hold)

    def L(self, market, line, pa, pb, period="FG", cap="2026-11-25T12:34:10Z", player="", note=""):
        return f"CBB,A,B,{market},{line},{pa},{pb},{period},{player},2026-11-25T16:00:00Z,{cap},,6.34.10,{note}"

    def test_accepts_consistent_main_markets_and_fills_id(self):
        d, ledger, info = self.run_board([self.L("SPREAD", "-3.5", "-110", "-110"), self.L("ML", "", "-165", "+140"),
                                          self.L("TOTAL", "140.5", "-110", "-110"), self.L("ALT_TOTAL", "138.5", "-135", "+110")])
        by = {x.market: x for x in d}
        self.assertEqual(by["SPREAD"].disposition, S.ACCEPTED); self.assertEqual(by["SPREAD"].dk_event_id, "7")
        self.assertEqual(by["TOTAL"].totals_order, "over_under")
        self.assertEqual(by["SPREAD"].tip_ct, "2026-11-25 10:00 CT")
        self.assertEqual(ledger, [])

    def test_orientation_conflict_rejected(self):
        d, ledger, _ = self.run_board([self.L("SPREAD", "-3.5", "-110", "-110"), self.L("ML", "", "+140", "-165")])
        self.assertTrue(all("ORIENTATION_SPREAD_VS_ML_CONFLICT" in x.reason_codes for x in d))
        self.assertTrue(all(x.disposition == S.REJECTED for x in d)); self.assertEqual(len(ledger), 2)

    def test_totals_order_conflict_and_unverified(self):
        d, _, _ = self.run_board([self.L("TOTAL", "140.5", "-110", "-110"), self.L("ALT_TOTAL", "138.5", "+110", "-135")])
        self.assertTrue(all("TOTALS_ORDER_CONFLICT" in x.reason_codes for x in d))
        d, _, _ = self.run_board([self.L("TOTAL", "140.5", "-110", "-110")])
        self.assertEqual((d[0].disposition, d[0].reason_codes), (S.HELD, "TOTALS_ORDER_UNVERIFIED"))

    def test_one_sided_milestone_and_bad_prices(self):
        d, _, _ = self.run_board([self.L("PLAYER_POINTS_AT_LEAST", "16", "-120", "", player="X",
                                         note="one-sided milestone; player team not established by screenshot"),
                                  self.L("SPREAD", "-3.5", "-12", "-11"), self.L("SPREAD", "-3.25", "-110", "-110", period="1H")])
        self.assertEqual(d[0].reason_codes, "ONE_SIDED_QUOTE;PLAYER_TEAM_NOT_ESTABLISHED")
        self.assertIn("PRICE_INVALID_AMERICAN", d[1].reason_codes)
        self.assertIn("LINE_INVALID", d[2].reason_codes)

    def test_live_and_started_exclusion(self):
        d, _, _ = self.run_board([self.L("SPREAD", "-3.5", "-110", "-110", cap="2026-11-25T16:00:00Z")])
        self.assertIn("LIVE_AT_CAPTURE", d[0].reason_codes)
        d, _, _ = self.run_board([self.L("SPREAD", "-3.5", "-110", "-110")], as_of=datetime(2026, 11, 25, 16, 30, tzinfo=timezone.utc))
        self.assertIn("STARTED_BEFORE_AS_OF", d[0].reason_codes); self.assertEqual(d[0].disposition, S.REJECTED)

    def test_supersession_and_hold(self):
        tr = ['"CBB","A","B","SPREAD","-3.5","-110","-110","FG","","","2026-11-25T16:00:00Z","2026-11-25T11:30:00Z","op",""']
        d, _, _ = self.run_board([self.L("SPREAD", "-4.5", "-110", "-110")], tr, hold=frozenset({("A", "B", "2026-11-25T16:00:00Z")}))
        by = {x.capture_id: x for x in d}
        self.assertEqual(by["transcript_0517_0534CT"].disposition, S.SUPERSEDED)
        self.assertEqual(by["pdf_0636CT"].disposition, S.HELD)
        self.assertIn("ISSUE57_ORIENTATION_HOLD", by["pdf_0636CT"].reason_codes)

    def test_truncated_original_logged_and_corrected_used(self):
        d, ledger, _ = self.run_board([self.L("TOTAL", "6", "-12", "-11", period="1H")],
                                      corrected=[self.L("TOTAL", "63.5", "-120", "-110", period="1H")])
        self.assertEqual(d[0].provenance, S.PROV_PDF_RETRANSCRIBED); self.assertEqual(d[0].totals_order, "over_under")
        self.assertEqual(ledger[0]["reason_codes"], "LINE_TRUNCATED_SUPERSEDED_PR530")

    def test_every_non_accepted_row_has_reason(self):
        d, ledger, _ = self.run_board([self.L("SPREAD", "-3.5", "-110", "-110"), self.L("ML", "", "+140", "-165"),
                                       self.L("BOTH_TEAM_TOTAL", "60.5", "-200", "+800")])
        for x in d:
            self.assertTrue(x.disposition == S.ACCEPTED or x.reason_codes)
            for c in filter(None, x.reason_codes.split(";")):
                self.assertIn(c, S.REASONS)
            self.assertEqual((x.label, x.official_counted, x.approved_stake_u, x.authenticated), ("PAPER_0U", 0, 0, 0))


class TranscriptOrder(unittest.TestCase):
    def test_markdown_explicit_over_price(self):
        rows = [{"market": "TOTAL", "period": "FG", "line": "137.5", "price_a": "-112", "price_b": "-108"}]
        md = "Saint Bonaventure: Spread -4.5, -110; Total O137.5, -112; Moneyline -205\nBelmont: Spread +4.5, -110; Total U137.5, -108"
        self.assertTrue(R.transcript_explicit_totals_order(md, rows))
        rows[0]["price_a"], rows[0]["price_b"] = "-108", "-112"
        self.assertFalse(R.transcript_explicit_totals_order(md, rows))


LINES = ROOT / "models/cbb/lines"
ORIGINAL_BLOBS = {  # git blob SHA-1 of the originals on main 7fc5aaa9; this module must never change them
    "board_2026-11-25_0636CT_pdf_capture.csv": "2e2d42ded809c8e34b569c9a1d9cc60a260399d7",
}


def git_blob(path):
    b = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


class CommittedNov25(unittest.TestCase):
    def test_original_board_unchanged(self):
        for name, blob in ORIGINAL_BLOBS.items():
            self.assertEqual(git_blob(LINES / name), blob)

    def test_reproduces_committed_outputs(self):
        with tempfile.TemporaryDirectory() as t:
            from models.cbb.dk import cli
            self.assertEqual(cli.main(["reconcile", "--as-of", "2026-11-25T12:36:15Z", "--out-dir", t]), 0)
            committed = ROOT / "models/cbb/dk/derived/2026-11-25"
            for f in ("derived_board.csv", "runner_board.csv", "rejection_ledger.csv"):
                self.assertEqual((Path(t) / f).read_bytes(), (committed / f).read_bytes(), f)
            rep = json.loads((Path(t) / "report.json").read_text())
        self.assertEqual(rep["rows_in"], 1002)
        self.assertEqual(rep["event_ids"]["games"], 53)
        self.assertEqual(rep["event_ids"]["verified"], 48)
        self.assertEqual(rep["authenticated_rows"], 0)
        self.assertTrue(rep["transcript_totals_order_verified_from_markdown"])
        self.assertEqual(sum(rep["dispositions"].values()), 1002)

    def test_crosswalk_ids_unique_and_evidenced(self):
        xw = R.read_csv(LINES / "dk_event_crosswalk_2026-11-25.csv")
        ids = [x["dk_event_id"] for x in xw if x["dk_event_id"]]
        self.assertEqual(len(ids), len(set(ids)))
        for x in xw:
            if x["state"] == S.EID_VERIFIED:
                self.assertTrue(x["retrieved_utc"] and x["html_sha256"] and x["final_url"].endswith("/" + x["dk_event_id"]))
            else:
                self.assertTrue(x["reason"].startswith("DK_EVENT_ID_MISSING"))
        sb = [x for x in xw if x["board_away"] == "Saint Bonaventure"][0]
        self.assertEqual(sb["dk_event_id"], "35083406")


if __name__ == "__main__":
    unittest.main()
