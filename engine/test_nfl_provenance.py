"""Provenance classification regression (pure python; no v5 / numpy needed)."""
import os
from datetime import datetime
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nfl_provenance as P  # noqa: E402

H = "sport,home,away,home_proj,away_proj,proj_provenance,player,team,proj,market,line,price_a,price_b,sgp,side,event_id,kickoff_utc,captured_utc,player_id\n"
NOW = datetime.fromisoformat("2026-11-26T16:00:00+00:00")
KICK = "2026-11-26T18:00:00+00:00"
CAPTURE = "2026-11-26T15:00:00+00:00"
V = "PIT_VERIFIED"
KEY = "test-key"


def game(hp="27", ap="20", tag=V):
    return ["NFL,A,B,%s,%s,%s,,,,TOTAL,44.5,-110,-110,," % (hp, ap, tag), "NFL,A,B,,,,,,,SPREAD,-3.5,-110,-110,,"]


def prop(player="P1", market="REC_YDS", proj="70", tag=V, line="59.5", sgp="", side="", team="A"):
    return "NFL,A,B,,,%s,%s,%s,%s,%s,%s,-110,-110,%s,%s" % (tag, player, team, proj, market, line, sgp, side)


def td(player="P1", share="0.3", tag=V):
    return "NFL,A,B,,,%s,%s,A,%s,ATD,,150,-190,," % (tag, player, share)


SGP = "NFL,A,B,,,,,,,SGP,,600,,S1,"


def entry(subject, values, key=KEY, **kw):
    e = dict(subject=subject, values=values, model_version="m1", input_hash="a" * 64,
             forecast_ts="2026-11-26T14:00:00+00:00", available_ts="2026-11-26T14:30:00+00:00",
             kickoff_ts=KICK, event_id="event-ab")
    if subject.startswith("prop|"):
        e.update(player_id=subject.split("|")[3], team="A")
    e.update(kw)
    e["sig"] = P.sign(e, key)
    return e


def manifest(*entries):
    return {e["subject"]: e for e in entries}


FULL = manifest(entry("game|A|B", ["27.0", "20.0"]), entry("prop|A|B|P1|REC_YDS", ["70.0"]),
                entry("prop|A|B|P1|ATD", ["0.3"]), entry("prop|A|B|P2|REC_YDS", ["70.0"]))


def run(*rows, ev=FULL, key=KEY, event_id="event-ab", kick=KICK, capture=CAPTURE, now=NOW, athlete=None):
    p = os.path.join(tempfile.mkdtemp(), "b.csv")
    extended = []
    for r in rows:
        fields = r.split(",")
        pid = fields[6]
        eid = event_id if fields[1:3] == ["A", "B"] else "event-cd"
        extended.append(r + "," + ",".join((eid, kick, capture, athlete if athlete is not None and pid else pid)))
    with open(p, "w", newline="") as f:
        f.write(H + "\n".join(extended) + "\n")
    return P.classify(p, ev, key, now=now)


def cls(res, market, player="", sgp=""):
    return res[("B @ A", market, player, sgp)][0]


