"""Bounded, streaming gzip CSV census for public nflverse PBP source releases.

The full-season PBP can exceed the small generic 80MB decompressed CSV
parser's cap. Never materialize its >20k wide records into a Python list.
No models, inferred timestamps, odds or pregame features are generated here.
"""
from __future__ import annotations

import csv
import gzip
import io
from typing import Iterator

REQUIRED = frozenset({
    "game_id", "week", "posteam", "defteam", "epa", "wp", "pass", "rush",
})
MAX_DECOMPRESSED_BYTES = 600_000_000
MAX_PHYSICAL_LINE_BYTES = 4_000_000
MAX_CSV_RECORDS = 1_000_000


def _lines(gz: gzip.GzipFile, *, max_bytes: int, max_line: int) -> Iterator[str]:
    total = 0
    while True:
        # Capped physical read prevents a malicious unbounded CSV field
        # from accumulating in memory before the total cap is checked.
        buf = gz.readline(max_line + 1)
        if not buf:
            return
        if len(buf) > max_line:
            raise ValueError("PBP_CSV_PHYSICAL_LINE_TOO_LONG")
        total += len(buf)
        if total > max_bytes:
            raise ValueError("PBP_DECOMPRESSED_BYTES_EXCEED_LIMIT")
        yield buf.decode("utf-8-sig")


def scan_pbp_gzip(
    original_bytes: bytes,
    *,
    max_decoded_bytes: int = MAX_DECOMPRESSED_BYTES,
    max_line_bytes: int = MAX_PHYSICAL_LINE_BYTES,
    max_rows: int = MAX_CSV_RECORDS,
) -> tuple[tuple[str, ...], int]:
    """Return validated header and row count without retaining PBP rows.

    Verifies gzip trailer by exhausting the stream. Checks the EPA feature
    columns needed by SportsEdge, duplicates/blank headers, ragged rows and
    invalid game/week identifiers. Missing EPA on individual special-teams
    rows is NOT imputed or misreported as a successful modeled play.
    """
    if (not isinstance(original_bytes, bytes) or
            not original_bytes.startswith(b"\x1f\x8b")):
        raise ValueError("PBP_GZIP_RAW_BYTES_REQUIRED")
    if (type(max_decoded_bytes) is not int or max_decoded_bytes < 1024 or
            type(max_line_bytes) is not int or max_line_bytes < 128 or
            type(max_rows) is not int or max_rows < 1):
        raise ValueError("INVALID_PBP_SCAN_CAP")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(original_bytes), mode="rb") as gz:
            reader = csv.DictReader(
                _lines(gz, max_bytes=max_decoded_bytes, max_line=max_line_bytes),
                restkey="__overflow__", restval=None, strict=True,
            )
            header = reader.fieldnames or []
            if (not header or
                any(not isinstance(h, str) or not h.strip() for h in header) or
                len({h.casefold().strip() for h in header}) != len(header)):
                raise ValueError("PBP_EMPTY_OR_DUPLICATE_CSV_HEADER")
            absent = REQUIRED.difference(header)
            if absent:
                raise ValueError("PBP_MISSING_EPA_REQUIRED_COLUMNS")
            count = 0
            for row in reader:
                count += 1
                if count > max_rows:
                    raise ValueError("PBP_RECORD_COUNT_EXCEEDS_CAP")
                if ("__overflow__" in row or
                        any(value is None for value in row.values())):
                    raise ValueError("PBP_RAGGED_CSV_ROW")
                if (not row["game_id"].strip() or
                    not row["week"].strip() or
                    not row["week"].isdigit()):
                    raise ValueError("PBP_MISSING_EVENT_OR_WEEK")
            if count == 0:
                raise ValueError("PBP_NO_CSV_RECORDS")
            return tuple(header), count
    except (EOFError, OSError, UnicodeError, csv.Error) as exc:
        # Never echo raw source bytes or original exception contents;
        # malformed upstream archives remain unaccepted.
        raise ValueError("PBP_GZIP_OR_CSV_DECODE_FAILED") from exc
