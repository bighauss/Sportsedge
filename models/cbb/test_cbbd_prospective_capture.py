"""Offline tests: no network or credential usage; all fixtures synthetic."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cbbd_prospective_capture import (
    Hold, ROOT, MAX_BODY, checked_window, decoded, capture_games,
    finals_from_capture, safe_path,
)

STAMP = datetime(2026, 11, 15, 23, 30, tzinfo=timezone.utc)
H = "a" * 64


def game(i=10, **updates):
    rec = dict(
        id=i, season=2027, startDate="2026-11-15T20:00:00Z",
        homeTeamId=101, awayTeamId=202,
        status="final", startTimeTbd=False, neutralSite=False,
        homePoints=75, awayPoints=70,
    )
    rec.update(updates)
    return rec


def mock_transport(data, seen=None, ctype="application/json", wrong_url=False):
    def fetch(req, n):
        if seen is not None:
            seen.append(req)
        assert n == MAX_BODY
        uri = req.full_url
        return data, ctype, "https://example.test/bad" if wrong_url else uri
    return fetch


def capture(tmp, rows, *, transport=None, key="fake-test-key", clock=STAMP):
    return capture_games(season=2027,
                         start_utc="2026-11-15T00:00:00Z",
                         end_utc="2026-11-15T23:59:59Z",
                         private_dir=tmp,
                         key=key,
                         transport=transport or mock_transport(json.dumps(rows).encode("utf-8")),
                         clock=lambda: clock)


class CbbdCaptureTests(unittest.TestCase):
    def test_requires_explicit_secret_no_network_without_key(self):
        called=[]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(Hold, "NO_AUTHORIZED_CBBD_API_KEY"):
                capture(tmp, [game()], key="", transport=lambda *args:called.append(1))
            self.assertEqual(called,[])

    def test_documented_host_and_bearer_only_in_request_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen=[]
            result=capture(tmp,[game()],transport=mock_transport(json.dumps([game()]).encode(),seen=seen))
            self.assertEqual(len(seen),1)
            self.assertEqual(seen[0].get_header("Authorization"),"Bearer fake-test-key")
            self.assertIn("https://api.collegebasketballdata.com/games?", seen[0].full_url)
            self.assertIn("season=2027", seen[0].full_url)
            self.assertNotIn("fake-test-key",seen[0].full_url)
            man=Path(result["manifest_path"]).read_bytes()
            raw=Path(result["raw_path"]).read_bytes()
            self.assertNotIn(b"fake-test-key",man)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),result["sha256"])
            self.assertEqual(result["rows"],1)

    def test_create_only_will_not_clobber_or_reuse_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=capture(tmp,[game()])
            with self.assertRaises(FileExistsError):
                capture(tmp,[game()])
            self.assertTrue(Path(original["raw_path"]).exists())

    def test_utc_window_bounded_to_daily_and_correct_season(self):
        with self.assertRaisesRegex(Hold,"REQUEST_MUST_COVER"):
            checked_window(2027,"2026-11-01T00:00:00Z","2026-11-04T00:00:00Z")
        with self.assertRaisesRegex(Hold,"SEASON_END_YEAR_WINDOW"):
            checked_window(2026,"2026-11-01T00:00:00Z","2026-11-02T00:00:00Z")
        with self.assertRaisesRegex(Hold,"UTC_Z"):
            checked_window(2027,"2026-11-01T00:00:00","2026-11-02T00:00:00Z")

    def test_broken_or_redirected_provider_response_rejected_without_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(Hold,"CONTENT_TYPE_OR_URL"):
                capture(tmp, [game()],transport=mock_transport(b"[]", wrong_url=True))
            with self.assertRaisesRegex(Hold,"CONTENT_TYPE_OR_URL"):
                capture(tmp, [game()],transport=mock_transport(b"<html>hi</html>",ctype="text/html"))
            self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_bad_payload_and_cap_protection(self):
        with self.assertRaisesRegex(Hold,"NON_JSON"):
            decoded(b'{"obj":true}')
        with self.assertRaisesRegex(Hold,"NON_JSON"):
            decoded(b'[{"x":1,"x":2}]')
        with self.assertRaisesRegex(Hold,"NON_JSON"):
            decoded(b'[NaN]')
        with self.assertRaisesRegex(Hold,"EXCESSIVE"):
            decoded(b"x"*(MAX_BODY+1))
        with self.assertRaisesRegex(Hold,"POSSIBLY_TRUNCATED"):
            decoded(b"[" + b"0,"*2999 + b"0]")

    def test_private_out_of_public_checkout(self):
        with self.assertRaisesRegex(Hold,"PUBLIC_GIT"):
            safe_path(ROOT/"models"/"cbb"/"not-private.json")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertNotEqual(safe_path(tmp),ROOT)

    def test_normalize_final_uses_local_observation_not_invented_publish_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap=capture(tmp,[game()])
            path=Path(tmp)/"finals.json"
            out=finals_from_capture(cap["raw_path"],cap["manifest_path"],output_path=path)
            self.assertEqual(out["finals"],1)
            report=json.loads(path.read_text())
            row=report["rows"][0]
            self.assertEqual(row["status"],"FINAL_RECEIPT_LOCAL_CAPTURE_UNAUTHENTICATED")
            r=row["final"]
            self.assertEqual(r["game_id"],"10")
            self.assertEqual(r["home_team_id"],"101")
            self.assertEqual(r["away_team_id"],"202")
            self.assertEqual(r["season"],2027)
            self.assertEqual(r["published_utc"],cap["observed_utc"])
            self.assertEqual(r["captured_utc"],cap["observed_utc"])
            self.assertEqual(r["publication_basis"],
                             "UPPER_BOUND_LOCAL_OBSERVATION_NOT_PROVIDER_PUBLICATION")
            self.assertEqual(r["sha256"],cap["sha256"])
            self.assertEqual(report["stake_u"],0)

    def test_nonfinal_unknown_and_future_games_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap=capture(tmp,[
                game(1,status="scheduled",homePoints=None,awayPoints=None),
                game(2,startDate="2026-11-16T10:00:00Z"),
                game(3,status="final",homePoints=None),
                game(4,awayTeamId=None),
            ])
            out=Path(tmp)/"finals.json"
            finals_from_capture(cap["raw_path"],cap["manifest_path"],output_path=out)
            rows=json.loads(out.read_text())["rows"]
            self.assertEqual(len(rows),4)
            self.assertEqual(rows[0]["status"],"NOT_FINAL_OR_FUTURE_EVENT")
            self.assertEqual(rows[1]["status"],"NOT_FINAL_OR_FUTURE_EVENT")
            self.assertEqual(rows[2]["status"],"BLOCKED")
            self.assertEqual(rows[3]["status"],"BLOCKED")

    def test_duplicate_ids_quarantined_all_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap=capture(tmp,[game(1),game(1),game(3)])
            report=Path(tmp)/"finals.json"
            finals_from_capture(cap["raw_path"],cap["manifest_path"],output_path=report)
            rows=json.loads(report.read_text())["rows"]
            self.assertEqual([r["status"] for r in rows],
                             ["BLOCKED","BLOCKED","FINAL_RECEIPT_LOCAL_CAPTURE_UNAUTHENTICATED"])
            self.assertIn("DUPLICATE_PROVIDER_GAME_ID",rows[0]["reason"])

    def test_original_bytes_mutation_fails_digest_without_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap=capture(tmp,[game()])
            source=Path(cap["raw_path"])
            source.write_bytes(source.read_bytes()+b" ")
            with self.assertRaisesRegex(Hold,"ORIGINAL_RESPONSE_SHA_MISMATCH"):
                finals_from_capture(source,cap["manifest_path"],output_path=Path(tmp)/"out.json")
            self.assertFalse((Path(tmp)/"out.json").exists())

    def test_manifest_editing_invalidates_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap=capture(tmp,[game()])
            m=Path(cap["manifest_path"])
            changed=json.loads(m.read_text())
            changed["documented_endpoint"]="https://malicious.example/"
            m.write_text(json.dumps(changed))
            with self.assertRaisesRegex(Hold,"UNVERIFIED_CAPTURE_PROVIDER"):
                finals_from_capture(cap["raw_path"],m,output_path=Path(tmp)/"out.json")

    def test_false_claim_of_final_and_ties_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap=capture(tmp,[game(1,homePoints=72,awayPoints=72)])
            report=Path(tmp)/"finals.json"
            out=finals_from_capture(cap["raw_path"],cap["manifest_path"],output_path=report)
            self.assertEqual(out["finals"],0)
            rows=json.loads(report.read_text())["rows"]
            self.assertIn("INVALID_FINAL_SCORE",rows[0]["reason"])

    def test_missing_clock_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(Hold,"CAPTURE_CLOCK_NOT_UTC"):
                capture(tmp,[game()],clock=datetime(2026,11,15,23,30))

    def test_manifests_and_reports_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap=capture(tmp,[game()])
            report=Path(tmp)/"finals.json"
            finals_from_capture(cap["raw_path"],cap["manifest_path"],output_path=report)
            with self.assertRaises(FileExistsError):
                finals_from_capture(cap["raw_path"],cap["manifest_path"],output_path=report)

    def test_season_rejected_when_unmatched_to_tipoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            cap=capture(tmp,[game(1,startDate="2025-11-15T20:00:00Z")])
            report=Path(tmp)/"finals.json"
            finals_from_capture(cap["raw_path"],cap["manifest_path"],output_path=report)
            self.assertIn("GAME_TIP_SEASON_MISMATCH",json.loads(report.read_text())["rows"][0]["reason"])


if __name__=="__main__":
    unittest.main()
