"""Provenance wiring: non-VERIFIED_PIT NFL rows are held at 0u and can never reach the card."""
import csv
from datetime import datetime, timedelta, timezone
import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nfl_provenance as P  # noqa: E402
import run_nfl_wpl as W  # noqa: E402

KEY = "wiring-test-key"
KEY_ENV, MAN_ENV = W.ENV_KEY, W.ENV_MANIFEST
H = "sport,home,away,home_proj,away_proj,proj_provenance,market,line,price_a,price_b,event_id,kickoff_utc,captured_utc\n"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
KICK = (NOW + timedelta(hours=2)).isoformat()
CAPTURE = (NOW - timedelta(minutes=10)).isoformat()


def row(**kw):
    o = dict(sport="NFL", game="AWY @ HOM", bet_type="TOTAL|0|", player="", held="")
    o.update(kw)
    return o


def prov(cls, why=""):
    return {("AWY @ HOM", "TOTAL", "", ""): (cls, why)}


class Apply(unittest.TestCase):
    def test_verified_row_is_not_held_by_provenance(self):
        o = W.apply_provenance(row(), prov(P.VERIFIED))
        self.assertEqual((o["provenance"], o["held"]), (P.VERIFIED, ""))

    def test_every_other_class_is_held_with_class_and_reason(self):
        for cls in (P.UNVERIFIED, P.ANCHOR, P.MIXED, P.AMBIGUOUS, P.INVALID):
            o = W.apply_provenance(row(), prov(cls, "why-" + cls))
            self.assertEqual(o["provenance"], cls)
            self.assertIn("provenance " + cls, o["held"])
            self.assertIn("why-" + cls, o["held"])

    def test_existing_hold_reasons_are_kept(self):
        o = W.apply_provenance(row(held="prob guard"), prov(P.ANCHOR))
        self.assertTrue(o["held"].startswith("prob guard; provenance ANCHOR"))

    def test_missing_entry_and_failed_classification_fail_closed(self):
        self.assertIn("no provenance entry", W.apply_provenance(row(), {})["held"])
        self.assertIn("classification failed", W.apply_provenance(row(), None)["held"])

    def test_live_suffix_and_sgp_and_player_keys(self):
        p = {("AWY @ HOM", "SGP", "", "S1"): (P.VERIFIED, ""), ("AWY @ HOM", "REC_YDS", "P1", ""): (P.ANCHOR, "")}
        self.assertEqual(W.apply_provenance(row(game="AWY @ HOM (LIVE)", bet_type="SGP|0|S1"), p)["held"], "")
        self.assertIn("ANCHOR", W.apply_provenance(row(bet_type="REC_YDS|0|", player="P1"), p)["held"])

    def test_non_nfl_rows_untouched(self):
        o = row(sport="CBB")
        self.assertEqual(W.apply_provenance(dict(o), None), o)


def board(tag, hp="24", ap="20", event_id="event-test"):
    p = os.path.join(tempfile.mkdtemp(), "b.csv")
    with open(p, "w", newline="") as f:
        f.write(H + "".join(r + "," + ",".join((event_id, KICK, CAPTURE)) + "\n" for r in (
            "NFL,HOM,AWY,%s,%s,%s,SPREAD,-3.5,-110,-110" % (hp, ap, tag),
            "NFL,HOM,AWY,,,,TOTAL,44.5,-110,-110",
            "NFL,HOM,AWY,,,,ML,,-180,150")))
    return p


def run_cli(path, env_extra=None):
    wd = tempfile.mkdtemp()
    env = {k: v for k, v in os.environ.items() if k not in (KEY_ENV, MAN_ENV)}
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, os.path.join(HERE, "run_nfl_wpl.py"), path], cwd=wd, env=env,
                       capture_output=True, text=True, timeout=900)
    files = glob.glob(os.path.join(wd, "picks_nfl_*.csv"))
    rows = []
    if files:
        with open(files[0], newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    return r, rows


class EndToEnd(unittest.TestCase):
    def test_no_evidence_holds_every_row_and_nothing_is_selected(self):
        r, rows = run_cli(board("PIT_VERIFIED"))
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertTrue(rows)
        for x in rows:
            self.assertEqual(x["provenance"], P.UNVERIFIED, x["pick"])
            self.assertIn("provenance " + P.UNVERIFIED, x["held"])
            self.assertEqual(x["selected_for_card"], "False")
            self.assertEqual(float(x["approved_stake_u"]), 0.0)

    def test_signed_evidence_clears_provenance_but_only_for_the_proven_game(self):
        e = dict(subject="game|HOM|AWY", values=["24.0", "20.0"], model_version="m1", input_hash="a" * 64,
                 event_id="event-test", kickoff_ts=KICK,
                 forecast_ts=(NOW - timedelta(minutes=30)).isoformat(),
                 available_ts=(NOW - timedelta(minutes=20)).isoformat())
        e["sig"] = P.sign(e, KEY)
        mp = os.path.join(tempfile.mkdtemp(), "m.json")
        with open(mp, "w") as f:
            json.dump({"entries": [e]}, f)
        r, rows = run_cli(board("PIT_VERIFIED"), {KEY_ENV: KEY, MAN_ENV: mp})
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertTrue(rows)
        for x in rows:
            self.assertEqual(x["provenance"], P.VERIFIED, x["pick"])
            self.assertNotIn("provenance", x["held"])
        r2, rows2 = run_cli(board("PIT_VERIFIED", hp="25"), {KEY_ENV: KEY, MAN_ENV: mp})   # board differs from evidence
        self.assertTrue(all(x["provenance"] == P.UNVERIFIED and "provenance" in x["held"] for x in rows2))
        r3, rows3 = run_cli(board("PIT_VERIFIED"), {KEY_ENV: "wrong-key", MAN_ENV: mp})
        self.assertTrue(all(x["provenance"] == P.UNVERIFIED for x in rows3))
        r4, rows4 = run_cli(board("PIT_VERIFIED", event_id="rematch"), {KEY_ENV: KEY, MAN_ENV: mp})
        self.assertEqual(r4.returncode, 0, r4.stderr[-2000:])
        self.assertTrue(rows4)
        self.assertTrue(all(x["provenance"] == P.UNVERIFIED and x["selected_for_card"] == "False" for x in rows4))


if __name__ == "__main__":
    unittest.main()
