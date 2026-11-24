"""Resolve a reviewed, main-branch CBB paper run request without provider access."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

REQUEST = Path("models/cbb/run_requests/current.json")
FIELDS = {"schema", "date_ct", "board_path", "board_blob_sha", "board_captured_utc",
          "season", "totals_order_verified", "label"}

def resolve_request(root, request, now):
    if not isinstance(request, dict) or set(request) != FIELDS:
        raise ValueError("REQUEST_SCHEMA")
    if request["schema"] != "cbb-paper-run-request-v1" or request["label"] != "PAPER_0U":
        raise ValueError("REQUEST_POLICY")
    if now.tzinfo is None:
        raise ValueError("REQUEST_CLOCK")
    day = now.astimezone(ZoneInfo("America/Chicago")).date()
    if request["date_ct"] != day.isoformat():
        raise ValueError("REQUEST_STALE_DATE")
    p = request["board_path"]
    if not isinstance(p, str) or not re.fullmatch(
            r"models/cbb/lines/board_" + re.escape(day.isoformat()) + r"_[A-Za-z0-9_-]+\.csv", p):
        raise ValueError("REQUEST_BOARD_PATH")
    root = Path(root).resolve()
    board = root / p
    if not board.is_file() or not board.resolve().is_relative_to(root) or board.is_symlink():
        raise ValueError("REQUEST_BOARD_MISSING")
    raw = board.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if request["board_blob_sha"] != blob:
        raise ValueError("REQUEST_BOARD_HASH")
    stamp = request["board_captured_utc"]
    if not isinstance(stamp, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", stamp):
        raise ValueError("REQUEST_CAPTURE_TIME")
    capture = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if not timedelta(0) <= now - capture < timedelta(hours=24):
        raise ValueError("REQUEST_CAPTURE_TIME")
    season = day.year + int(day.month >= 7)
    if type(request["season"]) is not int or request["season"] != season:
        raise ValueError("REQUEST_SEASON")
    if type(request["totals_order_verified"]) is not bool:
        raise ValueError("REQUEST_TOTALS_FORMAT")
    return {"board": p, "board_at": stamp, "season": str(season),
            "season_start": f"{season-1}-11-01T00:00:00Z",
            "totals_verified": str(request["totals_order_verified"]).lower()}

def main():
    if os.environ.get("GITHUB_EVENT_NAME") == "push":
        if os.environ.get("GITHUB_REF") != "refs/heads/main":
            raise SystemExit("REQUEST_NOT_MAIN")
        # Duplicate JSON keys are ambiguous, even in a reviewed file.
        def pairs(values):
            out = {}
            for k, v in values:
                if k in out:
                    raise ValueError("REQUEST_DUPLICATE_KEY")
                out[k] = v
            return out
        try:
            request = json.loads(REQUEST.read_text(), object_pairs_hook=pairs)
            values = resolve_request(Path.cwd(), request, datetime.now(timezone.utc))
        except (ValueError, OSError, TypeError):
            raise SystemExit("BLOCK_RUN_REQUEST") from None
    elif os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        values = {k: os.environ.get("MANUAL_" + k.upper(), "") for k in
                  ("board", "board_at", "season", "season_start", "totals_verified")}
    else:
        raise SystemExit("REQUEST_EVENT_UNSUPPORTED")
    if any("\n" in v or "\r" in v for v in values.values()):
        raise SystemExit("REQUEST_OUTPUT_INVALID")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        for k, v in values.items():
            out.write(f"{k}={v}\n")

if __name__ == "__main__":
    main()
