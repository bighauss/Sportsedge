"""Dry-run grade frozen picks from reviewed, hash-bound ESPN originals."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from sportsedge.validation import nfl_frozen_csv
from sportsedge.validation import espn_final_evidence as espn
from sportsedge.validation import paper_grade_batch as batch
from sportsedge.validation import paper_ledger as ledger

SCHEMA = 'sportsedge-espn-paper-bridge-v1'


def dry_run(manifest, *, now=None, private_receipt=None, include_intake_rows=False):
    path = ledger.private_file(manifest, 'BRIDGE_MANIFEST')
    if not 0 < path.stat().st_size <= ledger.MAX_EVIDENCE_BYTES:
        raise ledger.Blocked('BRIDGE_MANIFEST_SIZE_INVALID')
    manifest_bytes = path.read_bytes()
    plan = ledger.strict_json(manifest_bytes)
    asof = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(asof, datetime) or asof.utcoffset() is None:
        raise ledger.Blocked('ASOF_REQUIRES_OFFSET')
    if isinstance(plan, dict) and plan.get('schema') == nfl_frozen_csv.SCHEMA:
        result, rows = nfl_frozen_csv.grade(path.parent, plan, asof)
        if private_receipt is not None:
            _receipt(private_receipt, manifest_bytes, {'csv_sha256': result['csv_sha256'], 'rows': rows})
        if include_intake_rows:
            result['csv_rows'] = rows
        return result
    if (not isinstance(plan, dict) or set(plan) != {'schema', 'entries'}
            or plan['schema'] != SCHEMA or not isinstance(plan['entries'], list)
            or not 0 < len(plan['entries']) <= batch.MAX_PICKS):
        raise ledger.Blocked('INVALID_BRIDGE_MANIFEST')
    staged, intake, temporary = [], [], []

    def write(doc):
        raw = json.dumps(doc, sort_keys=True, allow_nan=False).encode()
        with NamedTemporaryFile(dir=path.parent, prefix='.paper-bridge-', delete=False) as f:
            temporary.append(Path(f.name))
            f.write(raw)
        return dict(path=temporary[-1].name, sha256=hashlib.sha256(raw).hexdigest())

    try:
        for src in plan['entries']:
            if not isinstance(src, dict) or set(src) - {'kickoff_utc', 'pick', 'taken', 'espn_original', 'espn_ids_reviewed'}:
                staged.append(None)
                intake.append('INVALID_ENTRY')
                continue
            row = {k: src[k] for k in ('kickoff_utc', 'pick', 'taken') if k in src}
            staged.append(row)
            if src.get('espn_original') is None:
                intake.append('NO_FINAL_SOURCE')
                continue
            try:
                market, pick, kickoff, _, _ = batch._pick(path.parent, row, asof)
                if src.get('espn_ids_reviewed') is not True:
                    raise ledger.Blocked('EXACT_ESPN_IDS_REVIEW_REQUIRED')
                # Market uses an empty string for a non-player selection.
                if market.player_id != '':
                    raise ledger.Blocked('PLAYER_ID_CROSSWALK_NOT_ADMITTED')
                spec = src['espn_original']
                _, captured, digest = ledger.source(path.parent, spec, kickoff, 'postgame')
                if captured > asof:
                    raise ledger.Blocked('FINAL_AFTER_ASOF')
                raw = ledger.private_file(path.parent / spec['path'], 'ESPN_ORIGINAL').read_bytes()
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise ledger.Blocked('SOURCE_BYTES_CHANGED')
                report = espn.inspect(raw, event_id=market.event_id, sport=market.sport,
                                      home_espn_id=pick['home_id'], away_espn_id=pick['away_id'],
                                      captured_utc=captured.isoformat(), kickoff_utc=kickoff.isoformat())
                final = dict(report['candidate'], source_original_sha256=digest)
                row['final'] = dict(write(final), captured_at_utc=captured.isoformat())
                intake.append('FINAL_STAGED')
            except batch.BAD_INPUT:
                intake.append('FINAL_INPUT_BLOCKED')
        spec = write(dict(schema=batch.SCHEMA, entries=staged))
        rejected = {i for i, status in enumerate(intake) if status == 'FINAL_INPUT_BLOCKED'}
        result = batch.run_batch(path.parent / spec['path'], now=asof, rejected_final_indices=rejected)
        result['espn_intake'] = dict(Counter(intake))
        result['manifest_entries'] = len(staged)
        if not sum(result['picks'].values()) == len(intake) == len(staged) == len(plan['entries']):
            raise ledger.Blocked('GRADE_DENOMINATOR_MISMATCH')
        if include_intake_rows:
            result['espn_intake_rows'] = intake
        if private_receipt is not None:
            _receipt(private_receipt, manifest_bytes, {'intake_by_entry': intake})
        return result
    finally:
        for p in temporary:
            p.unlink(missing_ok=True)


def _receipt(path, manifest_bytes, fields):
    target = ledger.private_file(path, 'INTAKE_RECEIPT', required=False)
    fields['manifest_sha256'] = hashlib.sha256(manifest_bytes).hexdigest()
    with NamedTemporaryFile(dir=target.parent) as receipt:
        receipt.write(json.dumps(fields).encode())
        receipt.flush()
        os.link(receipt.name, target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--private-receipt', type=Path, help='new owner-only JSON file with intake status in manifest order')
    args = parser.parse_args(argv)
    try:
        result = dry_run(args.manifest, private_receipt=args.private_receipt)
    except batch.BAD_INPUT:
        print('ESPN_PAPER_BRIDGE_BLOCKED')
        return 2
    print(json.dumps(result, sort_keys=True))
    return 2 if any(('BLOCKED' in k or k == 'INVALID_ENTRY')
                    for group in ('picks', 'results', 'prices', 'espn_intake') for k in result.get(group, {})) else 0


if __name__ == '__main__':
    raise SystemExit(main())
