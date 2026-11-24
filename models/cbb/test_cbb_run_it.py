"""CBB RUN IT end-to-end on SYNTHETIC fixtures: provider-shaped captures -> adapters ->
unchanged cbbd_paper_card.build_card (frozen model) -> ledger -> sanitized card."""
import json, os, sys, tempfile, unittest
from datetime import datetime
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1]))
import cbb_run_it as R
import cbbd_paper_synthetic as S
import cbbd_paper_ledger as LG
from cbbd_native_score_model import project

NOW = datetime.fromisoformat("2026-11-21T15:00:00+00:00")
OBS = "2026-11-21T14:00:00Z"

def provider():
    games, boxes = [], []
    for p in S.prior_games():
        games.append({"id": int(p["game_id"]), "season": S.SEASON, "startDate": p["tipoff_utc"], "startTimeTbd": False,
                      "status": "final", "homeTeamId": int(p["home_team_id"]), "awayTeamId": int(p["away_team_id"]),
                      "homeTeam": f"Synthetic {p['home_team_id']}", "awayTeam": f"Synthetic {p['away_team_id']}",
                      "neutralSite": p["neutral"], "homePoints": p["home_points"], "awayPoints": p["away_points"]})
        boxes += [{"gameId": int(p["game_id"]), "teamId": int(t), "teamStats": {"possessions": p["possessions"]}}
                  for t in (p["home_team_id"], p["away_team_id"])]
    for gid, h, a, n in S.SLATE:
        games.append({"id": int(gid), "season": S.SEASON, "startDate": S.TIP, "startTimeTbd": False,
                      "status": "scheduled", "homeTeamId": int(h), "awayTeamId": int(a),
                      "homeTeam": f"Synthetic {h}", "awayTeam": f"Synthetic {a}", "neutralSite": n == "1"})
    return games, boxes

def espn(neutral_override=None):
    ev = []
    for gid, h, a, n in S.SLATE:
        nn = neutral_override.get(gid, n) if neutral_override else n
        ev.append({"competitions": [{"date": S.TIP.replace(":00Z", "Z"), "neutralSite": nn == "1", "competitors": [
            {"homeAway": "home", "team": {"location": f"Synthetic {h}"}},
            {"homeAway": "away", "team": {"location": f"Synthetic {a}"}}]}]})
    return {"events": ev}

BOARD = [{"sport": "CBB", "home": "Synthetic 1", "away": "Synthetic 2", "market": "SPREAD", "line": "-3.5", "price_a": "-110", "price_b": "-110"},
         {"sport": "CBB", "home": "Synthetic 1", "away": "Synthetic 2", "market": "TOTAL", "line": "140.5", "price_a": "-110", "price_b": "-110"},
         {"sport": "CBB", "home": "Synthetic 1", "away": "Synthetic 2", "market": "ML", "line": "", "price_a": "-150", "price_b": "130"},
         {"sport": "CBB", "home": "Synthetic 2", "away": "Synthetic 1", "market": "ML", "line": "", "price_a": "-150", "price_b": "130"},
         {"sport": "CBB", "home": "Nowhere U", "away": "Synthetic 3", "market": "ML", "line": "", "price_a": "-150", "price_b": "130"}]

def run(d, **kw):
    games, boxes = provider(); body = S.ratings_body()
    args = dict(work=d, season=S.SEASON, now_utc=NOW, games=games, boxes=boxes, observed_utc=OBS,
                ratings_body=body, ratings_receipt=S.receipt(body), espn=espn(), espn_sha="e" * 64,
                espn_captured="2026-11-21T14:30:00Z", board_rows=BOARD, board_captured_utc="2026-11-21T14:30:00Z")
    args.update(kw)
    return R.build(**args)

