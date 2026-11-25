"""Regression and census tests for the NBA market-contract ingestion guard v2 (PR #539).

The frozen model file is never edited. Every owner-review defect has a test here; the same scenarios were
probed against the first guard (006ef31b) and were accepted or mishandled there (see the PR report).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import make_samples
import market_contract as mc
import run_it
import sportsedge_nba_model as frozen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FROZEN = HERE / "sportsedge_nba_model.py"

T1 = "2026-11-15T12:00:00-05:00"   # before tip (G1 21:00 ET, G2 19:30 ET)
T2 = "2026-11-15T13:00:00-05:00"
AS_OF = datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc).astimezone()  # 14:00Z = 09:00 ET
AS_OF = datetime.fromisoformat("2026-11-15T14:00:00-05:00")

GAMES = [dict(game_id="G1", date="2026-11-15", tipoff_et="21:00", home="DEN", away="LAL"),
         dict(game_id="G2", date="2026-11-15", tipoff_et="19:30", home="BOS", away="MIA")]
TEAMS = [dict(team=t) for t in ("DEN", "LAL", "BOS", "MIA")]
EVENTS = mc.build_events(GAMES, TEAMS)


def blob_sha1(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()


def row(gid, market, sel, price, line="", cid="C1", at=T1, **extra):
    r = dict(game_id=gid, market=market, selection=sel, line=line, price=str(price), capture_id=cid, captured_at=at)
    r.update(extra)
    return r


def pair(gid="G1", market="1H_ML", a="DEN", b="LAL", pa=-135, pb=115, la="", lb="", **kw):
    return [row(gid, market, a, pa, la, **kw), row(gid, market, b, pb, lb, **kw)]


def v(rows, events=EVENTS, kind="csv", board=None, as_of=AS_OF):
    return mc.validate_odds(rows, events, as_of=as_of, board=board, source_kind=kind)


def codes(out):
    return {r["reason_code"] for r in out["rejected"]}


class FrozenFileUntouched(unittest.TestCase):
    def test_frozen_model_blob_is_unchanged(self):
        self.assertEqual(blob_sha1(FROZEN), mc.FROZEN_BLOB)


class P0_1_EventIdentity(unittest.TestCase):
    def test_unknown_event_rejected(self):
        out = v(pair(gid="G9"))
        self.assertEqual(out["accepted"], [])
        self.assertEqual(codes(out), {"UNKNOWN_EVENT"})

    def test_missing_games_file_rejects_everything(self):
        out = v(pair(), events=mc.build_events([], TEAMS))
        self.assertEqual((out["accepted"], codes(out)), ([], {"UNKNOWN_EVENT"}))

    def test_unknown_team_selections_cannot_pass_two_way_ml(self):
        for market in ("ML", "1H_ML", "1Q_ML"):
            out = v(pair(market=market, a="AAA", b="BBB"))
            self.assertEqual((out["accepted"], codes(out)), ([], {"SELECTION_NOT_EVENT_TEAM"}), market)

    def test_one_real_team_and_one_unknown_team_rejected(self):
        out = v(pair(a="DEN", b="MIA"))
        self.assertEqual((out["accepted"], codes(out)), ([], {"SELECTION_NOT_EVENT_TEAM"}))

    def test_selection_is_canonicalized_not_forwarded_raw(self):
        out = v([row(" G1 ", " 1h_ml ", " den ", "-135"), row("G1", "1H_ML", "lal", "115")])
        self.assertEqual([(r["market"], r["selection"], r["price"]) for r in out["accepted"]],
                         [("1H_ML", "DEN", "-135"), ("1H_ML", "LAL", "115")])

    def test_conflicting_duplicate_event_rows_poison_the_event(self):
        games = GAMES + [dict(game_id="G1", date="2026-11-15", tipoff_et="21:00", home="LAL", away="DEN")]
        ev = mc.build_events(games, TEAMS)
        out = v(pair(), events=ev)
        self.assertEqual((out["accepted"], codes(out)), ([], {"CONFLICTING_EVENT_BINDING"}))

    def test_bad_event_identity_rejected(self):
        for home, away in (("", "LAL"), ("DEN", ""), ("DEN", "DEN"), ("den", "LAL"), ("D_N", "LAL")):
            games = [dict(game_id="G1", date="2026-11-15", tipoff_et="21:00", home=home, away=away)]
            out = v(pair(), events=mc.build_events(games, TEAMS))
            self.assertEqual((out["accepted"], codes(out)), ([], {"INVALID_EVENT_IDENTITY"}), (home, away))

    def test_event_without_unique_ratings_is_not_priceable(self):
        for teams in ([dict(team="DEN")], TEAMS + [dict(team="DEN")]):
            out = v(pair(), events=mc.build_events(GAMES, teams))
            self.assertEqual((out["accepted"], codes(out)), ([], {"EVENT_NOT_PRICEABLE"}))

    def test_load_board_without_games_rejects_all(self):
        out = mc.load_board({"odds_rows": pair(), "teams_rows": TEAMS}, source_kind="csv", as_of=AS_OF)
        self.assertEqual((out["accepted"], codes(out)), ([], {"UNKNOWN_EVENT"}))


class P0_2_SpreadComplement(unittest.TestCase):
    def sp(self, la, lb, market="SPREAD"):
        return v(pair(market=market, pa=-110, pb=-110, la=la, lb=lb))

    def test_identical_signs_rejected(self):
        for market in ("SPREAD", "1H_SPREAD", "1Q_SPREAD"):
            for la, lb in (("-5", "-5"), ("5", "5"), ("-5.5", "-5.5")):
                out = self.sp(la, lb, market)
                self.assertEqual((out["accepted"], codes(out)), ([], {"SPREAD_LINES_NOT_COMPLEMENTARY"}), (market, la, lb))

    def test_unequal_magnitude_rejected(self):
        out = self.sp("-5", "4.5")
        self.assertEqual(out["accepted"], [])
        self.assertTrue(codes(out) <= {"SPREAD_LINES_NOT_COMPLEMENTARY", "INCOMPLETE_TWO_WAY"})

    def test_complementary_spread_accepted(self):
        out = self.sp("-5.5", "5.5")
        self.assertEqual([r["line"] for r in out["accepted"]], ["-5.5", "5.5"])
        out = self.sp("0", "0")
        self.assertEqual(len(out["accepted"]), 2)

    def test_spread_requires_finite_on_grid_lines(self):
        for la, lb, code in (("", "", "INVALID_LINE"), ("abc", "abc", "INVALID_LINE"), ("nan", "nan", "INVALID_LINE"),
                             ("inf", "-inf", "INVALID_LINE"), ("-5.25", "5.25", "LINE_OFF_GRID")):
            out = self.sp(la, lb)
            self.assertEqual(out["accepted"], [], (la, lb))
            self.assertIn(code, codes(out), (la, lb))

    def test_moneyline_must_not_carry_a_line(self):
        out = v(pair(la="1.5", lb="1.5"))
        self.assertEqual((out["accepted"], codes(out)), ([], {"INVALID_LINE"}))

    def test_opposite_signed_pairs_sharing_abs_line_cannot_collide_in_frozen_pairing(self):
        rows = pair(market="SPREAD", pa=-110, pb=-110, la="-5", lb="5") + \
            pair(market="SPREAD", pa=-110, pb=-110, la="5", lb="-5")
        out = v(rows)
        self.assertEqual((out["accepted"], codes(out)), ([], {"DUPLICATE_SELECTION"}))


class P0_3_TeamTotals(unittest.TestCase):
    def tt(self, market, line="112.5"):
        return v(pair(market=market, a="OVER", b="UNDER", pa=-110, pb=-110, la=line, lb=line))

    def test_unknown_team_total_team_rejected(self):
        for market in ("TT_XYZ", "1H_TT_XYZ", "TT_BOS"):  # BOS is not in G1
            out = self.tt(market)
            self.assertEqual((out["accepted"], codes(out)), ([], {"UNKNOWN_TEAM_TOTAL_TEAM"}), market)

    def test_malformed_team_total_names_rejected(self):
        for market in ("TT_", "TT_DEN_X", "XTT_DEN", "TT", "TT_den_", "TEAM_TOTAL_DEN"):
            out = self.tt(market)
            self.assertEqual(out["accepted"], [], market)
            self.assertTrue(codes(out) <= {"UNKNOWN_MARKET"}, (market, codes(out)))

    def test_known_team_totals_accepted_and_canonicalized(self):
        for market in ("TT_DEN", "TT_LAL", "1H_TT_LAL", "1Q_TT_DEN"):
            out = self.tt(market)
            self.assertEqual(len(out["accepted"]), 2, market)
        out = self.tt("tt_den")
        self.assertEqual({r["market"] for r in out["accepted"]}, {"TT_DEN"})

    def test_team_total_over_under_must_match(self):
        out = v(pair(market="TT_DEN", a="OVER", b="UNDER", pa=-110, pb=-110, la="112.5", lb="113.5"))
        self.assertEqual(out["accepted"], [])


class P0_4_PlayerProps(unittest.TestCase):
    PLAYERS = [dict(player="Big D5", team="DEN"), dict(player="Guard L1", team="LAL"),
               dict(player="Twin", team="DEN"), dict(player="Twin", team="DEN")]

    def pv(self, **kw):
        base = dict(game_id="G1", player="Big D5", team="DEN", stat="PTS", line="26.5", over_price="-105",
                    under_price="-105", capture_id="C1", captured_at=T1)
        base.update(kw)
        return mc.validate_props([base], EVENTS, self.PLAYERS, as_of=AS_OF, source_kind="csv")

    def test_valid_prop_accepted_and_canonical(self):
        out = self.pv(stat="pts")
        self.assertEqual(len(out["accepted"]), 1)
        self.assertEqual((out["accepted"][0]["stat"], out["accepted"][0]["line"]), ("PTS", "26.5"))

    def test_bad_props_rejected_with_reason(self):
        cases = [(dict(game_id="G9"), "UNKNOWN_EVENT"), (dict(stat="STL"), "PROP_UNSUPPORTED_STAT"),
                 (dict(team=""), "PROP_TEAM_NOT_EVENT_TEAM"), (dict(team="BOS"), "PROP_TEAM_NOT_EVENT_TEAM"),
                 (dict(player="Nobody"), "PROP_UNKNOWN_PLAYER"), (dict(player="Guard L1"), "PROP_UNKNOWN_PLAYER"),
                 (dict(player="Twin"), "PROP_UNKNOWN_PLAYER"), (dict(player_id="X1"), "PROP_UNKNOWN_PLAYER"),
                 (dict(over_price="-105.5"), "ODDS_MALFORMED_OR_FRACTIONAL"), (dict(under_price="1.91"), "ODDS_MALFORMED_OR_FRACTIONAL"),
                 (dict(line="26.25"), "LINE_OFF_GRID"), (dict(line="abc"), "INVALID_LINE"), (dict(line="0"), "INVALID_LINE"),
                 (dict(over_price="110", under_price="110"), "INCOHERENT_TWO_SIDED_PRICES"),
                 (dict(capture_id="", captured_at=""), "MISSING_CAPTURE_PROVENANCE"),
                 (dict(captured_at="2026-11-15T12:00:00"), "CHRONOLOGY_INVALID"),
                 (dict(captured_at="2026-11-15T21:30:00-05:00"), "QUOTE_AFTER_TIP")]
        for patch_, code in cases:
            out = self.pv(**patch_)
            self.assertEqual(out["accepted"], [], patch_)
            self.assertEqual({r["reason_code"] for r in out["rejected"]}, {code}, patch_)

    def test_duplicate_prop_in_same_capture_rejected(self):
        base = dict(game_id="G1", player="Big D5", team="DEN", stat="PTS", line="26.5", over_price="-105",
                    under_price="-105", capture_id="C1", captured_at=T1)
        out = mc.validate_props([dict(base), dict(base)], EVENTS, self.PLAYERS, as_of=AS_OF, source_kind="csv")
        self.assertEqual((out["accepted"], {r["reason_code"] for r in out["rejected"]}), ([], {"PROP_DUPLICATE"}))

    def test_props_do_not_bypass_the_guard_in_run_guarded(self):
        """Invalid props never reach frozen price_props; only validated prop rows do."""
        seen = []
        orig = frozen.price_props

        def spy(data, players):
            seen.extend(dict(r) for r in data["props"])
            return orig(data, players)

        good = dict(game_id="G1", player="Big D5", team="DEN", stat="PTS", line="26.5", over_price="-105",
                    under_price="-105")
        bad = [dict(good, player="Nobody"), dict(good, over_price="-105.5"), dict(good, stat="STL"),
               dict(good, team="BOS")]
        with tempfile.TemporaryDirectory() as tmp, patch.object(frozen, "price_props", side_effect=spy):
            inputs = sample_inputs(tmp)
            inputs["props_rows"] = [good] + bad
            res = mc.run_guarded(inputs, os.path.join(tmp, "out"), source_kind="csv", as_of=AS_OF)
        self.assertEqual(res["status"], "PRICED")
        self.assertEqual([(r["player"], r["stat"], r["over_price"]) for r in seen], [("Big D5", "PTS", "-105")])
        self.assertEqual(len([r for r in res["rejected"] if r["record_type"] == "prop"]), 4)


class P0_5_Captures(unittest.TestCase):
    def test_pair_split_across_captures_is_never_paired(self):
        rows = [row("G1", "1H_ML", "DEN", -135, cid="C1", at=T1), row("G1", "1H_ML", "LAL", 115, cid="C2", at=T2)]
        out = v(rows)
        self.assertEqual((out["accepted"], codes(out)), ([], {"INCOMPLETE_TWO_WAY"}))

    def test_same_capture_id_different_timestamps_not_paired(self):
        rows = [row("G1", "1H_ML", "DEN", -135, at=T1), row("G1", "1H_ML", "LAL", 115, at=T2)]
        out = v(rows)
        self.assertEqual((out["accepted"], codes(out)), ([], {"INCOMPLETE_TWO_WAY"}))

    def test_newest_complete_capture_wins_older_is_ledgered(self):
        rows = pair(pa=-135, pb=115, cid="C1", at=T1) + pair(pa=-150, pb=130, cid="C2", at=T2)
        out = v(rows)
        self.assertEqual({(r["selection"], r["price"], r["capture_id"]) for r in out["accepted"]},
                         {("DEN", "-150", "C2"), ("LAL", "130", "C2")})
        self.assertEqual(codes(out), {"SUPERSEDED_BY_LATER_CAPTURE"})

    def test_equal_timestamp_different_captures_is_ambiguous(self):
        rows = pair(pa=-135, pb=115, cid="C1", at=T1) + pair(pa=-150, pb=130, cid="C2", at=T1)
        out = v(rows)
        self.assertEqual((out["accepted"], codes(out)), ([], {"AMBIGUOUS_CAPTURE_TIE"}))

    def test_missing_provenance_rejected_and_board_provenance_fills_gaps(self):
        rows = [dict(r, capture_id="", captured_at="") for r in pair()]
        out = v(rows)
        self.assertEqual((out["accepted"], codes(out)), ([], {"MISSING_CAPTURE_PROVENANCE"}))
        out = v(rows, board={"capture_id": "B1", "captured_at": T1})
        self.assertEqual({r["capture_id"] for r in out["accepted"]}, {"B1"})

    def test_chronology_checks(self):
        for at, code in (("2026-11-15T12:00:00", "CHRONOLOGY_INVALID"), ("garbage", "CHRONOLOGY_INVALID"),
                         ("2026-11-15T21:00:00-05:00", "QUOTE_AFTER_TIP"),
                         ("2026-11-15T23:00:00-05:00", "QUOTE_AFTER_TIP"),
                         ("2026-11-15T16:00:00-05:00", "QUOTE_FROM_FUTURE")):
            out = v(pair(at=at))
            self.assertEqual((out["accepted"], codes(out)), ([], {code}), at)

    def test_unverifiable_tipoff_rejected(self):
        games = [dict(game_id="G1", date="2026-11-15", tipoff_et="soon", home="DEN", away="LAL")]
        out = v(pair(), events=mc.build_events(games, TEAMS))
        self.assertEqual((out["accepted"], codes(out)), ([], {"TIPOFF_UNVERIFIABLE"}))

    def test_period_field_conflict_rejected(self):
        for field in ("1Q", "2H", "FG"):
            out = v(pair(market="1H_ML", period=field))
            self.assertEqual((out["accepted"], codes(out)), ([], {"PERIOD_FIELD_CONFLICT"}), field)
        self.assertEqual(len(v(pair(market="1H_ML", period="1H"))["accepted"]), 2)
        self.assertEqual(len(v(pair(market="ML", period=""))["accepted"]), 2)

    def test_partial_invalid_group_fails_whole_contract(self):
        rows = [row("G1", "1H_ML", "DEN", -135), row("G1", "1H_ML", "LAL", "115.5")]
        out = v(rows)
        self.assertEqual(out["accepted"], [])
        self.assertEqual(len(out["rejected"]), 2)
        rows = [row("G1", "1H_ML", "DEN", -135), row("G1", "1H_ML", "LAL", "")]
        out = v(rows)
        self.assertEqual(out["accepted"], [])
        self.assertEqual(len(out["rejected"]), 2)


class P1_7_StrictOddsAndLines(unittest.TestCase):
    BAD = ["-110.5", "150.5", "1.91", "2.5", "5/2", "EVEN", "abc", "nan", "inf", "-inf", "99", "-99", "0",
           "+-110", "--110", "1,50"]

    def test_parse_american_price(self):
        for ok, want in (("-110", -110), ("+150", 150), (-110, -110), (150.0, 150), ("-110.0", -110), (100, 100)):
            self.assertEqual(mc.parse_american_price(ok), want, ok)
        for bad in self.BAD + ["", None, True, False, float("nan"), float("inf"), -110.5, 1.91, 99]:
            self.assertIsNone(mc.parse_american_price(bad), repr(bad))

    def test_each_bad_price_rejects_the_whole_contract_every_market_type(self):
        for bad in self.BAD:
            for market, kw in (("ML", {}), ("1H_ML", {}), ("1Q_ML", {}),
                               ("TOTAL", dict(a="OVER", b="UNDER", la="220.5", lb="220.5")),
                               ("TT_DEN", dict(a="OVER", b="UNDER", la="112.5", lb="112.5")),
                               ("SPREAD", dict(la="-3.5", lb="3.5"))):
                rows = pair(market=market, pa=bad, **kw)
                out = v(rows)
                self.assertEqual(out["accepted"], [], (bad, market))
                self.assertIn("ODDS_MALFORMED_OR_FRACTIONAL", codes(out), (bad, market))
                self.assertEqual(len(out["rejected"]), 2)

    def test_incoherent_two_sided_prices_rejected(self):
        for pa, pb in ((110, 110), (-120, 120), (200, 150), (-1000, -1000)):
            out = v(pair(pa=pa, pb=pb))
            self.assertEqual((out["accepted"], codes(out)), ([], {"INCOHERENT_TWO_SIDED_PRICES"}), (pa, pb))

    def test_whole_number_prices_accepted(self):
        for price in ("-110", "+115", 115, "115.0", "100"):
            self.assertEqual(len(v(pair(pa=-135, pb=price))["accepted"]), 2, price)

    def test_total_lines(self):
        for la, lb in (("abc", "abc"), ("nan", "nan"), ("220.25", "220.25"), ("0", "0"), ("-220.5", "-220.5")):
            out = v(pair(market="TOTAL", a="OVER", b="UNDER", pa=-110, pb=-110, la=la, lb=lb))
            self.assertEqual(out["accepted"], [], (la, lb))

    def test_tie_three_way_duplicate_missing_unsupported(self):
        cases = [
            ([row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "TIE", 1000)], "TIE_OR_DRAW_IN_TWO_WAY_ML"),
            ([row("G1", "1Q_ML", "DEN", -120), row("G1", "1Q_ML", "DRAW", 800)], "TIE_OR_DRAW_IN_TWO_WAY_ML"),
            ([row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "LAL", 210), row("G1", "1H_ML", "TIE", 900)],
             "THREE_WAY_ML_UNSUPPORTED"),
            ([row("G1", "1H_ML_3WAY", "DEN", -120), row("G1", "1H_ML_3WAY", "LAL", 210)], "THREE_WAY_ML_UNSUPPORTED"),
            ([row("G1", "ML", "DEN", -160)], "INCOMPLETE_TWO_WAY"),
            ([row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "DEN", -125)], "DUPLICATE_SELECTION"),
            ([row("G1", "TOTAL", "OVER", -110, "220.5")], "INCOMPLETE_TWO_WAY"),
            ([row("G1", "1H/1Q_ML", "DEN", -120), row("G1", "1H/1Q_ML", "LAL", 110)], "MIXED_PERIOD_CONTRACT"),
            ([row("G1", "FUTURES", "DEN", -120), row("G1", "FUTURES", "LAL", 110)], "UNKNOWN_MARKET"),
        ]
        for rows, code in cases:
            out = v(rows)
            self.assertEqual((out["accepted"], codes(out)), ([], {code}), rows[0]["market"])
        for market in ("2H_ML", "2Q_ML", "3Q_ML", "4Q_ML", "2H_TOTAL", "3Q_SPREAD"):
            out = v(pair(market=market))
            self.assertEqual((out["accepted"], codes(out)), ([], {"UNSUPPORTED_PERIOD_MARKET"}), market)

    def test_every_period_and_market_type_is_priced_or_reason_coded(self):
        for period in ("", "1H", "2H", "1Q", "2Q", "3Q", "4Q"):
            pre = period + "_" if period else ""
            cases = [pair(market=pre + "ML"),
                     pair(market=pre + "SPREAD", pa=-110, pb=-110, la="-3.5", lb="3.5"),
                     pair(market=pre + "TOTAL", a="OVER", b="UNDER", pa=-110, pb=-110, la="220.5", lb="220.5"),
                     pair(market=pre + "TT_DEN", a="OVER", b="UNDER", pa=-110, pb=-110, la="112.5", lb="112.5")]
            for rows in cases:
                out = v(rows)
                if period in ("", "1H", "1Q"):
                    self.assertEqual((len(out["accepted"]), out["rejected"]), (2, []), rows[0]["market"])
                else:
                    self.assertEqual((out["accepted"], codes(out)), ([], {"UNSUPPORTED_PERIOD_MARKET"}), rows[0]["market"])


def sample_inputs(tmp: str) -> dict:
    """Synthetic frozen-fixture inputs with board-level provenance. Fixture data, not live eligibility."""
    dest = Path(tmp) / "sample"
    dest.mkdir()
    prev = make_samples.OUT
    make_samples.OUT = str(dest)
    try:
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            make_samples.main()
    finally:
        make_samples.OUT = prev
    inputs = {n: str(dest / (n + ".csv")) for n in
              ("teams", "games", "injuries", "players", "positional_defense", "odds", "props")}
    inputs.update(capture_id="FIXTURE-1", captured_at=T1)
    return inputs


class RealPricerIntegration(unittest.TestCase):
    def test_valid_fixture_board_prices_and_outputs_are_labelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = sample_inputs(tmp)
            res = mc.run_guarded(inputs, os.path.join(tmp, "out"), source_kind="csv", as_of=AS_OF)
            self.assertEqual(res["status"], "PRICED")
            self.assertGreater(len(res["picks"]), 0)
            rows = list(csv.DictReader(open(res["csv"], newline="")))
            self.assertTrue(rows)
            for r in rows:
                self.assertEqual((r["release"], r["status"], r["official_counted"], r["approved_stake_u"]),
                                 ("PAPER_0U", "NON_COUNTED", "0", "0"))
            md = open(res["md"]).read()
            self.assertTrue(md.startswith("> **PAPER_0U / NON_COUNTED"))
            man = json.load(open(res["manifest"]))
            self.assertEqual((man["status"], man["official_counted"], man["frozen_model_blob"]),
                             ("PRICED", 0, mc.FROZEN_BLOB))
            for name, digest in man["files_sha256"].items():
                self.assertEqual(mc.sha256_file(os.path.join(res["run_dir"], name)), digest, name)

    def test_bad_rows_in_a_real_board_never_reach_price_game_market(self):
        seen = []
        orig = frozen.price_game_market

        def spy(r, proj):
            seen.append(dict(r))
            return orig(r, proj)

        with tempfile.TemporaryDirectory() as tmp:
            inputs = sample_inputs(tmp)
            rows = mc.read_csv_rows(inputs["odds"])
            bad = (pair(market="1H_ML", a="DEN", b="TIE", pa=-120, pb=1000)
                   + pair(market="1Q_ML", pa="-110.5")
                   + pair(market="SPREAD", pa=-110, pb=-110, la="-5", lb="-5")
                   + pair(market="TT_XYZ", a="OVER", b="UNDER", pa=-110, pb=-110, la="112.5", lb="112.5")
                   + pair(gid="G9") + pair(market="2H_ML") + pair(market="1H_ML", cid="C9", at=T1)[:1])
            inputs["odds_rows"] = rows + bad
            with patch.object(frozen, "price_game_market", side_effect=spy):
                res = mc.run_guarded(inputs, os.path.join(tmp, "out"), source_kind="csv", as_of=AS_OF)
            ledger = list(csv.DictReader(open(res["ledger"], newline="")))
        self.assertEqual(res["status"], "PRICED")
        priced = {(r["game_id"], r["market"], r["selection"].upper(), r["line"], r["price"]) for r in seen}
        self.assertTrue(priced)
        accepted = {(r["game_id"], r["market"], r["selection"], r["line"], r["price"]) for r in res["accepted"]}
        self.assertEqual(priced, accepted)
        for r in seen:
            self.assertNotIn(r["selection"].upper(), mc.TIE_SELECTIONS)
            self.assertNotIn(r["game_id"], {"G9"})
            self.assertNotIn(r["market"], {"2H_ML", "TT_XYZ"})
        self.assertGreaterEqual(len(res["rejected"]), 10)
        self.assertEqual(len(ledger), len(res["rejected"]))
        self.assertTrue(all(r["reason_code"] and r["reason"] for r in ledger))

    def test_zero_invalid_contracts_reach_pricing_on_every_source_kind(self):
        hook_seen = []
        orig_pgm, orig_pp = frozen.price_game_market, frozen.price_props
        seen_odds, seen_props = [], []

        def spy_m(r, proj):
            seen_odds.append(dict(r))
            return orig_pgm(r, proj)

        def spy_p(data, players):
            seen_props.extend(dict(x) for x in data["props"])
            return orig_pp(data, players)

        bad_props = [dict(game_id="G1", player="Nobody", team="DEN", stat="PTS", line="1.5", over_price="-105",
                          under_price="-105")]
        bad_odds = (pair(market="1H_ML", a="DEN", b="TIE", pa=-120, pb=1000) + pair(market="ML", pa="1.91")
                    + pair(market="SPREAD", pa=-110, pb=-110, la="-5", lb="-5") + pair(gid="G9"))
        for kind in sorted(mc.SOURCE_KINDS):
            seen_odds.clear(); seen_props.clear()
            with tempfile.TemporaryDirectory() as tmp, patch.object(frozen, "price_game_market", side_effect=spy_m), \
                    patch.object(frozen, "price_props", side_effect=spy_p):
                inputs = {"games_rows": GAMES, "teams_rows": TEAMS, "odds_rows": bad_odds, "props_rows": bad_props,
                          "capture_path": "/tmp/capture"}
                res = run_it.run_from_inputs(inputs, tmp, source_kind=kind, as_of=AS_OF)
            self.assertEqual(res["status"], "NO_ELIGIBLE_CONTRACTS", kind)
            self.assertEqual((seen_odds, seen_props, res["picks"], res["accepted"]), ([], [], [], []), kind)

    def test_pdf_and_screenshot_without_structured_rows_fail_closed(self):
        for kind in ("pdf", "screenshot"):
            out = mc.load_board({"capture_path": "/tmp/board.png", "games_rows": GAMES, "teams_rows": TEAMS},
                                source_kind=kind, as_of=AS_OF)
            self.assertEqual((out["accepted"], codes(out)), ([], {"SOURCE_ROWS_MISSING"}))
        out = mc.load_board({"odds_rows": pair(a="DEN", b="TIE", pa=-120, pb=1000), "games_rows": GAMES,
                             "teams_rows": TEAMS}, source_kind="pdf", as_of=AS_OF)
        self.assertEqual((out["accepted"], codes(out)), ([], {"TIE_OR_DRAW_IN_TWO_WAY_ML"}))

    def test_invalid_source_kind_rejected(self):
        out = mc.load_board({"odds_rows": pair(), "games_rows": GAMES, "teams_rows": TEAMS},
                            source_kind="carrier_pigeon", as_of=AS_OF)
        self.assertEqual(out["accepted"], [])
        self.assertIn("SOURCE_KIND_INVALID", codes(out))

    def test_refuses_to_price_if_frozen_blob_changes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(mc, "FROZEN_BLOB", "0" * 40):
            res = mc.run_guarded(sample_inputs(tmp), os.path.join(tmp, "out"), source_kind="csv", as_of=AS_OF)
        self.assertEqual((res["status"], res["picks"]), ("FROZEN_MODEL_CHANGED", []))
        self.assertIn("FROZEN_MODEL_CHANGED", codes(res))


class P1_8_ConcurrencyAndCli(unittest.TestCase):
    def test_concurrent_runs_use_unique_workspaces_and_never_overwrite(self):
        results, errors = {}, []
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "out")
            base = sample_inputs(tmp)
            base_rows = mc.read_csv_rows(base["odds"])

            def work(i):
                try:
                    inputs = dict(base)
                    # each thread gets a distinguishable board: a different G1 ML price
                    rows = [dict(r) for r in base_rows]
                    for r in rows:
                        if r["game_id"] == "G1" and r["market"] == "ML" and r["selection"] == "DEN":
                            r["price"] = str(-150 - i)
                    inputs["odds_rows"] = rows
                    results[i] = mc.run_guarded(inputs, out_dir, source_kind="csv", as_of=AS_OF)
                except Exception as exc:  # pragma: no cover
                    errors.append(repr(exc))

            threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            self.assertEqual(errors, [])
            self.assertEqual(len({r["run_dir"] for r in results.values()}), 8)
            for i, r in results.items():
                rows = mc.read_csv_rows(os.path.join(r["run_dir"], "_accepted_odds.csv"))
                den = [x for x in rows if x["game_id"] == "G1" and x["market"] == "ML" and x["selection"] == "DEN"]
                self.assertEqual([x["price"] for x in den], [str(-150 - i)], i)
                man = json.load(open(r["manifest"]))
                for name, digest in man["files_sha256"].items():
                    self.assertEqual(mc.sha256_file(os.path.join(r["run_dir"], name)), digest)
            leftovers = [p for p in Path(out_dir).rglob(".tmp-*")]
            self.assertEqual(leftovers, [])
            self.assertFalse((Path(out_dir) / "_accepted_odds.csv").exists())

    def test_atomic_write_leaves_no_partial_file_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "x.csv")
            mc.atomic_write(target, "a\n")
            with patch("os.replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    mc.atomic_write(target, "b\n")
            self.assertEqual(open(target).read(), "a\n")
            self.assertEqual([p for p in os.listdir(tmp) if p.startswith(".tmp-")], [])

    def test_cli_exit_status_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = sample_inputs(tmp)
            d = str(Path(inputs["odds"]).parent)
            common = ["--source-kind", "csv", "--inputs", d, "--capture-id", "FIXTURE-1", "--captured-at", T1,
                      "--as-of", "2026-11-15T14:00:00-05:00"]
            self.assertEqual(run_it.main(common + ["--out", os.path.join(tmp, "o1")]), 0)
            empty = Path(tmp) / "empty_odds.csv"
            empty.write_text("game_id,market,selection,line,price\n")
            self.assertEqual(run_it.main(common + ["--odds", str(empty), "--props", str(empty), "--out", os.path.join(tmp, "o2")]), 3)
            tie = Path(tmp) / "tie.csv"
            with open(tie, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["game_id", "market", "selection", "line", "price"])
                w.writeheader()
                w.writerows([dict(game_id="G1", market="1H_ML", selection="DEN", line="", price="-120"),
                             dict(game_id="G1", market="1H_ML", selection="TIE", line="", price="1000")])
            self.assertEqual(run_it.main(common + ["--odds", str(tie), "--props", str(empty), "--out", os.path.join(tmp, "o3")]), 3)
            self.assertEqual(run_it.main(["--source-kind", "pdf", "--inputs", d, "--odds", str(empty),
                                          "--props", str(empty), "--as-of", "nope", "--out", os.path.join(tmp, "o4")]), 2)
            # no-eligible runs still persist the ledger and a manifest
            run_dirs = list((Path(tmp) / "o3" / "runs").iterdir())
            self.assertEqual(len(run_dirs), 1)
            self.assertTrue((run_dirs[0] / "nba_rejected_markets.csv").exists())
            man = json.load(open(run_dirs[0] / "run_manifest.json"))
            self.assertEqual((man["status"], man["official_counted"], man["release"]),
                             ("NO_ELIGIBLE_CONTRACTS", 0, "PAPER_0U"))


class P0_6_OperationalCallerCensus(unittest.TestCase):
    """No operational Python module, script, workflow or CLI may reach frozen pricing unguarded.
    The frozen functions (including the frozen __main__) remain only for frozen regression fixtures."""

    FROZEN_REGRESSION_FILES = {
        "models/nba/sportsedge_nba_model.py",
        "models/nba/test_sportsedge_nba_model.py",
        "models/nba/test_period_ml_settlement.py",
        "models/nba/test_nba_event_identity.py",
        "models/nba/test_market_contract.py",
        # explicit frozen-quote regression fixture (not an operational caller)
        "research/audits/test_multisport_quote_ev_regressions.py",
    }
    GUARD_FILES = {"models/nba/market_contract.py", "models/nba/run_it.py"}
    PRICING_NAMES = {"price_game_market", "price_games", "run_card", "price_props", "novig"}
    SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__"}

    def _py_files(self):
        for path in ROOT.rglob("*.py"):
            if self.SKIP_PARTS & set(path.parts):
                continue
            yield str(path.relative_to(ROOT)).replace("\\", "/"), path

    def test_every_python_module_touching_nba_pricing_is_guard_or_frozen_regression(self):
        import ast
        offenders = []
        for rel, path in self._py_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            if "sportsedge_nba_model" not in text:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            used = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in self.PRICING_NAMES:
                    used.add(node.attr)
                if isinstance(node, ast.Name) and node.id in self.PRICING_NAMES:
                    used.add(node.id)
                if isinstance(node, ast.ImportFrom) and node.module and "sportsedge_nba_model" in node.module:
                    used |= {a.name for a in node.names if a.name in self.PRICING_NAMES or a.name == "*"}
            if used and rel not in self.FROZEN_REGRESSION_FILES | self.GUARD_FILES:
                offenders.append((rel, sorted(used)))
        self.assertEqual(offenders, [], "operational callers reach frozen pricing unguarded: %r" % offenders)

    def test_guard_modules_use_frozen_pricing_only_after_validation(self):
        text = (HERE / "market_contract.py").read_text()
        self.assertEqual(text.count("frozen.run_card("), 1)
        self.assertLess(text.index("def load_board"), text.index("frozen.run_card("))
        self.assertLess(text.index("blob_sha1(frozen_path) == FROZEN_BLOB"), text.index("frozen.run_card("))
        self.assertNotIn("price_game_market(", text)
        self.assertIsNone(re.search(r"^\s*(import|from)\s+sportsedge_nba_model", (HERE / "run_it.py").read_text(), re.M))

    def test_only_the_frozen_file_has_a_main_that_prices(self):
        offenders = []
        for rel, path in self._py_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            if "__main__" in text and "sportsedge_nba_model" in text and "run_card" in text \
                    and rel not in self.FROZEN_REGRESSION_FILES | self.GUARD_FILES:
                offenders.append(rel)
        self.assertEqual(offenders, [])

    def test_no_workflow_script_or_doc_runner_invokes_the_frozen_pricer_cli(self):
        direct = re.compile(r"python3?\s+(?:-\S+\s+)*(?:\S*/)?sportsedge_nba_model(?:\.py)?(?:\s|$)")
        module = re.compile(r"python3?\s+-m\s+(?:\S+\.)?sportsedge_nba_model\b")
        offenders = []
        files = list((ROOT / ".github" / "workflows").glob("*.yml")) + list(ROOT.glob("*.sh")) + \
            list(ROOT.glob("Makefile")) + list((ROOT / "tools").glob("*.sh")) + list((ROOT / "scripts").glob("*.sh"))
        for f in files:
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                s = line.strip()
                if not s.startswith("#") and (direct.search(s) or module.search(s)):
                    offenders.append((str(f.relative_to(ROOT)), n, s))
        self.assertEqual(offenders, [], "workflows/scripts must use models/nba/run_it.py: %r" % offenders)

    def test_guarded_registry_and_cli_are_importable_and_cover_all_source_kinds(self):
        self.assertEqual(set(run_it.SOURCE_KINDS), set(mc.SOURCE_KINDS))
        self.assertEqual(mc.SOURCE_KINDS, {"dk_capture", "pdf", "screenshot", "csv", "manual", "replay"})
        for entry in mc.GUARDED_ENTRY_POINTS:
            rel, name = entry.split(":")
            self.assertIn(f"def {name}", (ROOT / rel).read_text(), entry)
        for entry in mc.FROZEN_REGRESSION_ONLY:
            rel, name = entry.split(":")
            self.assertTrue((ROOT / rel).exists(), entry)

    def test_run_card_guarded_alias_is_the_guard(self):
        self.assertIs(mc.run_card_guarded, mc.run_guarded)


class FrozenBehaviorUnchanged(unittest.TestCase):
    def test_unguarded_frozen_run_still_prices_home_plus_tie(self):
        """Documents the defect the guard isolates. The frozen function is regression-only; do not 'fix' it here."""
        proj = {"margin": 3.0, "total": 225.0, "home": "H", "away": "A", "home_pts": 114.0, "away_pts": 111.0,
                "game_id": "G", "inputs": ""}
        rows = [{"game_id": "G", "market": "1H_ML", "selection": "H", "line": "", "price": "-120"},
                {"game_id": "G", "market": "1H_ML", "selection": "TIE", "line": "", "price": "+1000"}]
        priced = frozen.price_games({"odds": [dict(r) for r in rows]}, {"G": proj})
        self.assertEqual([p["selection"] for p in priced], ["H", "TIE"])


if __name__ == "__main__":
    unittest.main()
