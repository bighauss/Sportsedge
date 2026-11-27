import hashlib
import io
import tempfile
import unittest
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from research.sportsleader.intake import ingest, ROOT

class AssetIntegrity(unittest.TestCase):
    def setUp(self):
        sink = pa.BufferOutputStream()
        pq.write_table(pa.table({"game_id": ["1", "2"]}), sink)
        self.raw = sink.getvalue().to_pybytes()
        self.entry = dict(league="cbb", dataset="games", season=2025,
                          url=ROOT+"cbb_games/2025.parquet",
                          sha256=hashlib.sha256(self.raw).hexdigest(),
                          bytes=len(self.raw), rows=2)

    def opener(self, url, timeout):
        return io.BytesIO(self.raw)

    def test_publish_and_replay(self):
        with tempfile.TemporaryDirectory() as root:
            target = ingest(self.entry, root, self.opener)
            self.assertEqual(target.read_bytes(), self.raw)
            self.assertEqual(ingest(self.entry, root, self.opener), target)
            self.assertEqual(len(list(Path(root).iterdir())), 1)

    def test_reject_and_cleanup(self):
        for key, value in [("sha256", "0"*64), ("rows", 3),
                           ("bytes", len(self.raw)-1), ("bytes", len(self.raw)+1)]:
            with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):
                    ingest(dict(self.entry, **{key:value}), root, self.opener)
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_corrupted_existing_asset(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / (self.entry["sha256"] + ".parquet")
            target.write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                ingest(self.entry, root, self.opener)
            self.assertEqual(target.read_bytes(), b"corrupt")
