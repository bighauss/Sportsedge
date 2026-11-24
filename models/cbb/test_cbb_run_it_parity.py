"""CBB RUN IT vs cbbd_paper_card.run parity on the SAME synthetic fixture. Offline.

cbb_run_it.build calls the unchanged cbbd_paper_card.build_card in-process. This test
writes the runner's own adapter outputs (slate, registry, prior games, quotes, ratings
+ receipt) to files and feeds them to cbbd_paper_card.run with a clock pinned to the
runner's freeze, then compares the two cards.

Fields that legitimately differ (excluded from equality, documented):
  * input_sha256  - runner records {"espn_scoreboard": sha}; run() records the sha256 of
                    every input file it read (slate, registry, ratings, receipt, priors, quotes)
  * card_sha256   - digest over the whole card, so it differs only because input_sha256 does;
                    recomputed here with input_sha256 removed and asserted EQUAL.
built_utc is NOT excluded: the runner builds at its freeze and run() is given that clock.
Synthetic fixtures only; NOT predictive validation.
"""
import json, os, socket, sys, tempfile, unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1]))
import cbb_run_it as R
import cbb_pricing as PR
import cbbd_paper_card as PC
import test_cbb_run_it as T

EXCLUDED = ("input_sha256", "card_sha256")


class Parity(unittest.TestCase):
    def setUp(self):
        self._sock = mock.patch.object(socket, "socket", side_effect=AssertionError("network used"))
        self._sock.start()

    def tearDown(self):
        self._sock.stop()

    def test_runner_card_equals_paper_run_on_same_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); os.chmod(d, 0o700)
            games, boxes = T.provider(); body = T.S.ratings_body(); receipt = T.S.receipt(body)
            card_r, _, _ = T.run(d / "work", games=games, boxes=boxes, ratings_body=body, ratings_receipt=receipt)
            # equivalent files from the SAME adapters the runner used
            s = R.slate(games, T.NOW.astimezone(R.CT).date(), T.NOW, T.S.SEASON)
            pg, _ = R.prior_games(games, boxes, T.OBS, T.S.SEASON)
            quotes, _ = R.board_quotes(T.BOARD, s, "2026-11-21T14:30:00Z")
            files = {"ratings": body, "ratings_receipt": json.dumps({"receipts": [receipt]}).encode(),
                     "prior_games": json.dumps(pg).encode(), "quotes": json.dumps(quotes).encode()}
            for k, v in files.items():
                (d / f"{k}.json").write_bytes(v); os.chmod(d / f"{k}.json", 0o600)
            args = Namespace(freeze_utc=card_r["freeze_utc"], season=T.S.SEASON,
                             slate=str(d / "work" / "slate.csv"), registry=str(d / "work" / "registry.csv"),
                             ratings=str(d / "ratings.json"), ratings_receipt=str(d / "ratings_receipt.json"),
                             prior_games=str(d / "prior_games.json"), prior_residuals=None,
                             quotes=[str(d / "quotes.json")], odds_api_raw=None, odds_api_manifest=None,
                             odds_api_crosswalk=None, max_quote_age_hours=24, output=str(d / "out" / "card.json"))
            # the runner prices with the configured SD constants + blend fields; apply the same to the paper run
            with PR.patched_card(PR.make_config()):
                res = PC.run(args, clock=lambda: T.NOW)
            card_p = json.loads((d / "out" / "card.json").read_bytes())
            self.assertEqual(res["card_sha256"], card_p["card_sha256"])
            strip = lambda c: {k: v for k, v in c.items() if k not in EXCLUDED}  # noqa: E731
            self.assertEqual(strip(card_r), strip(card_p))
            self.assertEqual(card_r["rows"], card_p["rows"])
            self.assertEqual([r["projection"] for r in card_r["rows"]], [r["projection"] for r in card_p["rows"]])
            self.assertEqual(PC.card_digest(strip(card_r)), PC.card_digest(strip(card_p)))
            self.assertEqual(card_r["built_utc"], card_p["built_utc"])
            self.assertNotEqual(card_r["input_sha256"], card_p["input_sha256"])  # documented difference
            self.assertGreater(card_r["priced_market_rows"], 0)


if __name__ == "__main__":
    unittest.main()
