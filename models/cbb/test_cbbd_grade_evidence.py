"""Provider-free grade evidence archive integrity tests."""
import io
import json
import tarfile
import unittest
from test_cbbd_paper_ledger import LedgerBase
import cbbd_paper_ledger as LG
from cbbd_grade_evidence import bundle


class GradeEvidence(LedgerBase):
    def files(self):
        self.freeze(self.make_card())
        finals, raw, man = self.finals([("9001", 1, 2, 80, 77)])
        from test_cbbd_paper_ledger import T_LATER
        LG.append(self.ledger, LG.final_entries(finals, raw, man), clock=lambda: T_LATER)
        fp = self.dir / "derived.json"
        fp.write_text(json.dumps(finals))
        report = self.dir / "eval.json"
        report.write_text(json.dumps(LG.evaluate(LG.read(self.ledger)), allow_nan=False))
        return raw, man, fp, report, self.ledger

    def test_bundle_retains_originals_and_reproducible_report(self):
        paths = self.files()
        data = bundle(*paths)
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            self.assertEqual(set(t.getnames()), {"provider.raw.json", "provider.manifest.json",
                "finals.json", "eval.json", "ledger.jsonl", "bundle-index.json"})
            self.assertEqual(t.extractfile("provider.raw.json").read(), paths[0].read_bytes())
            self.assertEqual(t.extractfile("ledger.jsonl").read(), paths[4].read_bytes())

    def test_mutated_evaluation_is_rejected(self):
        paths = self.files()
        rep = json.loads(paths[3].read_text())
        rep["official_counted"] = 1
        paths[3].write_text(json.dumps(rep))
        with self.assertRaisesRegex(ValueError, "GRADE_EVIDENCE_REPORT_MISMATCH"):
            bundle(*paths)

    def test_changed_provider_bytes_are_rejected(self):
        paths = self.files()
        paths[0].write_bytes(paths[0].read_bytes() + b" ")
        with self.assertRaises(ValueError):
            bundle(*paths)


class HalfForwardQuality(LedgerBase):
    def inputs(self):
        from datetime import timedelta
        from hashlib import sha256
        import test_cbb_run_it as T
        from cbbd_half_evidence import fit_full_to_first_half, project_first_halves
        card = self.make_card()
        raw = json.dumps([{"id": i+1, "season": T.S.SEASON, "homeTeamId": 1, "awayTeamId": 2,
                         "status": "final", "startTimeTbd": False,
                         "startDate": T.R.utcz(T.NOW-timedelta(days=8-i//8, hours=2)),
                         "homePeriodPoints": [30,40], "awayPeriodPoints": [35,34],
                         "homePoints": 70, "awayPoints": 69} for i in range(56)]).encode()
        def manifest(blob, observed):
            return {"format": "CBBD_GAMES_CAPTURE_V1", "provider": "collegebasketballdata",
                    "documented_endpoint": "https://api.collegebasketballdata.com/games",
                    "source_sha256": sha256(blob).hexdigest(), "source_bytes": len(blob),
                    "returned_rows": len(json.loads(blob)), "season": T.S.SEASON,
                    "local_observed_utc": observed}
        man = manifest(raw, T.OBS)
        fit = fit_full_to_first_half(raw, man, asof_utc=card["freeze_utc"])
        half = {"label": "PAPER_0U", "fit": fit, "rows": project_first_halves(card, fit)}
        finals = json.dumps([{"id": 9001, "season": T.S.SEASON, "homeTeamId": 1, "awayTeamId": 2,
                          "status": "final", "startTimeTbd": False, "startDate": T.S.TIP,
                          "homePeriodPoints": [31,40], "awayPeriodPoints": [35,34],
                          "homePoints": 71, "awayPoints": 69}]).encode()
        fm = manifest(finals, "2026-11-22T03:00:00Z")
        return [card, half, raw, man, finals, fm]

    def test_original_half_forecast_replay_and_exact_final_join(self):
        from cbbd_half_forward_quality import audit
        args = self.inputs()
        report = audit(*args, evaluated_utc="2026-11-22T04:00:00Z")
        self.assertEqual(report["input_rows"], len(args[0]["rows"]))
        self.assertEqual(report["graded"], 1)
        row = next(r for r in report["rows"] if r["state"] == "GRADED")
        self.assertEqual(row["actual_home"], 31)
        self.assertAlmostEqual(report["metrics"]["total"]["mae"], abs(row["total_error"]))
        self.assertFalse(report["holdout_calibrated"])

    def test_rewritten_half_forecast_is_refused(self):
        from cbbd_half_forward_quality import audit
        args = self.inputs()
        args[1]["rows"][0]["home_points"] = 1000
        with self.assertRaisesRegex(ValueError, "HALF_ORIGINAL_REPORT_REPLAY_MISMATCH"):
            audit(*args, evaluated_utc="2026-11-22T04:00:00Z")


if __name__ == "__main__":
    unittest.main()
