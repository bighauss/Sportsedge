"""Build a private, source-bound CBB grade evidence bundle before ledger advancement."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

import cbbd_paper_ledger as LG
from cbbd_frozen_final_join import verify_provider_originals


def bundle(raw_path, manifest_path, finals_path, report_path, ledger_path):
    paths = {"provider.raw.json": Path(raw_path), "provider.manifest.json": Path(manifest_path),
             "finals.json": Path(finals_path), "eval.json": Path(report_path),
             "ledger.jsonl": Path(ledger_path)}
    if any(p.is_symlink() or not p.is_file() for p in paths.values()):
        raise ValueError("GRADE_EVIDENCE_FILE_INVALID")
    files = {n: p.read_bytes() for n, p in paths.items()}
    finals = json.loads(files["finals.json"])
    report = json.loads(files["eval.json"])
    digest = verify_provider_originals(finals, paths["provider.raw.json"], paths["provider.manifest.json"])
    if digest != hashlib.sha256(files["provider.raw.json"]).hexdigest():
        raise ValueError("GRADE_EVIDENCE_SOURCE_HASH")
    entries = LG.parse_ledger(files["ledger.jsonl"])
    if report != LG.evaluate(entries):
        raise ValueError("GRADE_EVIDENCE_REPORT_MISMATCH")
    if report.get("official_counted") != 0 or report.get("approved_stake_u") != 0:
        raise ValueError("GRADE_EVIDENCE_NON_PAPER")
    manifest = {"label": "PAPER_0U", "source_authenticated": False,
                "files": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
    files["bundle-index.json"] = json.dumps(manifest, sort_keys=True).encode()
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        for name, data in sorted(files.items()):
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(data), 0o600
            archive.addfile(item, io.BytesIO(data))
    return out.getvalue()
