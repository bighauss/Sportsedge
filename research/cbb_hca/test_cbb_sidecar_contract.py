"""Synthetic runner-shaped evidence, not historical validation."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from cbbd_prospective_capture import BASE
from test_cbb_run_it import provider, run, OBS, S
from research.cbb_hca.collect_sidecar import discover_and_record, source_context, digest

def setup(root):
    cap=root/"capture";carddir=root/"card";rd=cap/"ratings";gd=cap/"games"
    for d in (cap,carddir,rd,gd):d.mkdir(mode=0o700)
    def put(path,value,*,raw=False):
        b=value if raw else json.dumps(value,sort_keys=True,allow_nan=False).encode()
        path.write_bytes(b);path.chmod(0o600);return b
    card,_,_=run(carddir/"work")
    cardpath=carddir/"cbb_card.json";put(cardpath,card)
    games,boxes=provider();today=[r for r in games if r["status"]!="final"];history=[r for r in games if r["status"]=="final"]
    ratings=S.ratings_body();rr=dict(S.receipt(ratings),file="cbbd_ratings_adjusted.json")
    put(rd/rr["file"],ratings,raw=True);put(rd/"receipt.json",dict(receipts=[rr]))
    tr=put(gd/f"cbbd_games_{S.SEASON}_20261121T140000000000Z.raw.json",today)
    sr=put(gd/"cbbd_games_season.raw.json",history);br=put(gd/"cbbd_games_teams.raw.json",boxes)
    man=dict(format="CBBD_GAMES_CAPTURE_V1",provider="collegebasketballdata",documented_endpoint=BASE,
        season=S.SEASON,source_sha256=digest(tr),source_bytes=len(tr),returned_rows=len(today),local_observed_utc=OBS)
    put(gd/f"cbbd_games_{S.SEASON}_20261121T140000000000Z.manifest.json",man)
    def rec(source,b):return dict(source=source,sha256=digest(b),bytes=len(b),observed_utc=OBS)
    put(carddir/"receipts.json",[rr,rec("cbbd_games",tr),rec("cbbd_games_season",sr),rec("cbbd_games_teams",br)])
    return cardpath,cap

class Sidecar(unittest.TestCase):
    def test_actual_runner_parity_and_create_only(self):
        with tempfile.TemporaryDirectory() as d:
            c,cap=setup(Path(d));original=c.read_bytes()
            result=discover_and_record(c,cap,cap/"factorial_sidecar",clock=lambda:datetime(2026,11,21,15,1,tzinfo=timezone.utc))
            self.assertGreater(result["forecasts_written"],0)
            self.assertEqual(c.read_bytes(),original)
            self.assertEqual(result["source_receipts"]["parent_card_bytes"],digest(original))
            with self.assertRaises(FileExistsError):
                discover_and_record(c,cap,cap/"factorial_sidecar")
    def test_tampered_source(self):
        with tempfile.TemporaryDirectory() as d:
            c,cap=setup(Path(d));p=cap/"games"/"cbbd_games_season.raw.json"
            p.write_bytes(p.read_bytes()+b" ")
            with self.assertRaisesRegex(ValueError,"SOURCE_RECEIPT_MISMATCH"):
                source_context(c,cap)
    def test_tampered_card(self):
        with tempfile.TemporaryDirectory() as d:
            c,cap=setup(Path(d));r=json.loads(c.read_bytes());r["approved_stake_u"]=False;c.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,"PARENT_CARD_INVALID"):
                source_context(c,cap)
    def test_rehashed_card_with_changed_tip_is_rejected(self):
        import cbbd_paper_card as pc
        with tempfile.TemporaryDirectory() as d:
            c,cap=setup(Path(d))
            card=json.loads(c.read_bytes())
            row=next(r for r in card["rows"] if r["status"]=="PROJECTED")
            row["tipoff_utc"]="2026-11-25T01:00:00Z"
            card["card_sha256"]=pc.card_digest(card)
            c.write_text(json.dumps(card))
            with self.assertRaisesRegex(ValueError,"PARENT_PROJECTED_SCHEDULE_IDENTITY_MISMATCH"):
                source_context(c,cap)
    def test_expired_game_no_forecast(self):
        with tempfile.TemporaryDirectory() as d:
            c,cap=setup(Path(d))
            r=discover_and_record(c,cap,cap/"factorial_sidecar",clock=lambda:datetime(2026,11,22,12,tzinfo=timezone.utc))
            self.assertEqual(r["forecasts_written"],0)
            self.assertTrue(all(x["state"]=="HOLD" for x in r["rows"]))

if __name__=="__main__":unittest.main()
