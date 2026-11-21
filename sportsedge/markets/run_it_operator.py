"""One offline RUN IT entry point for prepared slates and screenshot lines."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import stat
import sys

from .cli import MAX_MANIFEST_BYTES, _deny_nonfinite_json, _iso, _unique_json_keys
from .screenshot_line_handoff import run_line_capture
from .slate_orchestrator import run_slate


REPO = Path(__file__).resolve().parents[2]
SCHEMA = "sportsedge-run-it-operator-report-v1"
_INPUT_HINTS = {
    "RUN_IT_INVALID_ARGUMENTS": "RUN_WITH_HELP_FOR_EXPECTED_ARGUMENTS",
    "RUN_IT_PRIVATE_PATH_REQUIRED": "USE_OUT_OF_REPO_NON_SYMLINK_PATHS",
    "RUN_IT_DISTINCT_PATHS_REQUIRED": "USE_DISTINCT_INPUT_AND_REPORT_PATHS",
    "RUN_IT_REGULAR_INPUT_REQUIRED": "PROVIDE_EXISTING_REGULAR_JSON_FILES",
    "RUN_IT_INVALID_INPUT_SIZE": "PROVIDE_NONEMPTY_JSON_WITHIN_SIZE_LIMIT",
    "RUN_IT_INPUT_OBJECT_REQUIRED": "PROVIDE_A_JSON_OBJECT",
    "RUN_IT_MALFORMED_JSON": "PROVIDE_VALID_UTF8_JSON",
    "RUN_MANIFEST_DUPLICATE_JSON_KEY": "REMOVE_DUPLICATE_JSON_KEYS",
    "RUN_MANIFEST_NONFINITE_JSON_NUMBER": "USE_FINITE_JSON_NUMBERS",
    "RUN_IT_INVALID_REPLAY_CLOCK": "USE_AN_EXPLICIT_UTC_REPLAY_TIMESTAMP",
    "RUN_IT_FUTURE_REPLAY_CLOCK": "USE_A_REPLAY_TIMESTAMP_NOT_IN_THE_FUTURE",
    "RUN_IT_RELEASE_INVARIANT_FAILED": "STOP_AND_REVIEW_RESEARCH_RELEASE_INVARIANTS",
    "RUN_IT_SCREENSHOT_EVIDENCE_OVERLAY_UNSUPPORTED":
        "USE_UNPRICED_FROZEN_REFS_WITHOUT_QUOTE_BOUND_OVERLAYS",
    "RUN_IT_REPORT_ALREADY_EXISTS": "CHOOSE_A_NEW_PRIVATE_REPORT_FILENAME",
    "SCREENSHOT_PRICE_STALE_OVER_300_SECONDS": "CAPTURE_FRESH_PRICES_BEFORE_EVENT_START",
    "SCREENSHOT_OBSERVATION_CLOCK_INVALID": "CHECK_ORIGINAL_OBSERVATION_AND_RECEIPT_CLOCKS",
    "SCREENSHOT_BYTES_OR_SHA256_MISMATCH": "CHECK_ORIGINAL_IMAGE_BYTES_AND_DIGEST",
    "SCREENSHOT_CAPTURE_COUNT_INVALID": "PROVIDE_VALID_CAPTURE_RECORDS_OR_OMIT_SCREENSHOTS",
    "SCREENSHOT_NO_FROZEN_MODELS": "SUPPLY_PREEXISTING_UNPRICED_PROJECTION_REFS",
    "SCREENSHOT_NO_TRANSCRIBED_PRICE": "TRANSCRIBE_EXACT_AVAILABLE_PRICES",
    "SCREENSHOT_SPORT_UNSUPPORTED": "USE_SCREENSHOTS_FOR_CBB_CFB_NFL_ONLY",
    "PREGAME_FROZEN_SLATE_REQUIRED": "USE_A_FROZEN_CBB_CFB_NFL_SLATE_FOR_SCREENSHOTS",
    "PREGAME_INDEPENDENT_UNPRICED_PROJECTION_REQUIRED":
        "SUPPLY_PREEXISTING_UNPRICED_PROJECTION_REFS",
    "UNSUPPORTED_SLATE_SCHEMA": "USE_THE_DOCUMENTED_PREPARED_SLATE_SCHEMA",
}


def _check_no_release(report, *, card_key):
    if (any(type(report.get(field)) is not int or report[field] != 0
            for field in ("approved_stake_u", "official_counted"))
            or card_key not in report or report[card_key] is not None):
        raise ValueError("RUN_IT_RELEASE_INVARIANT_FAILED")


def run_operator(slate: dict, screenshots: dict | None = None,
                 *, now: datetime | None = None) -> dict:
    """Preserve the full research ledger; never construct an official card."""
    wall_clock = datetime.now(timezone.utc)
    clock = wall_clock if now is None else _iso(now.isoformat())
    if clock > wall_clock:
        raise ValueError("RUN_IT_FUTURE_REPLAY_CLOCK")
    if screenshots is None:
        lane = "PREPARED_SLATE"
        research = run_slate(slate, now=clock)
        views = [research]
    else:
        lane = "SCREENSHOT_TRANSCRIPTION"
        if slate.get("projection_evidence"):
            raise ValueError("RUN_IT_SCREENSHOT_EVIDENCE_OVERLAY_UNSUPPORTED")
        research = run_line_capture(slate, screenshots, now=clock)
        _check_no_release(research, card_key="wager_card")
        views = research["orientations"]
    for view in views:
        _check_no_release(view, card_key="card")
        if view.get("issue10_release_certified") is not False:
            raise ValueError("RUN_IT_RELEASE_INVARIANT_FAILED")
    # Screenshot orientations contain the same schedule, but different sides.
    expected = views[0]["counts"]["expected"]
    priced = sum(view["counts"]["priced_research"] for view in views)
    next_actions = []
    if not expected:
        next_actions.append("PROVIDE_EXPECTED_SCHEDULE")
    elif not priced:
        next_actions.append("CHECK_FROZEN_INPUTS_AND_SUBMITTED_EXACT_PRICES")
    if (any(view["counts"]["blocked_research"] or
            any(event["status"] == "BLOCK" for event in view["events"]) for view in views)
            or (screenshots is not None and research["blocked_offers"])):
        next_actions.append("REVIEW_EVENT_AND_OFFER_BLOCK_REASONS")
    return {
        "schema": SCHEMA,
        "input_lane": lane,
        "state": "PAPER_RESEARCH_AVAILABLE" if priced else "NEEDS_LINES_OR_REVIEW",
        "summary": {"scheduled_events": expected, "research_priced_sides": priced},
        "decision_at_utc": views[0]["generated_at_utc"],
        "decision_clock": "EXPLICIT_REPLAY" if now is not None else "SYSTEM_UTC",
        "next_actions": next_actions,
        "research": research,
        "final_bets": None,
        "release_blocker": "ISSUE10_RELEASE_GATES_NOT_CLEARED",
        "source_authenticated": False,
        "approved_stake_u": 0,
        "official_counted": 0,
    }


def _private_path(value: str) -> Path:
    lexical = Path(os.path.abspath(value))
    try:
        resolved = lexical.resolve()
    except RuntimeError:
        raise ValueError("RUN_IT_PRIVATE_PATH_REQUIRED") from None
    if (lexical.is_symlink() or
            any(p == REPO or REPO in p.parents for p in (lexical, resolved))):
        raise ValueError("RUN_IT_PRIVATE_PATH_REQUIRED")
    return resolved


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("RUN_MANIFEST_NONFINITE_JSON_NUMBER")
    return result


def _load(path: Path) -> tuple[dict, str]:
    if not path.is_file():
        raise ValueError("RUN_IT_REGULAR_INPUT_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise ValueError("RUN_IT_REGULAR_INPUT_REQUIRED")
        raw = f.read(MAX_MANIFEST_BYTES + 1)
    if not 0 < len(raw) <= MAX_MANIFEST_BYTES:
        raise ValueError("RUN_IT_INVALID_INPUT_SIZE")
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_keys,
                             parse_constant=_deny_nonfinite_json, parse_float=_finite_float)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("RUN_IT_MALFORMED_JSON") from None
    except ValueError as exc:
        code = str(exc).partition(":")[0]
        if code in ("RUN_MANIFEST_DUPLICATE_JSON_KEY", "RUN_MANIFEST_NONFINITE_JSON_NUMBER"):
            raise ValueError(code) from None
        raise
    if type(request) is not dict:
        raise ValueError("RUN_IT_INPUT_OBJECT_REQUIRED")
    return request, "sha256:" + sha256(raw).hexdigest()


def _blocked(reason: str) -> int:
    print(json.dumps({
        "state": "RUN_IT_REJECTED",
        "reason": reason,
        "next_action": _INPUT_HINTS.get(reason, "CHECK_PRIVATE_INPUTS_AND_REPORT_DIRECTORY"),
        "official_counted": 0,
        "approved_stake_u": 0,
    }, sort_keys=True), file=sys.stderr)
    return 2


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        # The default parser can echo arbitrary arguments (including paths).
        raise ValueError("RUN_IT_INVALID_ARGUMENTS")


def main(argv=None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("slate", help="private prepared or unpriced frozen slate JSON")
    parser.add_argument("report", help="new private report JSON (will not overwrite)")
    parser.add_argument("--screenshots", help="private screenshot transcription JSON")
    parser.add_argument("--replay-at", help="explicit UTC timestamp for offline PAPER replay")
    try:
        args = parser.parse_args(argv)
        source, dest = _private_path(args.slate), _private_path(args.report)
        screen = _private_path(args.screenshots) if args.screenshots else None
        if source == dest or screen in (source, dest):
            raise ValueError("RUN_IT_DISTINCT_PATHS_REQUIRED")
        if dest.exists():
            raise FileExistsError
        replay = None
        if args.replay_at is not None:
            try:
                replay = _iso(args.replay_at)
            except ValueError:
                raise ValueError("RUN_IT_INVALID_REPLAY_CLOCK") from None
        slate, slate_digest = _load(source)
        screens, screen_digest = _load(screen) if screen is not None else (None, None)
        report = run_operator(slate, screens, now=replay)
        report["input_sha256"] = {"slate": slate_digest}
        if screen_digest is not None:
            report["input_sha256"]["screenshots"] = screen_digest
        payload = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
                   + "\n").encode("utf-8")
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            dest.unlink(missing_ok=True)
            raise
    except FileExistsError:
        return _blocked("RUN_IT_REPORT_ALREADY_EXISTS")
    except ValueError as exc:
        # Only literal contract codes, never input-derived paths, labels or values.
        reason = str(exc)
        return _blocked(reason if reason in _INPUT_HINTS else "RUN_IT_INPUT_OR_REPORT_BLOCKED")
    except (KeyError, TypeError, OSError, RecursionError, ArithmeticError):
        # Full exception messages may contain input paths, identifiers, or data.
        return _blocked("RUN_IT_INPUT_OR_REPORT_BLOCKED")
    print(json.dumps({"state": report["state"], **report["summary"],
                      "decision_clock": report["decision_clock"],
                      "next_actions": report["next_actions"],
                      "official_counted": 0, "approved_stake_u": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