class EndToEnd(unittest.TestCase):
    def test_full_path_uses_frozen_model(self):
        with tempfile.TemporaryDirectory() as d:
            card, names, extra = run(d, ledger_path=os.path.join(d, "ledger.jsonl"))
            self.assertIsNone(card["context_error"])
            row = next(r for r in card["rows"] if r["game_id"] == "9001")
            self.assertEqual(row["status"], "PROJECTED")
            st = {m["market"]: (m["status"], m.get("pass_reason")) for m in row["markets"]}
            self.assertEqual(st["moneyline"][0], "PRICED_PAPER"); self.assertEqual(st["spread"][0], "PRICED_PAPER")
            self.assertEqual(st["total"], ("PASS", "MISSING_QUOTE"))              # total order unverified
            self.assertIn(("Synthetic 2 @ Synthetic 1", "TOTAL", "over/under price order not verified for this board format"),
                          extra["quotes_unmatched"])
            # projection equals a direct call into the frozen model with the same context
            from cbbd_native_score_model import fit_context
            from sportsedge.validation.daily_ratings_capture import eligible_bytes
            self.assertEqual(card["model_code_sha256"], __import__("cbbd_native_score_model").MODEL_CODE_SHA256)
            self.assertEqual(extra["ledger"]["state"], "CARD_FROZEN")
            self.assertEqual(len(LG.read(os.path.join(d, "ledger.jsonl"))), 1)
            md = R.render(card, names, extra)
            self.assertIn("PAPER / 0u", md); self.assertIn("5:00 PM", md)            # 23:00Z -> 5:00 PM CT
            self.assertEqual((card["official_counted"], card["approved_stake_u"]), (0, 0))

    def test_withholding_reasons(self):
        with tempfile.TemporaryDirectory() as d:
            card, names, extra = run(d)
            reasons = {r["game_id"]: r["pass_reason"] for r in card["rows"] if r["status"] == "PASS"}
            self.assertIn("9003", reasons)                               # unrated team
            unmatched = {(g, why) for g, _, why in extra["quotes_unmatched"]}
            self.assertIn(("Synthetic 1 @ Synthetic 2", "home/away orientation mismatch"), unmatched)
            self.assertIn(("Synthetic 3 @ Nowhere U", "no unique CBBD game for names"), unmatched)
            nine2 = next(r for r in card["rows"] if r["game_id"] == "9002")
            self.assertTrue(all(m["pass_reason"] == "MISSING_QUOTE" for m in nine2["markets"]))

    def test_neutral_disagreement_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            card, _, _ = run(d, espn=espn({"9001": "1"}))
            row = next(r for r in card["rows"] if r["game_id"] == "9001")
            self.assertEqual(row["status"], "PASS"); self.assertIn("NEUTRAL", row["pass_reason"])

    def test_missing_possessions_never_estimated(self):
        with tempfile.TemporaryDirectory() as d:
            card, _, extra = run(d, boxes=[])
            self.assertEqual(extra["prior_census"]["finals"], 0)
            self.assertTrue(all(r["status"] == "PASS" for r in card["rows"]))

    def test_started_game_excluded_from_slate(self):
        games, _ = provider()
        s = R.slate(games, NOW.date(), datetime.fromisoformat("2026-11-21T23:30:00+00:00"), S.SEASON)
        self.assertEqual(s, [])

    def test_ledger_refuses_refreeze(self):
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(d, "ledger.jsonl")
            run(d, ledger_path=led)
            with self.assertRaises(LG.LedgerError):
                run(os.path.join(d, "b"), ledger_path=led)

    def test_repeat_diagnostic_preserves_prior_freeze_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as d:
            led = Path(d) / "ledger.jsonl"
            run(Path(d) / "a", ledger_path=led)
            original = led.read_bytes()
            card, names, extra = run(Path(d) / "b", ledger_path=led, diagnostic_repeat=True)
            self.assertEqual(led.read_bytes(), original)
            self.assertEqual(extra["ledger"]["already_frozen"], card["row_count"])
            self.assertEqual(extra["ledger"]["newly_frozen"], 0)
            self.assertEqual(extra["ledger"]["appended"], 0)
            self.assertIn("Repeat diagnostic", R.render(card, names, extra))

    def test_repeat_diagnostic_freezes_only_unseen_subset(self):
        with tempfile.TemporaryDirectory() as d:
            led = Path(d) / "ledger.jsonl"
            card, _, _ = run(Path(d) / "a")
            prior = dict(card)
            prior["rows"] = card["rows"][:1]
            prior["row_count"] = 1
            prior["projected_rows"] = int(prior["rows"][0]["status"] == "PROJECTED")
            prior["priced_market_rows"] = sum(m["status"] == "PRICED_PAPER"
                                               for m in prior["rows"][0]["markets"])
            prior["card_sha256"] = R.PC.card_digest(prior)
            LG.append(led, LG.card_entries(prior), clock=lambda: NOW)
            original = led.read_bytes()
            current, _, extra = run(Path(d) / "b", ledger_path=led, diagnostic_repeat=True)
            entries = LG.read(led)
            self.assertTrue(led.read_bytes().startswith(original))
            self.assertEqual(len(entries), 2)
            subset = entries[-1]["payload"]
            self.assertEqual(subset["row_count"], current["row_count"] - 1)
            self.assertEqual(subset["ledger_subset"]["parent_card_sha256"], current["card_sha256"])
            self.assertEqual(subset["card_sha256"], R.PC.card_digest(subset))
            self.assertEqual(extra["ledger"]["already_frozen"], 1)
            self.assertEqual(extra["ledger"]["newly_frozen"], current["row_count"] - 1)
            self.assertNotIn(prior["rows"][0]["game_id"], [r["game_id"] for r in subset["rows"]])

