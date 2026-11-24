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


if __name__ == "__main__":
    unittest.main()
