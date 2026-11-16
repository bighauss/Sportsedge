"""One-command private prospective odds capture + CLV CSV conversion.

Run once for TAKE snapshot and separately in the last ten minutes pregame for
a CLOSE snapshot. No daemon, scheduler, paid history, secret logging, bookmaker
authentication, bet placement or official CLV. Never infer a real wager from a
TAKE-labeled board snapshot; this is an archival role only.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sportsedge.odds.free_odds_aggregator_intake import capture, SPORTS, utc
from sportsedge.odds.the_odds_api_clv_export import write_export, load_evidence
from sportsedge.odds.planned_capture_guard import guard_plan

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASES = frozenset({"TAKE", "CLOSE"})


def private_root(location: Path) -> Path:
    lexical = Path(os.path.abspath(os.fspath(location)))
    root = lexical.resolve()
    if any(p == REPO_ROOT or REPO_ROOT in p.parents for p in (lexical, root)):
        raise ValueError("PRIVATE_CAPTURE_PATH_IS_PUBLIC_CHECKOUT")
    return root


def capture_cycle(
    sport: str,
    private_dir: Path,
    event_id: str,
    phase: str,
    *,
    markets: tuple[str, ...] = ("h2h", "spreads", "totals"),
    bookmakers: tuple[str, ...] = ("draftkings", "fanduel"),
    key: str | None = None,
    opener=None,
    plan_path: Path | None = None,
):
    """Capture only a genuine provider event ID via documented v4 HTTP GET.

    Default opener=None is deliberate: it delegates to the upstream capture
    client's secure no-redirect opener. Never pass urllib.urlopen as a default:
    that silently bypasses protections against key-bearing query redirects.
    Original response JSON remains unchanged and hash-verified by converter.
    """
    root = private_root(private_dir)
    if phase not in PHASES:
        raise ValueError("PHASE_MUST_BE_TAKE_OR_CLOSE")
    if sport not in SPORTS:
        raise ValueError("UNSUPPORTED_SPORT")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("REAL_PROVIDER_EVENT_ID_REQUIRED")
    # A supplied quota plan must validate BEFORE a credit-consuming request.
    # No plan means legacy research capture, never claim plan approval.
    planned = (guard_plan(plan_path, sport=sport, event_id=event_id,
                          phase=phase, markets=markets, bookmakers=bookmakers)
               if plan_path is not None else None)
    info = capture(
        sport,
        root,
        key=key,
        event_id=event_id,
        markets=markets,
        bookmakers=bookmakers,
        opener=opener,
    )
    raw_name = info["raw_filename"]
    if raw_name != Path(raw_name).name or not raw_name.endswith(".json"):
        raise ValueError("UNSAFE_PROVIDER_ORIGINAL_FILENAME")
    stem = Path(raw_name).stem
    manifest = root / (stem + ".manifest.json")
    if not manifest.is_file() or not manifest.resolve().is_relative_to(root):
        raise ValueError("ORIGINAL_PROVIDER_MANIFEST_MISSING")
    # Retain original response even if the provider moved kickoff after plan.
    # Never label a changed event as an approved planned observation.
    if planned is not None:
        _, events, _, _ = load_evidence(manifest)
        if (len(events) != 1 or
            utc(events[0].get("commence_time")).isoformat() !=
                planned["expected_kickoff_utc"]):
            return {
                "schema": "sportsedge-prospective-clv-cycle-v1",
                "state": "BLOCK_PROVIDER_KICKOFF_CHANGED_FROM_APPROVED_PLAN",
                "sport":sport, "phase":phase,
                "event_id_provider_native":event_id,
                "original_json_filename":raw_name,
                "original_manifest_filename":manifest.name,
                "normalized_csv_filename":None,
                "normalized_audit_filename":None,
                "original_raw_sha256":info["original_raw_sha256"],
                "normalized_csv_sha256":None,
                "provider_credits_remaining":info["provider_remaining_credits"],
                "normalized_two_sided_selection_rows":0,
                "market_groups_quarantined_by_reason":{
                    "PROVIDER_KICKOFF_CHANGED_FROM_APPROVED_PLAN":1},
                "source_plan_sha256":planned["plan_sha256"],
                "capture_plan_guard":"BLOCK_KICKOFF_CHANGED",
                "official_counted":0,"approved_stake_u":0,
            }
    # CLOSE is a near-kickoff *capture*, not just an arbitrarily labeled file.
    # Keep the original response and hash manifest for evidence even when a
    # premature/late collection fails the CLOSE window. Do not emit a CLOSE CSV
    # (nor silently relabel it as TAKE) outside 0 < seconds_to_start <= 600.
    if phase == "CLOSE":
        _, events, captured, _ = load_evidence(manifest)
        if len(events) != 1:
            raise ValueError("CLOSE_REQUIRES_SINGLE_PROVIDER_EVENT")
        kickoff = utc(events[0].get("commence_time"))
        seconds_to_start = (kickoff - captured).total_seconds()
        if not 0 < seconds_to_start <= 600:
            return {
                "schema": "sportsedge-prospective-clv-cycle-v1",
                "state": "BLOCK_CLOSE_CAPTURE_OUTSIDE_T_MINUS_10M",
                "sport": sport,
                "phase": phase,
                "event_id_provider_native": event_id,
                "original_json_filename": raw_name,
                "original_manifest_filename": manifest.name,
                "normalized_csv_filename": None,
                "normalized_audit_filename": None,
                "original_raw_sha256": info["original_raw_sha256"],
                "normalized_csv_sha256": None,
                "provider_credits_remaining": info["provider_remaining_credits"],
                "raw_provider_outcomes_returned": info["outcomes_returned"],
                "normalized_two_sided_selection_rows": 0,
                "market_groups_quarantined_by_reason": {
                    "CLOSE_CAPTURE_OUTSIDE_T_MINUS_10M": 1,
                },
                "original_books_independently_authenticated": False,
                "provider_quote_clock_externally_attested": False,
                "official_counted": 0,
                "approved_stake_u": 0,
                "source_plan_sha256": planned["plan_sha256"] if planned else None,
                "capture_plan_guard": "PLAN_PREHTTP_PASSED" if planned else "NOT_PLAN_BOUND",
            }
    normalized_file = root / (stem + "." + phase.lower() + ".csv")
    exported = write_export(manifest, normalized_file, "TAKE" if phase == "TAKE" else "HISTORY")
    return {
        "schema": "sportsedge-prospective-clv-cycle-v1",
        "state": (
            "PAPER_0U_PROSPECTIVE_CAPTURE_NOT_ORIGINAL_BOOK_AUTHENTICATED"
            if exported["rows_generated"]
            else "BLOCK_NO_VALID_FRESH_TWO_SIDED_QUOTES"
        ),
        "sport": sport,
        "phase": phase,
        "event_id_provider_native": event_id,
        "original_json_filename": raw_name,
        "original_manifest_filename": manifest.name,
        "normalized_csv_filename": normalized_file.name,
        "normalized_audit_filename": normalized_file.name + ".audit.json",
        "original_raw_sha256": info["original_raw_sha256"],
        "normalized_csv_sha256": exported["normalized_csv_sha256"],
        "provider_credits_remaining": info["provider_remaining_credits"],
        "raw_provider_outcomes_returned": info["outcomes_returned"],
        "normalized_two_sided_selection_rows": exported["rows_generated"],
        "market_groups_quarantined_by_reason": exported["market_groups_quarantined_by_reason"],
        "original_books_independently_authenticated": False,
        "provider_quote_clock_externally_attested": False,
        "official_counted": 0,
        "approved_stake_u": 0,
        "source_plan_sha256": planned["plan_sha256"] if planned else None,
        "capture_plan_guard": "PLAN_PREHTTP_PASSED" if planned else "NOT_PLAN_BOUND",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sport", choices=sorted(SPORTS))
    parser.add_argument("private_dir", type=Path)
    parser.add_argument("--event-id", required=True, help="A real ID from the authorized upstream provider")
    parser.add_argument("--phase", choices=sorted(PHASES), required=True)
    parser.add_argument("--plan", type=Path,
                        help="Optional private quota plan: validate before provider request")
    parser.add_argument("--markets", nargs="+", default=["h2h", "spreads", "totals"])
    parser.add_argument("--bookmakers", nargs="+", default=["draftkings", "fanduel"])
    args = parser.parse_args(argv)
    # API key remains in SPORTSEDGE_ODDS_API_KEY, not argv or any returned file.
    result = capture_cycle(
        args.sport, args.private_dir, args.event_id, args.phase,
        markets=tuple(args.markets), bookmakers=tuple(args.bookmakers),
        plan_path=args.plan,
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