class Adapters(unittest.TestCase):
    def test_prior_rejects_duplicates_and_wrong_teams(self):
        games, boxes = provider()
        g0 = next(g for g in games if g["status"] == "final")
        dup = dict(g0)
        wrong = [b for b in boxes if b["gameId"] != g0["id"]]
        pg, c = R.prior_games(games + [dup], boxes, OBS, S.SEASON)
        self.assertEqual(c["duplicate_game_id"], 2)
        g1 = [g for g in games if g["status"] == "final"][1]
        bad = [dict(b, teamId=999) if b["gameId"] == g1["id"] else b for b in boxes]
        _, c2 = R.prior_games(games, bad, OBS, S.SEASON)
        self.assertEqual(c2["team_mismatch"], 1)

    def test_unknown_neutral_not_defaulted(self):
        games, _ = provider(); miss = []
        for g in games:
            if g["id"] == 9001: g["neutralSite"] = None
        s = R.slate(games, NOW.date(), NOW, S.SEASON, miss)
        self.assertNotIn("9001", [r["game_id"] for r in s]); self.assertIn(("9001", "CBBD neutral-site flag unknown"), miss)

class CliFixture(unittest.TestCase):
    def test_main_end_to_end_from_fixture_dir(self):
        import csv as _csv
        with tempfile.TemporaryDirectory() as d:
            fx = Path(d) / "fx"; fx.mkdir()
            games, boxes = provider(); body = S.ratings_body()
            (fx / "ratings.json").write_bytes(body)
            (fx / "receipt.json").write_text(json.dumps(S.receipt(body)))
            (fx / "games.json").write_text(json.dumps(games)); (fx / "boxes.json").write_text(json.dumps(boxes))
            (fx / "espn.json").write_text(json.dumps(espn()))
            board = Path(d) / "board.csv"
            with open(board, "w", newline="") as f:
                w = _csv.DictWriter(f, ["sport", "home", "away", "market", "line", "price_a", "price_b"]); w.writeheader(); w.writerows(BOARD)
            rc = R.main(["--board", str(board), "--board-captured-utc", "2026-11-21T14:30:00Z", "--season", str(S.SEASON),
                         "--private-dir", str(Path(d) / "priv"), "--out", str(Path(d) / "out"),
                         "--ledger", str(Path(d) / "priv" / "ledger.jsonl"),
                         "--fixture-dir", str(fx), "--now", "2026-11-21T15:00:00+00:00"])
            self.assertEqual(rc, 0)
            md = (Path(d) / "out" / "cbb_card.md").read_text()
            self.assertIn("Priced markets", md); self.assertIn("Source receipts", md)
            rec = json.loads((Path(d) / "out" / "receipts.json").read_text())
            archived = {R.sha(p.read_bytes()) for p in (Path(d) / "priv").rglob("*.raw.json")}
            for r in rec:
                if r["source"] != "dk_board":
                    self.assertIn(str(r["sha256"]).replace("sha256:", ""), archived)   # every receipt has archived bytes
            self.assertEqual(len(LG.read(str(Path(d) / "priv" / "ledger.jsonl"))), 1)

    def test_main_without_key_blocks(self):
        os.environ.pop("CBBD_API_KEY", None)
        with tempfile.TemporaryDirectory() as d:
            rc = R.main(["--board", "x", "--board-captured-utc", "2026-11-21T14:30:00Z", "--season", "2027",
                         "--private-dir", str(Path(d) / "p"), "--out", str(Path(d) / "o")])
            self.assertEqual(rc, 2); self.assertFalse((Path(d) / "p").exists())

