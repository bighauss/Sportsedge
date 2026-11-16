"""Archived public PBP -> EPA synthetic PIT and original-byte provenance tests."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import csv
import gzip
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from epa_from_public_archive import build_from_archive, main
from score_walkforward_pit import REPO_ROOT
from test_epa_ridge_pit import GAME1, GAME2, fixture

CAPTURED="2026-11-15T17:00:00Z"
ASOF="2026-11-15T18:00:00Z"


def digest(raw):
    return "sha256:" + sha256(raw).hexdigest()


def build_zip(*, plays=None, captured=CAPTURED,
              modify_sidecar=None, modify_meta=None, extra_members=()):
    plays=fixture() if plays is None else plays
    fields=("game_id","week","drive","play_id","posteam","defteam",
            "pass","rush","epa","wp")
    buf=StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=fields,lineterminator="\n")
    writer.writeheader()
    for row in plays:
        record={key:row.get(key,"") for key in fields}
        record["week"]="1"
        writer.writerow(record)
    pbp=gzip.compress(buf.getvalue().encode("utf-8"),mtime=0)
    raw_sha=digest(pbp)
    filename="NFL_PBP_2026_"+raw_sha[7:23]+".csv.gz"
    folder="forward_nfl_fixture_1/"
    source_manifest={
        "state":"RAW_PUBLIC_SOURCE_ARCHIVED_RESEARCH_ONLY",
        "asset":"NFL_PBP_2026",
        "original_bytes_sha256":raw_sha,"provider_digest":raw_sha,
        "rows":len(plays),"retrieved_at_utc":captured,
        "provider_updated_at_claim":"2026-11-15T16:00:00Z",
        "source_schema_scan_mode":"BOUNDED_STREAMING_GZIP_CSV",
    }
    if modify_sidecar:
        modify_sidecar(source_manifest)
    meta={
        "state":"PAPER_0U_RAW_PUBLIC_SOURCE_CAPTURE","sport":"NFL",
        "collected_run_start_utc":"2026-11-15T16:55:00Z",
        "requested_assets":["NFL_PBP_2026"],"captured_asset_count":1,
        "asset_receipts":[{
            "asset_id":"NFL_PBP_2026",
            "source_id":"NFLVERSE_PBP",
            "raw_sha256":raw_sha,"raw_bytes":len(pbp),
            "original_filename":filename,"source_rows":len(plays),
            "retrieved_at_utc":captured,
        }],
        "collected_before_declared_event":False,
    }
    if modify_meta:
        modify_meta(meta)
    writer_buf=BytesIO()
    with zipfile.ZipFile(writer_buf,mode="w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(folder+"capture_manifest.json",
                   json.dumps(meta,sort_keys=True))
        z.writestr(folder+filename,pbp)
        z.writestr(folder+filename+".manifest.json",
                   json.dumps(source_manifest,sort_keys=True))
        for name,blob in extra_members:
            z.writestr(name,blob)
    raw=writer_buf.getvalue()
    return raw,digest(raw),raw_sha


def build(arch=None, sha=None, manifest=None, **kwargs):
    if arch is None:
        arch,sha,_=build_zip()
    if manifest is None:
        manifest={"g1":GAME1,"g2":GAME2}
    return build_from_archive(
        arch,expected_archive_sha256=sha,
        game_manifest=manifest,
        game_manifest_sha256=digest(json.dumps(manifest).encode()),
        asof_utc=kwargs.pop("asof_utc",ASOF),
        **kwargs,
    )


class ArchivedPBPBridgeTests(unittest.TestCase):
    def test_valid_archived_plays_feed_unchanged_ridge_research(self):
        arch,archive_sha,source_sha=build_zip()
        out=build(arch,archive_sha)
        self.assertEqual(out["status"],"PAPER_HOLD_0U")
        self.assertEqual(out["games_used"],2)
        self.assertEqual(out["census"]["source_rows"],8)
        self.assertEqual(out["units"]["pass"]["play_count"],4)
        self.assertEqual(out["units"]["rush"]["play_count"],4)
        self.assertEqual(out["approved_stake_u"],0)
        self.assertEqual(out["official_counted"],0)
        self.assertEqual(out["archive_provenance"]["source_raw_sha256"],source_sha)
        self.assertEqual(out["archive_provenance"]["original_archive_sha256"],archive_sha)
        self.assertFalse(out["archive_provenance"]["original_source_publication_authenticated"])
        self.assertIsNone(out["market_ev"])
        self.assertIsNone(out["win_probability"])

    def test_mutated_zip_does_not_pass_original_sha(self):
        arch,sha,_=build_zip()
        with self.assertRaisesRegex(ValueError,"ARCHIVED_GITHUB_ZIP_SHA_MISMATCH"):
            build(arch+b"corrupt",sha)

    def test_missing_game_manifest_fail_closed(self):
        arch,sha,_=build_zip()
        with self.assertRaisesRegex(ValueError,"PBP_GAME_MANIFEST_MISSING"):
            build(arch,sha,manifest={"g1":GAME1})

    def test_source_capture_later_than_model_asof_rejected(self):
        arch,sha,_=build_zip(captured="2026-11-15T19:00:00Z")
        with self.assertRaisesRegex(ValueError,"PUBLIC_PBP_CAPTURE_AFTER_FORECAST"):
            build(arch,sha)

    def test_stale_or_tampered_sidecar_sha_refused(self):
        arch,sha,_=build_zip(modify_sidecar=lambda s:s.update(
            provider_digest="sha256:"+"f"*64))
        with self.assertRaisesRegex(ValueError,"PBP_SIDECAR_SOURCE_IDENTITY_MISMATCH"):
            build(arch,sha)

    def test_pbp_missing_drive_or_play_id_refused(self):
        bad=fixture()
        for r in bad:
            r.pop("drive",None)
        arch,sha,_=build_zip(plays=bad)
        with self.assertRaisesRegex(ValueError,"PBP_DRIVE_MISSING"):
            build(arch,sha)

    def test_duplicate_zip_member_quarantined(self):
        arch,sha,_=build_zip(extra_members=(
            ("forward_nfl_fixture_1/capture_manifest.json",b"BAD"),
        ))
        with self.assertRaisesRegex(ValueError,"DUPLICATE_ZIP_ARCHIVE_MEMBER"):
            build(arch,sha)

    def test_traversal_member_rejected_without_extraction(self):
        arch,sha,_=build_zip(extra_members=(("../bad",b"secret"),))
        with self.assertRaisesRegex(ValueError,"ZIP_PATH_TRAVERSAL_OR_NONCANONICAL"):
            build(arch,sha)

    def test_raw_pbp_source_count_must_match_captured_manifest(self):
        arch,sha,_=build_zip(modify_meta=lambda m:m["asset_receipts"][0].update(
            source_rows=999))
        with self.assertRaisesRegex(ValueError,"SOURCE_PBP_RECORD_CENSUS_CHANGED"):
            build(arch,sha)

    def test_nonfinite_play_epa_fails_without_estimated_fill(self):
        bad=fixture()
        bad[0]["epa"]="NaN"
        arch,sha,_=build_zip(plays=bad)
        with self.assertRaisesRegex(ValueError,"NONFINITE_EPA"):
            build(arch,sha)

    def test_capture_marked_incomplete_not_accepted(self):
        arch,sha,_=build_zip(modify_meta=lambda m:m.update(
            state="BLOCK_INCOMPLETE_PUBLIC_CAPTURE"))
        with self.assertRaisesRegex(ValueError,"SOURCE_CAPTURE_NOT_COMPLETE"):
            build(arch,sha)

    def test_duplicate_json_keys_in_capture_manifest_rejected(self):
        arch,sha,_=build_zip(extra_members=())
        with zipfile.ZipFile(BytesIO(arch)) as z:
            files={name:z.read(name) for name in z.namelist()}
        name=next(p for p in files if p.endswith("/capture_manifest.json"))
        files[name]=b'{"state":"PAPER_0U_RAW_PUBLIC_SOURCE_CAPTURE","state":"FAKE"}'
        b=BytesIO()
        with zipfile.ZipFile(b,"w") as z:
            for key,value in files.items():
                z.writestr(key,value)
        fresh=b.getvalue()
        with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
            build(fresh,digest(fresh))

    def test_original_source_zip_not_worked_on_inside_public_repo(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-pbp-model-") as tmp:
            arch,sha,_=build_zip()
            manifest={"g1":GAME1,"g2":GAME2}
            files={
                "archive":Path(tmp)/"source.zip",
                "manifest":Path(tmp)/"games.json",
                "output":Path(tmp)/"ratings.json",
            }
            files["archive"].write_bytes(arch)
            files["manifest"].write_text(json.dumps(manifest),encoding="utf-8")
            argv=[
                "epa_from_public_archive.py",
                "--source-archive",str(files["archive"]),
                "--expected-archive-sha256",sha,
                "--game-manifest",str(files["manifest"]),
                "--expected-game-manifest-sha256",digest(files["manifest"].read_bytes()),
                "--asof-utc",ASOF,
                "--out",str(files["output"]),
            ]
            with patch.object(sys,"argv",argv),redirect_stdout(StringIO()):
                main()
            self.assertEqual(stat.S_IMODE(files["output"].stat().st_mode),0o600)
            saved=files["output"].read_bytes()
            self.assertEqual(json.loads(saved)["archive_provenance"][
                "original_archive_sha256"],sha)
            with patch.object(sys,"argv",argv),redirect_stdout(StringIO()):
                with self.assertRaises(FileExistsError):
                    main()
            self.assertEqual(files["output"].read_bytes(),saved)
            args=list(argv)
            args[args.index("--out")+1]=str(REPO_ROOT/"private_archive_output.json")
            with patch.object(sys,"argv",args),self.assertRaisesRegex(
                ValueError,"PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
                main()

    def test_wrong_original_game_manifest_hash_rejected(self):
        with tempfile.TemporaryDirectory(prefix="sportsedge-pbp-model-") as tmp:
            arch,sha,_=build_zip()
            data={"g1":GAME1,"g2":GAME2}
            zf=Path(tmp)/"source.zip"
            gf=Path(tmp)/"games.json"
            zf.write_bytes(arch)
            gf.write_text(json.dumps(data),encoding="utf-8")
            argv=[
                "epa_from_public_archive.py",
                "--source-archive",str(zf),
                "--expected-archive-sha256",sha,
                "--game-manifest",str(gf),
                "--expected-game-manifest-sha256","sha256:"+"0"*64,
                "--asof-utc",ASOF,
                "--out",str(Path(tmp)/"out.json"),
            ]
            with patch.object(sys,"argv",argv),self.assertRaisesRegex(
                ValueError,"GAME_MANIFEST_ORIGINAL_BYTES_HASH_MISMATCH"):
                main()
            self.assertFalse((Path(tmp)/"out.json").exists())


if __name__=="__main__":
    unittest.main()
