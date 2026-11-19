"""Synthetic CBB venue provenance gate regressions; no network or real venue claims."""
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from sportsedge.validation.cbb_venue_registry import verify_cbb_venue

ASOF=datetime(2026,11,18,12,0,tzinfo=timezone.utc)
HEADER="game_id,neutral,source,source_sha256,published_utc,captured_utc,tipoff_utc\n"
ORIGINAL="G1,1,ESPN,"+"a"*64+",2026-11-18T10:00:00Z,2026-11-18T11:00:00Z,2026-11-18T19:00:00Z\n"

class VenueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.games=Path(self.tmp.name)/"games.csv"
        self.registry=Path(self.tmp.name)/"venue.csv"
        self.games.write_text("game_id,home,away,neutral\nG1,A,B,1\nG2,C,D,0\n")
        self.registry.write_text(HEADER+ORIGINAL)

    def check(self):
        return verify_cbb_venue(str(self.games),str(self.registry),"G1",ASOF)

    def test_explicit_neutral_passes(self):
        self.assertIs(self.check(),True)
        self.games.write_text("game_id,neutral\nG1,0\n")
        self.registry.write_text(HEADER+ORIGINAL.replace("G1,1,","G1,0,"))
        self.assertIs(self.check(),False)

    def test_missing_or_nonsense_neutral_cannot_be_home(self):
        for flag in ("","None","false","2","0.0"):
            with self.subTest(flag=flag):
                self.games.write_text("game_id,neutral\nG1,"+flag+"\n")
                with self.assertRaisesRegex(ValueError,"NEUTRAL_FLAG_MUST_BE_EXPLICIT"):
                    self.check()

    def test_registry_disagreement_blocks(self):
        self.games.write_text("game_id,neutral\nG1,0\n")
        with self.assertRaisesRegex(ValueError,"FLAG_SOURCE_MISMATCH"):
            self.check()

    def test_missing_and_duplicated_registry_refused(self):
        self.registry.write_text(HEADER)
        with self.assertRaisesRegex(ValueError,"REGISTRY_MISSING_OR_DUPLICATE"):
            self.check()
        self.registry.write_text(HEADER+ORIGINAL+ORIGINAL)
        with self.assertRaisesRegex(ValueError,"REGISTRY_MISSING_OR_DUPLICATE"):
            self.check()

    def test_duplicate_game_quarantines(self):
        self.games.write_text("game_id,neutral\nG1,1\nG1,1\n")
        with self.assertRaisesRegex(ValueError,"GAME_MISSING_OR_DUPLICATE"):
            self.check()

    def test_future_or_posttip_provider_clocks_block(self):
        for replacement in (
           "2026-11-18T13:00:00Z,2026-11-18T14:00:00Z,2026-11-18T19:00:00Z",
           "2026-11-18T10:00:00Z,2026-11-18T20:00:00Z,2026-11-18T19:00:00Z",
           "2026-11-18T11:00:00Z,2026-11-18T10:00:00Z,2026-11-18T19:00:00Z"):
            with self.subTest(replacement=replacement):
                self.registry.write_text(HEADER+"G1,1,ESPN,"+"a"*64+","+replacement+"\n")
                with self.assertRaisesRegex(ValueError,"NOT_FROZEN_BEFORE_TIP"):
                    self.check()

    def test_future_start_invalid(self):
        self.registry.write_text(HEADER+ORIGINAL.replace("2026-11-18T19:00:00Z","2026-11-18T11:00:00Z"))
        with self.assertRaisesRegex(ValueError,"NOT_FROZEN_BEFORE_TIP"):
            self.check()

    def test_source_and_hash_must_be_declared(self):
        self.registry.write_text(HEADER+ORIGINAL.replace(",ESPN,",",UNVERIFIED,"))
        with self.assertRaisesRegex(ValueError,"SOURCE_UNSUPPORTED"):
            self.check()
        self.registry.write_text(HEADER+ORIGINAL.replace("a"*64,"fake"))
        with self.assertRaisesRegex(ValueError,"SOURCE_SHA_INVALID"):
            self.check()

    def test_shifted_cells_header_and_empty_registry_rejected(self):
        self.registry.write_text(HEADER+ORIGINAL.strip()+",extra\n")
        with self.assertRaisesRegex(ValueError,"CSV_ROW_INVALID"):
            self.check()
        self.registry.write_text(HEADER.replace("game_id,","event_id,")+ORIGINAL)
        with self.assertRaisesRegex(ValueError,"REGISTRY_SCHEMA_INVALID"):
            self.check()

    def test_source_clock_must_be_utc_z(self):
        self.registry.write_text(HEADER+ORIGINAL.replace("2026-11-18T10:00:00Z","2026-11-18T10:00:00-06:00"))
        with self.assertRaisesRegex(ValueError,"UTC_Z_TIME_REQUIRED"):
            self.check()
        with self.assertRaisesRegex(ValueError,"ASOF_MUST_BE_UTC"):
            verify_cbb_venue(str(self.games),str(self.registry),"G1",
                             datetime(2026,11,18,12,0))

if __name__=="__main__":
    unittest.main()