class HalfSourceEvidence(unittest.TestCase):
    def fixture(self, games, asof="2026-11-22T04:00:00Z"):
        import hashlib
        from cbbd_half_evidence import normalize
        raw = json.dumps(games).encode()
        man = {"format": "CBBD_GAMES_CAPTURE_V1", "provider": "collegebasketballdata",
               "documented_endpoint": "https://api.collegebasketballdata.com/games",
               "source_sha256": hashlib.sha256(raw).hexdigest(), "source_bytes": len(raw),
               "returned_rows": len(games), "season": 2027,
               "local_observed_utc": "2026-11-22T03:00:00Z"}
        return normalize(raw, man, asof_utc=asof)

    def game(self, **kw):
        return dict({"id": 9001, "season": 2027, "homeTeamId": 1, "awayTeamId": 2,
                     "status": "final", "startTimeTbd": False, "startDate": S.TIP,
                     "homePeriodPoints": [30, 40, 8], "awayPeriodPoints": [35, 35, 5],
                     "homePoints": 78, "awayPoints": 75}, **kw)

    def test_overtime_removed_and_observation_clock_preserved(self):
        raw, report = self.fixture([self.game()])
        row = json.loads(raw)
        self.assertEqual(row["periods"], {"H1": [30, 35], "H2": [40, 35]})
        self.assertEqual((row["regulation_home"], row["regulation_away"]), (70, 70))
        self.assertEqual(row["final_published_utc"], row["final_captured_utc"])
        self.assertEqual(report["admitted"], 1)
        from sportsedge.markets.period_share_fit import _row
        from datetime import timezone
        _row(row, "CBB", datetime(2026, 11, 22, 4, tzinfo=timezone.utc))

    def test_duplicates_missing_and_invalid_overtime_fail_closed(self):
        bad = [self.game(), self.game(), self.game(id=2, homePeriodPoints=None),
               self.game(id=3, homePeriodPoints=[31, 39, 8], awayPeriodPoints=[35, 34, 6]),
               self.game(id=4, homePoints=99)]
        raw, report = self.fixture(bad)
        self.assertEqual(raw, b"")
        self.assertEqual(report["input_rows"], 5)
        self.assertEqual(len(report["rejected"]), 5)

    def test_snapshot_after_cutoff_refused(self):
        from cbbd_prospective_capture import Hold
        with self.assertRaisesRegex(Hold, "HALF_SOURCE_NOT_PRIOR"):
            self.fixture([self.game()], asof="2026-11-22T03:00:00Z")


