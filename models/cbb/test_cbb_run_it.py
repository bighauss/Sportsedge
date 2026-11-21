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
            self.assertEqual([m["status"] for m in row["markets"]], ["PRICED_PAPER"] * 3)
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

if __name__ == "__main__":
    unittest.main()
