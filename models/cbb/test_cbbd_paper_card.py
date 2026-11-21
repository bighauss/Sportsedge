"""OFFLINE synthetic tests for the CBBD daily paper card. Not predictive validation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

import cbbd_paper_card as card_mod
from cbbd_native_score_model import Pass
from cbbd_paper_card import build_card, card_digest, odds_api_quotes, select_quotes
from cbbd_native_score_model import utc
from cbbd_paper_synthetic import (BUILT, FREEZE, SEASON, TIP, full_quotes, prior_games,
                                  quote, ratings_body, receipt, write_slate)


class CardBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.body = ratings_body()

    def card(self, quotes=None, slate_kw=None, **kw):
        slate, reg = write_slate(self.dir, **(slate_kw or {}))
        q = full_quotes("9001") + full_quotes("9002") if quotes is None else quotes
        args = dict(freeze_utc=FREEZE, built_utc=BUILT, season=SEASON, slate_path=slate,
                    registry_path=reg, ratings_body=self.body,
                    ratings_receipt=receipt(self.body), prior_games=prior_games(),
                    quotes=[(x, "OPERATOR") for x in q])
        args.update(kw)
        return build_card(**args)

    def row(self, card, gid):
        rows = [r for r in card["rows"] if r["game_id"] == gid]
        self.assertEqual(len(rows), 1)
        return rows[0]


class CardContractTest(CardBase):
    def test_every_game_has_projection_or_explicit_pass(self):
        c = self.card()
        self.assertEqual(c["row_count"], 4)
        for r in c["rows"]:
            self.assertIn(r["status"], ("PROJECTED", "PASS"))
            self.assertEqual(r["status"] == "PASS", bool(r["pass_reason"]))
            self.assertEqual([m["market"] for m in r["markets"]], ["moneyline", "spread", "total"])
        self.assertEqual(self.row(c, "9003")["pass_reason"], "UNMAPPED_CBBD_TEAM_ID")
        self.assertEqual(self.row(c, "9004")["pass_reason"], "MISSING_PACE_HISTORY")
        self.assertEqual(c["projected_rows"], 2)

    def test_paper_labels_everywhere_and_self_hash(self):
        c = self.card()
        self.assertEqual((c["official_counted"], c["approved_stake_u"]), (0, 0))
        for r in c["rows"]:
            for m in r["markets"]:
                self.assertEqual((m["label"], m["stake_u"], m["official_counted"],
                                  m["approved_stake_u"]), ("PAPER", 0, 0, 0))
        self.assertEqual(c["card_sha256"], card_digest(c))
        c["rows"][0]["projection"]["margin"] += 1
        self.assertNotEqual(c["card_sha256"], card_digest(c))

    def test_freeze_metadata_and_full_two_sided_quote(self):
        c = self.card()
        for k in ("model_version", "model_code_sha256", "card_builder_sha256", "freeze_utc"):
            self.assertTrue(c[k])
        m = self.row(c, "9001")["markets"][1]
        self.assertEqual(m["status"], "PRICED_PAPER")
        for k in ("book", "line", "price_a", "price_b", "captured_utc"):
            self.assertIsNotNone(m["quote"][k])
        self.assertAlmostEqual(sum(m["market_novig_prob"].values()), 1.0)
        self.assertAlmostEqual(m["model_prob"]["home"] + m["model_prob"]["push"] +
                               m["model_prob"]["away"], 1.0)
        self.assertEqual(set(m["paper_ev_per_1u_at_price"]), {"home", "away"})

    def test_missing_quote_is_explicit(self):
        c = self.card(quotes=full_quotes("9001")[:1])
        r = self.row(c, "9001")
        self.assertEqual([m["status"] for m in r["markets"]], ["PRICED_PAPER", "PASS", "PASS"])
        self.assertEqual(r["markets"][1]["pass_reason"], "MISSING_QUOTE")
        self.assertTrue(all(m["pass_reason"] == "MISSING_QUOTE" for m in self.row(c, "9002")["markets"]))

    def test_built_before_freeze_refused(self):
        with self.assertRaisesRegex(Pass, "BUILT_BEFORE"):
            self.card(built_utc="2026-11-21T14:00:00Z")


class CardGameGateTest(CardBase):
    def test_duplicate_slate_ids_pass_all_copies(self):
        games = [("9001", "1", "2", "0"), ("9001", "3", "4", "0")]
        c = self.card(slate_kw={"games": games})
        self.assertTrue(all(r["pass_reason"] == "DUPLICATE_GAME_ID_ALL_COPIES" for r in c["rows"]))

    def test_wrong_season(self):
        c = self.card(slate_kw={"season": 2026})
        self.assertTrue(all(r["pass_reason"] == "WRONG_SEASON" for r in c["rows"]))

    def test_neutral_site_unknown(self):
        c = self.card(slate_kw={"registry_skip": ("9001",)})
        self.assertTrue(self.row(c, "9001")["pass_reason"].startswith("NEUTRAL_SITE_UNVERIFIED"))
        self.assertEqual(self.row(c, "9002")["status"], "PROJECTED")

    def test_neutral_flag_mismatch_or_registry_tip_mismatch(self):
        c = self.card(slate_kw={"registry_tip": "2026-11-21T23:30:00Z"})
        self.assertEqual(self.row(c, "9001")["pass_reason"], "VENUE_REGISTRY_TIPOFF_MISMATCH")

    def test_tip_before_freeze_and_built_after_tip(self):
        c = self.card(slate_kw={"tip": "2026-11-21T14:00:00Z"})
        self.assertTrue(all(r["pass_reason"] == "TIPOFF_NOT_AFTER_FREEZE" for r in c["rows"]))
        c = self.card(built_utc="2026-11-21T23:00:00Z")
        self.assertTrue(all(r["pass_reason"] == "CARD_BUILT_AT_OR_AFTER_TIPOFF" for r in c["rows"]))

    def test_ratings_observed_after_freeze_pass_everything(self):
        c = self.card(ratings_receipt=receipt(self.body, observed="2026-11-21T15:30:00Z"))
        self.assertIsNone(c["context"])
        self.assertTrue(all(r["status"] == "PASS" and
                            r["pass_reason"].startswith("RATINGS_OR_CONTEXT_NOT_ELIGIBLE")
                            for r in c["rows"] if r["game_id"] in ("9001", "9002")))

    def test_ratings_bytes_tampered_or_missing_receipt(self):
        c = self.card(ratings_receipt=receipt(ratings_body(n=361)))
        self.assertEqual(c["projected_rows"], 0)
        c = self.card(ratings_receipt=None)
        self.assertEqual(c["projected_rows"], 0)

    def test_wrong_season_ratings(self):
        body = ratings_body(season=2026)
        c = self.card(ratings_body=body, ratings_receipt=receipt(body))
        self.assertEqual(c["projected_rows"], 0)

    def test_future_prior_games_rejected_not_used(self):
        late = prior_games(n=40, start="2026-11-21T14:00:00Z")
        for i, g in enumerate(late):
            g["game_id"] = str(80000 + i)
            g["home_points"], g["away_points"] = 200, 10
        a = self.card()
        b = self.card(prior_games=prior_games() + late)
        self.assertEqual(self.row(a, "9001")["projection"], self.row(b, "9001")["projection"])
        self.assertIn("rejected:FUTURE_FINAL_AFTER_FREEZE", b["context"]["prior_game_census"])


class QuoteSelectionTest(unittest.TestCase):
    F = utc(FREEZE, "f")

    def sel(self, rows, **kw):
        return select_quotes([(r, "OPERATOR") for r in rows], self.F,
                             max_age_hours=kw.get("age", 24))

    def test_after_freeze_and_stale_rejected(self):
        chosen, census = self.sel([quote("9001", "total", 140.5, -110, -110, "2026-11-21T15:00:01Z"),
                                   quote("9001", "spread", -3.5, -110, -110, "2026-11-19T00:00:00Z")])
        self.assertEqual(chosen, {})
        self.assertEqual(census["rejected:QUOTE_CAPTURED_AFTER_FREEZE"], 1)
        self.assertEqual(census["rejected:QUOTE_STALE"], 1)

    def test_one_sided_or_invalid_rejected(self):
        rows = [quote("9001", "total", 140.5, -110, None), quote("9001", "spread", None, -110, -110),
                quote("9001", "moneyline", -3.5, -110, -110), quote("9001", "teaser", 1, -110, -110),
                quote("09001", "total", 140.5, -110, -110), quote("9001", "total", 140.25, -110, -110),
                quote("9001", "total", 140.5, -50, -110)]
        chosen, census = self.sel(rows)
        self.assertEqual(chosen, {})
        self.assertEqual(sum(v for k, v in census.items() if k.startswith("rejected:")), len(rows))

    def test_conflicting_duplicates_quarantined(self):
        rows = [quote("9001", "total", 140.5, -110, -110), quote("9001", "total", 141.5, -110, -110)]
        chosen, census = self.sel(rows)
        self.assertEqual(chosen, {})
        self.assertEqual(census["rejected:CONFLICTING_DUPLICATE_QUOTE_ALL_COPIES"], 2)

    def test_latest_then_book_name_never_by_price(self):
        rows = [quote("9001", "moneyline", None, +500, -900, "2026-11-21T14:00:00Z", "bookA"),
                quote("9001", "moneyline", None, -150, 130, "2026-11-21T14:30:00Z", "bookZ"),
                quote("9001", "moneyline", None, -160, 140, "2026-11-21T14:30:00Z", "bookB")]
        chosen, _ = self.sel(rows)
        self.assertEqual(chosen[("9001", "moneyline")]["book"], "bookB")


class OddsApiAdapterTest(unittest.TestCase):
    def setUp(self):
        events = [{"id": "evt00000001", "home_team": "Home U", "away_team": "Away St",
                   "sport_key": "basketball_ncaab", "bookmakers": [{"key": "draftkings", "markets": [
                       {"key": "h2h", "outcomes": [{"name": "Home U", "price": -150},
                                                   {"name": "Away St", "price": 130}]},
                       {"key": "spreads", "outcomes": [{"name": "Home U", "price": -110, "point": -3.5},
                                                       {"name": "Away St", "price": -110, "point": 3.5}]},
                       {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 140.5},
                                                      {"name": "Under", "price": -105, "point": 140.5}]}]}]},
                  {"id": "evt00000002", "home_team": "Other", "away_team": "Team",
                   "sport_key": "basketball_ncaab", "bookmakers": []}]
        self.raw = json.dumps(events).encode()
        self.man = {"schema": "sportsedge-oddsapi-aggregator-raw-v1", "sport": "CBB",
                    "original_raw_sha256": "sha256:" + hashlib.sha256(self.raw).hexdigest(),
                    "captured_utc": "2026-11-21T14:00:00+00:00"}
        self.xw = b"odds_event_id,game_id,odds_home_team,odds_away_team\nevt00000001,9001,Home U,Away St\n"

    def test_exact_crosswalk_yields_three_markets(self):
        rows, census = odds_api_quotes(self.raw, self.man, self.xw)
        self.assertEqual(sorted(r["market"] for r in rows), ["moneyline", "spread", "total"])
        self.assertEqual(census["UNMAPPED_PROVIDER_EVENT"], 1)
        spread = next(r for r in rows if r["market"] == "spread")
        self.assertEqual((spread["line"], spread["game_id"], spread["captured_utc"]),
                         (-3.5, "9001", "2026-11-21T14:00:00Z"))

    def test_orientation_mismatch_is_not_fuzzy_matched(self):
        xw = b"odds_event_id,game_id,odds_home_team,odds_away_team\nevt00000001,9001,Away St,Home U\n"
        rows, census = odds_api_quotes(self.raw, self.man, xw)
        self.assertEqual(rows, [])
        self.assertEqual(census["CROSSWALK_TEAM_ORIENTATION_MISMATCH"], 1)
        xw = b"odds_event_id,game_id,odds_home_team,odds_away_team\nevt00000001,9001,home u,Away St\n"
        self.assertEqual(odds_api_quotes(self.raw, self.man, xw)[0], [])

    def test_hash_sport_and_crosswalk_guards(self):
        with self.assertRaisesRegex(Pass, "HASH_MISMATCH"):
            odds_api_quotes(self.raw + b" ", self.man, self.xw)
        with self.assertRaisesRegex(Pass, "NOT_CBB"):
            odds_api_quotes(self.raw, {**self.man, "sport": "NFL"}, self.xw)
        dup = self.xw + b"evt00000002,9001,Other,Team\n"
        with self.assertRaisesRegex(Pass, "ONE_TO_ONE"):
            odds_api_quotes(self.raw, self.man, dup)


class RunTest(CardBase):
    def args(self, out):
        slate, reg = write_slate(self.dir)
        (self.dir / "ratings.json").write_bytes(self.body)
        (self.dir / "receipt.json").write_text(json.dumps({"receipts": [receipt(self.body)]}))
        (self.dir / "prior.json").write_text(json.dumps(prior_games()))
        (self.dir / "quotes.json").write_text(json.dumps(full_quotes("9001")))
        return argparse.Namespace(
            freeze_utc=FREEZE, season=SEASON, slate=str(slate), registry=str(reg),
            ratings=str(self.dir / "ratings.json"), ratings_receipt=str(self.dir / "receipt.json"),
            prior_games=str(self.dir / "prior.json"), prior_residuals=None,
            quotes=[str(self.dir / "quotes.json")], odds_api_raw=None, odds_api_manifest=None,
            odds_api_crosswalk=None, max_quote_age_hours=24, output=str(out))

    def test_private_create_only_output_with_input_hashes(self):
        out = self.dir / "private" / "card.json"
        clock = lambda: datetime(2026, 11, 21, 15, 5, tzinfo=timezone.utc)
        res = card_mod.run(self.args(out), clock=clock)
        self.assertEqual((res["official_counted"], res["approved_stake_u"]), (0, 0))
        self.assertEqual(os.stat(out).st_mode & 0o777, 0o600)
        card = json.loads(out.read_text())
        self.assertEqual(card["card_sha256"], card_digest(card))
        self.assertEqual(set(card["input_sha256"]) >= {"slate", "registry", "ratings",
                                                       "ratings_receipt", "prior_games",
                                                       "operator_quotes_0"}, True)
        with self.assertRaises(FileExistsError):
            card_mod.run(self.args(out), clock=clock)

    def test_output_inside_public_repo_refused(self):
        repo_out = Path(card_mod.__file__).resolve().parent / "should_not_exist.json"
        with self.assertRaises(ValueError):
            card_mod.run(self.args(repo_out))
        self.assertFalse(repo_out.exists())


if __name__ == "__main__":
    unittest.main()
