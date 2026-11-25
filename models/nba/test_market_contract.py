"""Adversarial and entry-point tests for the NBA market-contract ingestion guard.

The frozen model file is never edited. These tests prove invalid contracts are
rejected with a reason code and do not reach price_game_market through any
guarded runner entry point.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import market_contract as mc
import run_it
import sportsedge_nba_model as frozen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # models/nba -> repo root
FROZEN = HERE / "sportsedge_nba_model.py"


def blob_sha1(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()


def row(gid, market, sel, price, line=""):
    return dict(game_id=gid, market=market, selection=sel, line=line, price=str(price))


def two_way_ml(gid="G1", market="1H_ML", home="DEN", away="LAL"):
    return [row(gid, market, home, -135), row(gid, market, away, 115)]


class FrozenFileUntouched(unittest.TestCase):
    def test_frozen_model_blob_is_unchanged(self):
        self.assertEqual(blob_sha1(FROZEN), mc.FROZEN_BLOB)


class AdversarialContracts(unittest.TestCase):
    def _codes(self, rows, **kw):
        out = mc.filter_odds(rows, **kw)
        return out, {r["reason_code"] for r in out["rejected"]}

    def test_home_plus_tie_only_is_rejected_and_not_accepted(self):
        rows = [row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "TIE", 1000)]
        out, codes = self._codes(rows, home_away={"G1": {"home": "DEN", "away": "LAL"}})
        self.assertEqual(out["accepted"], [])
        self.assertEqual(codes, {"TIE_OR_DRAW_IN_TWO_WAY_ML"})
        self.assertEqual(len(out["rejected"]), 2)

    def test_draw_alias_rejected(self):
        rows = [row("G1", "1Q_ML", "DEN", -120), row("G1", "1Q_ML", "DRAW", 800)]
        out, codes = self._codes(rows)
        self.assertEqual(out["accepted"], [])
        self.assertIn("TIE_OR_DRAW_IN_TWO_WAY_ML", codes)

    def test_three_way_rows_rejected(self):
        rows = [row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "LAL", 210),
                row("G1", "1H_ML", "TIE", 1000)]
        out, codes = self._codes(rows)
        self.assertEqual(out["accepted"], [])
        self.assertEqual(codes, {"THREE_WAY_ML_UNSUPPORTED"})

    def test_labelled_three_way_market_rejected(self):
        rows = [row("G1", "1H_ML_3WAY", "DEN", -120), row("G1", "1H_ML_3WAY", "LAL", 210)]
        out, codes = self._codes(rows)
        self.assertEqual(out["accepted"], [])
        self.assertEqual(codes, {"THREE_WAY_ML_UNSUPPORTED"})

    def test_missing_side_rejected(self):
        out, codes = self._codes([row("G1", "ML", "DEN", -160)])
        self.assertEqual(out["accepted"], [])
        self.assertEqual(codes, {"INCOMPLETE_TWO_WAY"})

    def test_duplicate_selection_rejected(self):
        rows = [row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "DEN", -125)]
        out, codes = self._codes(rows)
        self.assertEqual(out["accepted"], [])
        self.assertEqual(codes, {"DUPLICATE_SELECTION"})

    def test_mixed_periods_rejected(self):
        # Same group key cannot mix periods; use an explicit mixed market label.
        rows = [row("G1", "1H_ML", "DEN", -120), row("G1", "1Q_ML", "LAL", 110)]
        out = mc.filter_odds(rows)
        # These are two different markets; 1H_ML and 1Q_ML each missing a side.
        codes = {r["reason_code"] for r in out["rejected"]}
        self.assertEqual(out["accepted"], [])
        self.assertEqual(codes, {"INCOMPLETE_TWO_WAY"})
        # A single malformed market name that mixes periods:
        mixed = [row("G1", "1H/1Q_ML", "DEN", -120), row("G1", "1H/1Q_ML", "LAL", 110)]
        out, codes = self._codes(mixed)
        self.assertEqual(out["accepted"], [])
        self.assertEqual(codes, {"MIXED_PERIOD_CONTRACT"})

    def test_unsupported_quarter_or_second_half_rejected(self):
        for market in ("2H_ML", "2Q_ML", "3Q_ML", "4Q_ML"):
            out, codes = self._codes(two_way_ml(market=market))
            self.assertEqual(out["accepted"], [], market)
            self.assertEqual(codes, {"UNSUPPORTED_PERIOD_MARKET"}, market)

    def test_valid_two_way_accepted(self):
        for market in ("ML", "1H_ML", "1Q_ML"):
            out, _ = self._codes(two_way_ml(market=market),
                                 home_away={"G1": {"home": "DEN", "away": "LAL"}})
            self.assertEqual(len(out["accepted"]), 2, market)
            self.assertEqual(out["rejected"], [])

    def test_incomplete_total_and_spread(self):
        out, codes = self._codes([row("G1", "TOTAL", "OVER", -110, "220.5")])
        self.assertEqual(codes, {"INCOMPLETE_TWO_WAY"})
        out, codes = self._codes([row("G1", "SPREAD", "DEN", -110, "-3.5")])
        self.assertEqual(codes, {"INCOMPLETE_TWO_WAY"})

    def test_pdf_or_screenshot_without_extracted_rows_fails_closed(self):
        for kind in ("pdf", "screenshot"):
            out = mc.load_board({"capture_path": "/tmp/board.png"}, source_kind=kind)
            self.assertEqual(out["accepted"], [])
            self.assertEqual({r["reason_code"] for r in out["rejected"]}, {"SOURCE_ROWS_MISSING"})

    def test_pdf_with_extracted_rows_still_filters_tie_bug(self):
        rows = [row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "TIE", 1000)]
        out = mc.load_board({"odds_rows": rows, "capture_path": "/tmp/board.pdf"}, source_kind="pdf")
        self.assertEqual(out["accepted"], [])
        self.assertEqual({r["reason_code"] for r in out["rejected"]}, {"TIE_OR_DRAW_IN_TWO_WAY_ML"})


class GuardBlocksPricing(unittest.TestCase):
    """Monkey-patch the frozen pricer and prove it never sees an invalid row."""

    def setUp(self):
        self.seen = []

        def hook(row):
            self.seen.append(row)

        self._old = mc._PRICING_HOOK if hasattr(mc, "_PRICING_HOOK") else None
        mc._PRICING_HOOK = hook
        # Also patch the frozen function so a leak would be visible even if hook is skipped.
        self._orig = frozen.price_game_market

        def wrapped(r, proj):
            self.seen.append(dict(r))
            return self._orig(r, proj)

        self.patcher = patch.object(frozen, "price_game_market", side_effect=wrapped)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        if self._old is None:
            mc.__dict__.pop("_PRICING_HOOK", None)
        else:
            mc._PRICING_HOOK = self._old

    def _sample_inputs(self, odds_rows, tmp):
        # Reuse make_samples structural files when present, else skip team projection
        # and only assert the hook over accepted odds.
        import make_samples
        dest = Path(tmp) / "sample"
        dest.mkdir()
        prev = make_samples.OUT
        make_samples.OUT = str(dest)
        try:
            make_samples.main()
        finally:
            make_samples.OUT = prev
        with open(dest / "odds.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["game_id", "market", "selection", "line", "price"])
            w.writeheader()
            w.writerows(odds_rows)
        return {n: str(dest / (n + ".csv")) for n in
                ("teams", "games", "injuries", "players", "positional_defense", "odds", "props")}

    def test_guarded_run_card_does_not_price_home_plus_tie(self):
        rows = [row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "TIE", 1000),
                row("G1", "ML", "DEN", -160), row("G1", "ML", "LAL", 140)]
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self._sample_inputs(rows, tmp)
            result = mc.run_card_guarded(inputs, os.path.join(tmp, "out"), source_kind="csv")
        sels = {(_norm_market(r), r.get("selection")) for r in self.seen}
        self.assertNotIn(("1H_ML", "TIE"), sels)
        self.assertNotIn(("1H_ML", "DEN"), sels)  # the paired home row is also withheld
        self.assertEqual({r["reason_code"] for r in result["rejected"] if r["market"] == "1H_ML"},
                         {"TIE_OR_DRAW_IN_TWO_WAY_ML"})

    def test_all_source_kinds_block_three_way_and_incomplete(self):
        bad = [
            [row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "LAL", 210), row("G1", "1H_ML", "TIE", 900)],
            [row("G1", "1Q_ML", "DEN", -120)],
            [row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "DEN", -121)],
        ]
        for kind in sorted(mc.SOURCE_KINDS):
            for rows in bad:
                self.seen.clear()
                out = mc.load_board({"odds_rows": rows}, source_kind=kind)
                self.assertEqual(out["accepted"], [], (kind, rows[0]["market"]))
                self.assertTrue(out["rejected"])
                # load_board does not call pricing; accepted is empty so hook must be empty too.
                if not out["accepted"]:
                    # Do not run_card; proving accepted is empty is the contract.
                    self.assertEqual(self.seen, [])


def _norm_market(r):
    return r.get("market")


class EntryPointCensus(unittest.TestCase):
    """Enumerate repo entry points into the frozen pricer and prove runners are guarded."""

    ALLOWED_UNGUARDED = {
        # Frozen unit tests and the frozen module itself.
        "models/nba/sportsedge_nba_model.py",
        "models/nba/test_sportsedge_nba_model.py",
        "models/nba/test_period_ml_settlement.py",
        "models/nba/test_nba_event_identity.py",
        # This test file patches the frozen pricer to observe leaks.
        "models/nba/test_market_contract.py",
    }

    def _call_names(self, path: Path):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeError):
            return set()
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {
                "price_game_market", "price_games", "run_card",
            }:
                found.add(node.attr)
            if isinstance(node, ast.Name) and node.id in {
                "price_game_market", "price_games", "run_card",
            }:
                found.add(node.id)
        return found

    def test_inventory_matches_registry_and_all_runners_are_guarded(self):
        unguarded = []
        for path in ROOT.rglob("*.py"):
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            if any(part in {".git", ".venv", "venv", "node_modules", "__pycache__"} for part in path.parts):
                continue
            if rel.startswith(("archive/", "moonshot/", ".")):
                continue
            names = self._call_names(path)
            if not names:
                continue
            # Only count files that also mention the NBA model, to avoid other sports' run_card.
            text = path.read_text(encoding="utf-8", errors="replace")
            if "sportsedge_nba_model" not in text and "price_game_market" not in text:
                continue
            if "sportsedge_nba_model" not in text and rel not in {
                "models/nba/sportsedge_nba_model.py",
                "models/nba/test_period_ml_settlement.py",
                "models/nba/test_sportsedge_nba_model.py",
                "models/nba/test_market_contract.py",
                "models/nba/market_contract.py",
                "models/nba/run_it.py",
            }:
                continue
            if rel in self.ALLOWED_UNGUARDED:
                continue
            if rel in {"models/nba/market_contract.py", "models/nba/run_it.py"}:
                continue
            unguarded.append((rel, sorted(names)))
        self.assertEqual(unguarded, [], msg="NBA pricing callers must go through the guarded adapter: %r" % unguarded)

    def test_no_workflow_or_script_runs_the_frozen_pricer_cli_directly(self):
        """Existing CLIs/workflows may run frozen-file test fixtures only; none may run the frozen
        module as a program or call its pricing functions on a real board."""
        import re
        offenders = []
        direct = re.compile(r"python3?\s+(?:-\S+\s+)*(?:\S*/)?sportsedge_nba_model(?:\.py)?(?:\s|$)")
        for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            for n, line in enumerate(wf.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                s = line.strip()
                if not s.startswith("#") and direct.search(s):
                    offenders.append((wf.name, n, s))
        self.assertEqual(offenders, [], msg="workflows must not run the frozen pricer CLI directly: %r" % offenders)

    def test_scripts_with_main_calling_frozen_pricer_are_only_the_frozen_file(self):
        offenders = []
        for path in ROOT.rglob("*.py"):
            if any(part in {".git", "__pycache__", "node_modules", "venv", ".venv"} for part in path.parts):
                continue
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            text = path.read_text(encoding="utf-8", errors="replace")
            if "__main__" in text and "sportsedge_nba_model" in text and "run_card" in text \
                    and rel not in self.ALLOWED_UNGUARDED | {"models/nba/market_contract.py", "models/nba/run_it.py"}:
                offenders.append(rel)
        self.assertEqual(offenders, [])

    def test_guarded_entry_point_names_are_importable(self):
        self.assertTrue(callable(mc.load_board))
        self.assertTrue(callable(mc.filter_odds))
        self.assertTrue(callable(mc.run_card_guarded))
        self.assertTrue(callable(run_it.main))
        self.assertTrue(callable(run_it.run_from_inputs))
        self.assertEqual(len(mc.GUARDED_ENTRY_POINTS), 5)

    def test_every_source_kind_is_a_registered_entry(self):
        # CLI advertises the same kinds the guard accepts.
        self.assertEqual(set(run_it.SOURCE_KINDS), set(mc.SOURCE_KINDS))
        for kind in mc.SOURCE_KINDS:
            out = mc.load_board({"odds_rows": two_way_ml()}, source_kind=kind)
            self.assertEqual(len(out["accepted"]), 2, kind)

    def test_cli_replay_and_dk_and_manual_reject_tie_bug(self):
        rows = [row("G1", "1H_ML", "DEN", -120), row("G1", "1H_ML", "TIE", 1000)]
        for kind in ("dk_capture", "replay", "manual", "csv"):
            out = run_it.run_from_inputs({"odds_rows": rows}, tempfile.mkdtemp(), source_kind=kind)
            self.assertEqual(out["accepted"], [])
            self.assertEqual(out["picks"], [])
            self.assertTrue(all(r["reason_code"] == "TIE_OR_DRAW_IN_TWO_WAY_ML" for r in out["rejected"]))



class MarketCoverage(unittest.TestCase):
    """Every quarter, half, spread, total, moneyline and team total is priced or reason-coded."""

    PERIODS = ("", "1H", "2H", "1Q", "2Q", "3Q", "4Q")
    PRICEABLE = {"", "1H", "1Q"}

    def _mkt(self, period, base):
        return f"{period}_{base}" if period else base

    def test_every_period_and_market_type_is_priced_or_reason_coded(self):
        home_away = {"G1": {"home": "DEN", "away": "LAL"}}
        for period in self.PERIODS:
            cases = [
                (self._mkt(period, "ML"), [row("G1", self._mkt(period, "ML"), "DEN", -135),
                                           row("G1", self._mkt(period, "ML"), "LAL", 115)]),
                (self._mkt(period, "SPREAD"), [row("G1", self._mkt(period, "SPREAD"), "DEN", -110, "-3.5"),
                                               row("G1", self._mkt(period, "SPREAD"), "LAL", -110, "3.5")]),
                (self._mkt(period, "TOTAL"), [row("G1", self._mkt(period, "TOTAL"), "OVER", -110, "220.5"),
                                              row("G1", self._mkt(period, "TOTAL"), "UNDER", -110, "220.5")]),
                (self._mkt(period, "TT_DEN") if period else "TT_DEN",
                 [row("G1", self._mkt(period, "TT_DEN") if period else "TT_DEN", "OVER", -110, "112.5"),
                  row("G1", self._mkt(period, "TT_DEN") if period else "TT_DEN", "UNDER", -110, "112.5")]),
            ]
            for name, rows in cases:
                out = mc.filter_odds(rows, home_away=home_away)
                if period in self.PRICEABLE:
                    self.assertEqual(out["rejected"], [], name)
                    self.assertEqual(len(out["accepted"]), 2, name)
                else:
                    self.assertEqual(out["accepted"], [], name)
                    self.assertTrue(out["rejected"], name)
                    self.assertEqual({r["reason_code"] for r in out["rejected"]},
                                     {"UNSUPPORTED_PERIOD_MARKET"}, name)


class FractionalAndMalformedOdds(unittest.TestCase):
    """Fractional or malformed American odds must be rejected before pricing, on every source kind."""

    BAD_PRICES = ["-110.5", "150.5", "1.91", "2.5", "5/2", "EVEN", "", "abc", "nan", "inf", "-inf",
                  "99", "-99", "0", "-0", "1e2.5", "+-110", "--110", "1,50"]

    def _pair(self, price, market="1H_ML"):
        return [row("G1", market, "DEN", price), row("G1", market, "LAL", 115)]

    def test_parse_american_price(self):
        for ok, want in (("-110", -110), ("+150", 150), ("150", 150), (-110, -110), (150.0, 150),
                         ("-110.0", -110), (100, 100), ("-100", -100), ("1e3", 1000)):
            self.assertEqual(mc.parse_american_price(ok), want, ok)
        for bad in self.BAD_PRICES + [None, True, False, float("nan"), float("inf"), -110.5, 1.91, 99]:
            self.assertIsNone(mc.parse_american_price(bad), repr(bad))

    def test_each_bad_price_rejects_the_whole_contract(self):
        for bad in self.BAD_PRICES:
            if bad == "":
                continue  # blank is a MISSING_REQUIRED_FIELD, covered below
            for market in ("ML", "1H_ML", "1Q_ML"):
                out = mc.filter_odds(self._pair(bad, market))
                self.assertEqual(out["accepted"], [], (bad, market))
                codes = {r["reason_code"] for r in out["rejected"]}
                self.assertEqual(codes, {"ODDS_MALFORMED_OR_FRACTIONAL", "AMBIGUOUS_MARKET_CONTRACT"}, (bad, market))
                self.assertEqual(len(out["rejected"]), 2)

    def test_blank_price_is_missing_field_and_poisons_pair(self):
        out = mc.filter_odds(self._pair(""))
        self.assertEqual(out["accepted"], [])
        self.assertIn("MISSING_REQUIRED_FIELD", {r["reason_code"] for r in out["rejected"]})

    def test_fractional_price_rejected_for_totals_spreads_team_totals(self):
        cases = [
            [row("G1", "TOTAL", "OVER", "-110.5", "220.5"), row("G1", "TOTAL", "UNDER", -110, "220.5")],
            [row("G1", "SPREAD", "DEN", -110, "-3.5"), row("G1", "SPREAD", "LAL", "-104.5", "3.5")],
            [row("G1", "1H_TT_DEN", "OVER", "1.91", "55.5"), row("G1", "1H_TT_DEN", "UNDER", -110, "55.5")],
            [row("G1", "TT_DEN", "OVER", "5/2", "112.5"), row("G1", "TT_DEN", "UNDER", -110, "112.5")],
        ]
        for rows in cases:
            out = mc.filter_odds(rows)
            self.assertEqual(out["accepted"], [], rows[0]["market"])
            self.assertTrue(any(r["reason_code"] == "ODDS_MALFORMED_OR_FRACTIONAL" for r in out["rejected"]))

    def test_invalid_lines_rejected(self):
        for rows, code in (
            ([row("G1", "TOTAL", "OVER", -110, "abc"), row("G1", "TOTAL", "UNDER", -110, "abc")], "INVALID_LINE"),
            ([row("G1", "TOTAL", "OVER", -110, "nan"), row("G1", "TOTAL", "UNDER", -110, "nan")], "INVALID_LINE"),
            ([row("G1", "SPREAD", "DEN", -110, ""), row("G1", "SPREAD", "LAL", -110, "")], "INVALID_LINE"),
            ([row("G1", "1H_ML", "DEN", -110, "1.5"), row("G1", "1H_ML", "LAL", 110, "1.5")], "INVALID_LINE"),
        ):
            out = mc.filter_odds(rows)
            self.assertEqual(out["accepted"], [], rows[0]["market"])
            self.assertIn(code, {r["reason_code"] for r in out["rejected"]})

    def test_whole_number_prices_still_accepted(self):
        for price in ("-110", "+115", 115, "115.0", "-100", "100"):
            out = mc.filter_odds([row("G1", "1H_ML", "DEN", -135), row("G1", "1H_ML", "LAL", price)])
            self.assertEqual(len(out["accepted"]), 2, price)

    def test_fractional_odds_never_reach_pricing_on_any_source_kind(self):
        seen = []
        orig = frozen.price_game_market
        def spy(r, proj):
            seen.append(dict(r)); return orig(r, proj)
        for kind in sorted(mc.SOURCE_KINDS):
            for bad in ("-110.5", "1.91", "5/2", "EVEN"):
                with patch.object(frozen, "price_game_market", side_effect=spy):
                    out = run_it.run_from_inputs({"odds_rows": self._pair(bad) + two_way_ml(market="ML")},
                                                 tempfile.mkdtemp(), source_kind=kind)
                self.assertEqual([r for r in out["accepted"] if r["market"] == "1H_ML"], [], (kind, bad))
                self.assertEqual([r for r in seen if r["market"] == "1H_ML"], [], (kind, bad))
                self.assertEqual({r["reason_code"] for r in out["rejected"]},
                                 {"ODDS_MALFORMED_OR_FRACTIONAL", "AMBIGUOUS_MARKET_CONTRACT"})

    def test_fractional_price_from_csv_file_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "odds.csv"
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["game_id", "market", "selection", "line", "price"])
                w.writeheader(); w.writerows(self._pair("-110.5"))
            for kind in ("csv", "manual", "replay", "dk_capture", "pdf", "screenshot"):
                out = mc.load_board({"odds": str(path), "capture_path": "/tmp/x"}, source_kind=kind)
                self.assertEqual(out["accepted"], [], kind)
                self.assertEqual({r["reason_code"] for r in out["rejected"]},
                                 {"ODDS_MALFORMED_OR_FRACTIONAL", "AMBIGUOUS_MARKET_CONTRACT"}, kind)
            rc = run_it.main(["--source-kind", "csv", "--inputs", str(Path(tmp) / "none"),
                              "--odds", str(path), "--out", str(Path(tmp) / "out")])
            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / "out" / "_accepted_odds.csv").exists())


class FrozenBehaviorUnchanged(unittest.TestCase):
    def test_unguarded_frozen_run_still_prices_home_plus_tie(self):
        """Documents the defect that the guard exists to isolate. Do not 'fix' this here."""
        proj = {"margin": 3.0, "total": 225.0, "home": "H", "away": "A",
                "home_pts": 114.0, "away_pts": 111.0, "game_id": "G", "inputs": ""}
        rows = [
            {"game_id": "G", "market": "1H_ML", "selection": "H", "line": "", "price": "-120"},
            {"game_id": "G", "market": "1H_ML", "selection": "TIE", "line": "", "price": "+1000"},
        ]
        priced = frozen.price_games({"odds": [dict(r) for r in rows]}, {"G": proj})
        self.assertEqual([p["selection"] for p in priced], ["H", "TIE"])


if __name__ == "__main__":
    unittest.main()
