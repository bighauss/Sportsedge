"""Explicit research-only nflverse 2026 weekly stats live-release smoke test.

This intentionally consumes the CURRENT public GitHub asset, not a reconstructed
historic week-9 pregame snapshot. The release may have been revised after
week 9; it cannot establish period-accurate backtest availability.

Run manually or via the allowlisted GitHub Actions research workflow:
 python -m sportsedge.markets.nflverse_public_research_smoke /tmp/sportsedge-nflverse

Never writes raw player data into the public repository. No API keys, no
sportsbook connection, no wagering, no TD probability or official card.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys

from .nfl_td_shares import build_offensive_td_shares
from .public_release_capture import capture_public_release


def verify_weekly_public_archive(
    destination: str | Path,
    *,
    season: int = 2026,
    through_week: int = 9,
    require_all_32_teams: bool = True,
    opener=None,
) -> dict:
    args = {} if opener is None else {"opener": opener}
    archive = capture_public_release("NFL_WEEKLY_2026", destination, **args)
    root = Path(destination).resolve()
    digest = archive["original_bytes_sha256"]
    files = list(root.glob(f"NFL_WEEKLY_2026_{digest[7:23]}.csv.gz"))
    if len(files) != 1:
        raise ValueError("NFLVERSE_ARCHIVE_MISSING_OR_AMBIGUOUS")
    raw = files[0].read_bytes()
    if "sha256:"+sha256(raw).hexdigest() != digest:
        raise ValueError("NFLVERSE_ARCHIVE_CHANGED_AFTER_CAPTURE")
    provider_time = datetime.fromisoformat(
        archive["provider_updated_at_claim"].replace("Z", "+00:00")
    )
    retrieved = datetime.fromisoformat(archive["retrieved_at_utc"])
    shares = build_offensive_td_shares(
        raw, season=season, through_week=through_week,
        source_observed_at_utc=provider_time,
        fetched_at_utc=retrieved,
        expected_raw_sha256=digest,
        require_all_32_teams=require_all_32_teams,
    )
    if shares["source_record_count"] != archive["rows"]:
        raise ValueError("NFLVERSE_SOURCE_RECORD_CENSUS_CHANGED")
    if require_all_32_teams and shares["teams_observed"] != 32:
        raise ValueError("NFLVERSE_INCOMPLETE_TEAM_COVERAGE")
    if any(e["share_is_probability"] for e in shares["entries"]):
        raise ValueError("HISTORICAL_TD_SHARE_NOT_ALLOWED_AS_PROBABILITY")
    return {
        "status": "PUBLIC_SOURCE_HASH_AND_WEEKLY_SCHEMA_CHECKED_RESEARCH_ONLY",
        "season": season, "through_week": through_week,
        "source_asset": "NFL_WEEKLY_2026",
        "source_original_sha256": digest,
        "provider_release_updated_at_claim": archive["provider_updated_at_claim"],
        "retrieved_at_utc": archive["retrieved_at_utc"],
        "total_csv_rows": archive["rows"],
        "eligible_regular_season_rows": shares["eligible_weekly_rows"],
        "excluded_post_cutoff_rows": shares["excluded_future_weekly_rows"],
        "excluded_non_scoring_missing_player_id_rows": (
            shares["excluded_non_scoring_rows_without_player_id"]),
        "unattributed_offensive_scoring_tds": (
            shares["unattributed_offensive_scoring_tds"]),
        "teams_seen_before_cutoff": shares["teams_observed"],
        "player_scoring_share_rows": len(shares["entries"]),
        "provider_data_asof_authentication": False,
        "historical_week9_pregame_reconstruction_certified": False,
        "player_td_probabilities_calibrated": False,
        "source_is_bookmaker_quote": False,
        "official_counted": 0, "approved_stake_u": 0,
        "admission": "RESEARCH_ONLY_NOT_GATE_A_OR_B_COMPLETE",
    }


def main(args: list[str] | None = None) -> int:
    args = sys.argv[1:] if args is None else args
    if len(args) != 1:
        raise SystemExit("Usage: python -m sportsedge.markets.nflverse_public_research_smoke /tmp/private-archive")
    result = verify_weekly_public_archive(args[0])
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