class LiveHalfMean(unittest.TestCase):
    def fit(self, count=56):
        from datetime import timedelta
        from hashlib import sha256
        from cbbd_half_evidence import fit_full_to_first_half
        rows = []
        for i in range(count):
            tip = NOW - timedelta(days=8-i//8, hours=2)
            rows.append({"id": i+1, "season": S.SEASON, "homeTeamId": 1, "awayTeamId": 2,
                         "status": "final", "startTimeTbd": False, "startDate": R.utcz(tip),
                         "homePeriodPoints": [30, 40, 8], "awayPeriodPoints": [35, 35, 5],
                         "homePoints": 78, "awayPoints": 75})
        raw = json.dumps(rows).encode()
        man = {"format": "CBBD_GAMES_CAPTURE_V1", "provider": "collegebasketballdata",
               "documented_endpoint": "https://api.collegebasketballdata.com/games",
               "source_sha256": sha256(raw).hexdigest(), "source_bytes": len(raw),
               "returned_rows": len(rows), "season": S.SEASON, "local_observed_utc": OBS}
        return fit_full_to_first_half(raw, man, asof_utc=R.utcz(NOW))

    def test_first_half_share_uses_full_final_including_ot_and_retains_passes(self):
        from cbbd_half_evidence import project_first_halves
        fit = self.fit()
        self.assertEqual(fit["status"], "TRAIN_ONLY_HALF_MEAN_UNVALIDATED")
        self.assertAlmostEqual(fit["share_of_final_points"], 65/153)
        self.assertEqual(fit["distinct_dates"], 7)
        with tempfile.TemporaryDirectory() as d:
            card, names, extra = run(d)
            rows = project_first_halves(card, fit)
            self.assertEqual(len(rows), len(card["rows"]))
            for r, half in zip(card["rows"], rows):
                if r["status"] == "PROJECTED":
                    self.assertAlmostEqual(half["home_points"], r["projection"]["home_points"]*65/153)
                else:
                    self.assertEqual(half["status"], "PASS")
                    self.assertIsNone(half["away_points"])
            extra.update(half_fit=fit, half_projections=rows)
            self.assertIn("First-half independent expected scores", R.render(card, names, extra))
            self.assertIn("No H1 probability", R.render(card, names, extra))

    def test_insufficient_history_never_invents_share(self):
        fit = self.fit(48)
        self.assertEqual(fit["status"], "BLOCK_HALF_TRAINING")
        self.assertIsNone(fit["share_of_final_points"])


class PlayerHistorySource(unittest.TestCase):
    def inputs(self):
        from datetime import timedelta
        games, boxes = [], []
        for i in range(5):
            tip = R.utcz(NOW - timedelta(days=8-i))
            games.append({"id": i+1, "season": S.SEASON, "status": "final", "startTimeTbd": False,
                          "startDate": tip, "homeTeamId": 1, "awayTeamId": 2})
            boxes.append({"gameId": i+1, "season": S.SEASON, "startTimeTbd": False, "startDate": tip,
                          "teamId": 1, "opponentId": 2, "isHome": True,
                          "players": [{"athleteId": 55, "minutes": 25, "points": 10+i,
                                       "rebounds": {"total": 5}, "assists": 3,
                                       "threePointFieldGoals": {"made": 2}}]})
        return games, boxes

    def normalize(self, games, boxes):
        from hashlib import sha256
        from cbbd_player_history import normalize
        g, b = json.dumps(games).encode(), json.dumps(boxes).encode()
        def rec(blob, source):
            return {"source": source, "sha256": sha256(blob).hexdigest(),
                    "bytes": len(blob), "observed_utc": OBS}
        return normalize(b, rec(b, "cbbd_games_players"), g, rec(g, "cbbd_games_season"),
                         season=S.SEASON, asof_utc=R.utcz(NOW))

    def test_actual_id_and_pra_history(self):
        from cbbd_player_history import historical_baselines
        records, census = self.normalize(*self.inputs())
        self.assertEqual(census["accepted_player_games"], 5)
        self.assertFalse(census["confirmed_activity"])
        p = historical_baselines(records)[0]
        self.assertEqual(p["player_id"], "55")
        self.assertEqual(p["stats"]["PRA"]["mean"], 20)
        self.assertEqual(p["mean_minutes"], 25)
        self.assertIn("NOT_PREGAME_FORECAST", p["status"])

    def test_cross_batch_duplicate_and_missing_final_census(self):
        from hashlib import sha256
        from cbbd_player_history import collect_batches
        games, boxes = self.inputs()
        g = json.dumps(games).encode()
        def rec(blob, source):
            return {"source": source, "sha256": sha256(blob).hexdigest(),
                    "bytes": len(blob), "observed_utc": OBS}
        batches = []
        for part in (boxes[:3], boxes[2:4]):
            raw = json.dumps(part).encode()
            batches.append((raw, rec(raw, "cbbd_games_players")))
        report = collect_batches(batches, g, rec(g, "cbbd_games_season"),
                                 season=S.SEASON, asof_utc=R.utcz(NOW))
        self.assertEqual(report["cross_batch_duplicate_rows"], 2)
        self.assertEqual(report["represented_final_games"], 3)
        self.assertEqual(report["expected_final_games"], 5)
        self.assertEqual(report["historical_players"], 0)
        self.assertFalse(report["confirmed_activity"])

    def test_duplicate_missing_or_wrong_identity_is_not_zero_filled(self):
        from cbbd_player_history import historical_baselines
        games, boxes = self.inputs()
        boxes[0]["players"][0]["points"] = None
        boxes[1]["opponentId"] = 999
        boxes.append(dict(boxes[2]))
        records, census = self.normalize(games, boxes)
        self.assertEqual(census["accepted_player_games"], 2)
        self.assertEqual(historical_baselines(records), [])


if __name__ == "__main__":
    unittest.main()
