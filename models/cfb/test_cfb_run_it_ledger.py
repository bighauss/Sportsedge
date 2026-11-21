"""Offline: CFB RUN IT persistent PAPER ledger (append, tamper, re-freeze refusal, restore round-trip)."""
import copy, datetime as dt, json, os, shutil, subprocess, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, ROOT)
import cfb_run_it as R
import test_cfb_run_it as F
from models.cfb import cfb_ledger as L

NOW = dt.datetime.fromisoformat("2026-11-21T15:00:00+00:00")

def doc(now=NOW):
    cap = F.fixture()
    card, projs, wh, _ = R.run(copy.deepcopy(F.INTAKE), cap, now, lambda *_: cap["_weather"])
    return R.recheck(R.to_doc(card, projs, wh, F.INTAKE, now, []), now)

class Ledger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); os.chmod(self.tmp, 0o700)
        self.d = os.path.join(self.tmp, "ledger"); self.p = os.path.join(self.d, "cfb_run_it_ledger.jsonl")
    def tearDown(self): shutil.rmtree(self.tmp)

    def test_append_card_frozen_paper(self):
        d = doc(); e = R.freeze_ledger(d, self.p, NOW)
        self.assertEqual((e["type"], e["seq"], e["official_counted"], e["approved_stake_u"]), ("CARD_FROZEN", 1, 0, 0))
        self.assertEqual(len(e["rows"]), len(d["card"]["rows"])); self.assertTrue(e["game_ids"])
        self.assertEqual(len(e["card_sha256"]), 64)
        self.assertEqual(L.verify(self.p)[0]["entry_sha256"], e["entry_sha256"])

    def test_requires_recheck(self):
        d = doc(); del d["card"]["rechecked_utc"]
        with self.assertRaisesRegex(L.LedgerRefused, "NOT_RECHECKED"): R.freeze_ledger(d, self.p, NOW)

    def test_refuses_refrozen_game(self):
        R.freeze_ledger(doc(), self.p, NOW)
        with self.assertRaisesRegex(L.LedgerRefused, "GAME_ALREADY_FROZEN"):
            R.freeze_ledger(doc(), self.p, NOW + dt.timedelta(minutes=5))
        self.assertEqual(len(L.verify(self.p)), 1)

    def test_tamper_detected(self):
        R.freeze_ledger(doc(), self.p, NOW)
        raw = open(self.p, "rb").read().replace(b'"approved_stake_u":0', b'"approved_stake_u":1', 1)
        open(self.p, "wb").write(raw)
        with self.assertRaises(L.LedgerRefused): L.verify(self.p)
        d = doc(); d["model_projections"]["games"] = []; d["card"]["rows"] = []
        with self.assertRaises(L.LedgerRefused): R.freeze_ledger(d, self.p, NOW)

    def test_restore_then_append_round_trip_cli(self):
        R.freeze_ledger(doc(), self.p, NOW)
        restored = os.path.join(self.tmp, "restored"); os.mkdir(restored, 0o700)
        rp = os.path.join(restored, "ledger.jsonl")
        with open(rp, "wb") as f: f.write(open(self.p, "rb").read())
        os.chmod(rp, 0o600)
        self.assertEqual(len(L.verify(rp)), 1)
        later = NOW + dt.timedelta(minutes=10)
        d2 = doc(later)
        for g in d2["model_projections"]["games"]: g["cfbd_game_id"] = "9" + str(g["cfbd_game_id"])
        out = os.path.join(self.tmp, "out"); os.mkdir(out)
        json.dump(d2, open(os.path.join(out, "cfb_run_it.json"), "w"), default=str)
        r = subprocess.run([sys.executable, os.path.join(HERE, "cfb_run_it.py"), "--freeze-ledger", rp,
                            "--out", out, "--now", later.isoformat()], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        es = L.verify(rp); self.assertEqual([e["seq"] for e in es], [1, 2]); self.assertTrue(es[1]["game_ids"])
        self.assertEqual(es[1]["prev_entry_sha256"], es[0]["entry_sha256"])
        r = subprocess.run([sys.executable, os.path.join(HERE, "cfb_run_it.py"), "--freeze-ledger", rp,
                            "--out", out, "--now", later.isoformat()], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2); self.assertIn("GAME_ALREADY_FROZEN", r.stderr)

if __name__ == "__main__":
    unittest.main()