class Provenance(unittest.TestCase):
    def test_independent_game_vs_anchored_game(self):
        self.assertEqual(cls(run(*game()), "TOTAL"), P.VERIFIED)
        self.assertEqual(cls(run(*game("", "", "")), "TOTAL"), P.ANCHOR)

    def test_supplied_but_unverified_projection_is_held(self):
        for tag in ("", "UNVERIFIED"):
            self.assertEqual(cls(run(*game(tag=tag)), "TOTAL"), P.UNVERIFIED)
        self.assertFalse(P.eligible(P.UNVERIFIED))

    def test_unknown_tag_is_ambiguous(self):
        self.assertEqual(cls(run(*game(tag="TRUST_ME")), "TOTAL"), P.AMBIGUOUS)

    def test_partial_team_projection_falls_back_to_anchor(self):
        self.assertEqual(cls(run(*game("27", "", V)), "TOTAL"), P.ANCHOR)

    def test_conflicting_team_projections_are_ambiguous(self):
        rows = game() + ["NFL,A,B,30,10,%s,,,,ML,,-150,130,," % V]
        self.assertEqual(cls(run(*rows), "TOTAL"), P.AMBIGUOUS)

    def test_independent_game_with_anchored_player_prop(self):
        self.assertEqual(cls(run(*game(), prop(proj="", tag="")), "REC_YDS", "P1"), P.ANCHOR)

    def test_anchored_game_with_independent_stat_prop_depends_only_on_its_mean(self):
        r = run(*game("", "", ""), prop())
        self.assertEqual(cls(r, "REC_YDS", "P1"), P.VERIFIED)
        self.assertEqual(cls(r, "TOTAL"), P.ANCHOR)

    def test_td_prop_depends_on_game_simulation(self):
        self.assertEqual(cls(run(*game("", "", ""), td()), "ATD", "P1"), P.MIXED)
        self.assertEqual(cls(run(*game(), td()), "ATD", "P1"), P.VERIFIED)
        self.assertEqual(cls(run(*game(tag="UNVERIFIED"), td()), "ATD", "P1"), P.UNVERIFIED)

    def test_td_prop_without_share_is_ambiguous(self):
        self.assertEqual(cls(run(*game(), td(share="", tag="")), "ATD", "P1"), P.AMBIGUOUS)

    def test_sgp_all_verified_legs_is_verified(self):
        r = run(*game(), prop(sgp="S1", side="A"), prop("P2", sgp="S1", side="B"), SGP)
        self.assertEqual(cls(r, "SGP", "", "S1"), P.VERIFIED)

    def test_sgp_with_anchored_player_leg_is_held(self):
        legs = (prop(sgp="S1", side="A"), prop("P2", proj="", tag="", sgp="S1", side="B"), SGP)
        r = run(*game(), *legs)
        self.assertEqual(cls(r, "SGP", "", "S1"), P.MIXED)
        self.assertFalse(P.eligible(cls(r, "SGP", "", "S1")))
        self.assertEqual(cls(run(*game("", "", ""), *legs), "SGP", "", "S1"), P.MIXED)

    def test_sgp_over_anchored_game_with_verified_legs_is_mixed(self):
        r = run(*game("", "", ""), prop(sgp="S1", side="A"), prop("P2", sgp="S1", side="B"), SGP)
        self.assertEqual(cls(r, "SGP", "", "S1"), P.MIXED)

    def test_duplicate_quote_with_different_provenance_is_ambiguous(self):
        rows = game() + [prop(), prop(tag="UNVERIFIED")]
        self.assertEqual(cls(run(*rows), "REC_YDS", "P1"), P.AMBIGUOUS)

    def test_row_order_does_not_change_classification(self):
        rows = game() + [prop(), td()]
        self.assertEqual(run(*rows), run(*reversed(rows)))


class Adversarial(unittest.TestCase):
    """The eight inputs an independent audit found wrongly eligible, plus evidence binding."""

    def test_self_asserted_tag_without_evidence_is_held(self):
        for ev, key in ((None, None), ({}, KEY), (FULL, None), (FULL, "other-key")):
            r = run(*game(), ev=ev, key=key)
            self.assertEqual(cls(r, "TOTAL"), P.UNVERIFIED)
        self.assertIn("without proof", run(*game(), ev=None)[("B @ A", "TOTAL", "", "")][1])

    def test_tampered_or_mismatched_or_incomplete_evidence_is_held(self):
        bad = {
            "tampered values": dict(entry("game|A|B", ["27.0", "20.0"]), values=["30.0", "20.0"]),
            "board differs": entry("game|A|B", ["28.0", "20.0"]),
            "no model version": entry("game|A|B", ["27.0", "20.0"], model_version=""),
            "no input hash": entry("game|A|B", ["27.0", "20.0"], input_hash=""),
            "forecast after kickoff": entry("game|A|B", ["27.0", "20.0"], forecast_ts="2026-11-26T19:00:00+00:00"),
            "forecast at kickoff": entry("game|A|B", ["27.0", "20.0"], forecast_ts="2026-11-26T18:00:00+00:00"),
            "naive timestamp": entry("game|A|B", ["27.0", "20.0"], forecast_ts="2026-11-26T14:00:00"),
            "garbage timestamp": entry("game|A|B", ["27.0", "20.0"], kickoff_ts="soon"),
        }
        for name, e in bad.items():
            with self.subTest(name):
                self.assertEqual(cls(run(*game(), ev=manifest(e)), "TOTAL"), P.UNVERIFIED)

    def test_valid_evidence_with_no_tag_is_still_unverified(self):
        self.assertEqual(cls(run(*game(tag="")), "TOTAL"), P.UNVERIFIED)

    def test_nonfinite_team_projection_is_invalid(self):
        for bad in ("nan", "inf", "-inf", "1e999"):
            with self.subTest(bad):
                r = run(*game(hp=bad))
                self.assertEqual(cls(r, "TOTAL"), P.INVALID)
                self.assertFalse(P.eligible(cls(r, "TOTAL")))

    def test_team_projection_out_of_range_is_invalid(self):
        self.assertEqual(cls(run(*game(hp="-3")), "TOTAL"), P.INVALID)
        self.assertEqual(cls(run(*game(hp="400")), "TOTAL"), P.INVALID)

    def test_nonfinite_or_negative_player_mean_is_invalid(self):
        for bad in ("inf", "nan", "-5", "99999"):
            with self.subTest(bad):
                self.assertEqual(cls(run(*game(), prop(proj=bad)), "REC_YDS", "P1"), P.INVALID)

    def test_td_share_outside_zero_one_is_invalid(self):
        for bad in ("1.5", "-0.1", "nan"):
            with self.subTest(bad):
                self.assertEqual(cls(run(*game(), td(share=bad)), "ATD", "P1"), P.INVALID)

    def test_player_on_two_teams_or_unknown_team_is_invalid(self):
        r = run(*game(), prop(team="A"), prop(market="RUSH_YDS", team="B"))
        self.assertEqual(cls(r, "REC_YDS", "P1"), P.INVALID)
        self.assertEqual(cls(run(*game(), prop(team="ZZZ")), "REC_YDS", "P1"), P.INVALID)

    def test_one_leg_and_zero_leg_sgp_is_invalid(self):
        one = run(*game(), prop(sgp="S1", side="A"), SGP)
        self.assertEqual(cls(one, "SGP", "", "S1"), P.INVALID)
        self.assertEqual(cls(one, "REC_YDS", "P1", "S1"), P.INVALID)
        self.assertEqual(cls(run(*game(), SGP), "SGP", "", "S1"), P.INVALID)

    def test_invalid_sgp_side_is_invalid(self):
        for side in ("", "C", "a", "HOME"):
            with self.subTest(side):
                r = run(*game(), prop(sgp="S1", side=side), prop("P2", sgp="S1", side="B"), SGP)
                self.assertEqual(cls(r, "SGP", "", "S1"), P.INVALID)

    def test_sgp_id_spanning_two_games_is_invalid(self):
        other = "NFL,C,D,,,,P9,C,70,REC_YDS,59.5,-110,-110,S1,A"
        r = run(*game(), prop(sgp="S1", side="A"), prop("P2", sgp="S1", side="B"), other, SGP)
        self.assertEqual(cls(r, "SGP", "", "S1"), P.INVALID)

    def test_same_team_both_sides_of_one_game_is_invalid(self):
        p = os.path.join(tempfile.mkdtemp(), "b.csv")
        with open(p, "w") as f:
            f.write(H + "NFL,A,A,27,20,%s,,,,TOTAL,44.5,-110,-110,,\n" % V)
        self.assertEqual(P.classify(p, FULL, KEY)[("A @ A", "TOTAL", "", "")][0], P.INVALID)

    def test_negative_control_verified_tag_but_no_game_projection_is_anchor(self):
        self.assertEqual(cls(run(*game("", "", V)), "TOTAL"), P.ANCHOR)

    def test_event_bound_receipt_rejects_rematch_and_changed_kickoff(self):
        self.assertEqual(cls(run(*game()), "TOTAL"), P.VERIFIED)
        for kw in ({"event_id": "rematch"}, {"kick": "2026-11-26T19:00:00+00:00"},
                   {"event_id": ""}, {"capture": ""}):
            with self.subTest(kw=kw):
                self.assertEqual(cls(run(*game(), **kw), "TOTAL"), P.UNVERIFIED)

    def test_pregame_clock_rejects_future_capture_and_late_run(self):
        for kw in ({"capture": "2026-11-26T17:00:00+00:00"},
                   {"now": datetime.fromisoformat(KICK)},
                   {"capture": "2026-11-26T14:15:00+00:00"}):
            with self.subTest(kw=kw):
                self.assertEqual(cls(run(*game(), **kw), "TOTAL"), P.UNVERIFIED)

    def test_player_id_must_match_signed_receipt_for_props_and_sgp(self):
        self.assertEqual(cls(run(*game(), prop(), athlete="different"), "REC_YDS", "P1"), P.UNVERIFIED)
        legs = (prop(sgp="S1", side="A"), prop("P2", sgp="S1", side="B"), SGP)
        self.assertEqual(cls(run(*game(), *legs, athlete="same-id"), "SGP", "", "S1"), P.UNVERIFIED)

    def test_legacy_signed_receipt_and_unavailable_forecast_held(self):
        old = entry("game|A|B", ["27.0", "20.0"])
        del old["event_id"]
        old["sig"] = P.sign(old, KEY)
        for e in (old, entry("game|A|B", ["27.0", "20.0"], available_ts="2026-11-26T15:30:00+00:00")):
            self.assertEqual(cls(run(*game(), ev=manifest(e)), "TOTAL"), P.UNVERIFIED)


if __name__ == "__main__":
    unittest.main()
