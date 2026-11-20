"""Join *user-transcribed* screenshot lines to PRE-FROZEN SportsEdge research.

This is the last manual odds handoff, not an OCR engine or authenticated
sportsbook-original API. It never creates team/player features, missing lines,
provider-native IDs, production release, official wagers, or stakes.

Each exact opposite-side price pair is evaluated in two independent slate
passes so no provider quote is disguised as a second independent observation
or duplicated within a single slate's quote-ID census. Everything stays 0u.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import stat

from .allmarkets_research import Market, _american
from .slate_orchestrator import SCHEMA as SLATE_SCHEMA, run_slate
from .cli import _iso, _unique_json_keys, _deny_nonfinite_json

SCHEMA = "sportsedge-screenshot-lines-v1"
SPORTS = frozenset(("NFL", "CFB", "CBB"))
SOURCE_SURFACES = frozenset(("DK_APP_SCREENSHOT", "BESTBOOK_DK_DISPLAY_SCREENSHOT"))
MARKET_FIELDS = frozenset((
    "sport", "event_id", "kind", "period", "selection",
    "line", "team_id", "player_id", "stat", "settlement",
))
CAPTURE_FIELDS = frozenset((
    "image_path", "image_sha256", "observed_at_utc",
    "received_at_utc", "source_surface", "offers",
))
OFFER_FIELDS = frozenset(("market", "odds_american"))
MAX_IMAGE = 15_000_000
MAX_CAPTURES = 100
MAX_OFFERS = 5000
REPO = Path(__file__).resolve().parents[2]


def _private_image(path: str, digest: str) -> bytes:
    if type(path) is not str or not path:
        raise ValueError("SCREENSHOT_ORIGINAL_FILE_REQUIRED")
    lexical = Path(os.path.abspath(path))
    resolved = lexical.resolve()
    if (lexical == REPO or REPO in lexical.parents or
        resolved == REPO or REPO in resolved.parents or
        lexical.is_symlink() or not lexical.is_file()):
        raise ValueError("SCREENSHOT_PRIVATE_UNMODIFIED_IMAGE_REQUIRED")
    status = lexical.stat()
    if not stat.S_ISREG(status.st_mode) or not 0 < status.st_size <= MAX_IMAGE:
        raise ValueError("SCREENSHOT_ORIGINAL_INVALID_SIZE_OR_TYPE")
    raw = lexical.read_bytes()
    valid = (
        raw.startswith(b"\x89PNG\r\n\x1a\n") or
        raw.startswith(b"\xff\xd8\xff") or
        (raw.startswith(b"RIFF") and raw[8:12] == b"WEBP") or
        raw.startswith(b"%PDF-")
    )
    if not valid or "sha256:" + sha256(raw).hexdigest() != digest:
        raise ValueError("SCREENSHOT_BYTES_OR_SHA256_MISMATCH")
    return raw


def _strict_keys(obj, keys, label):
    if type(obj) is not dict or set(obj) != keys:
        raise ValueError("SCREENSHOT_INVALID_FIELDS:" + label)
    return obj


def _side_market(raw):
    _strict_keys(raw, MARKET_FIELDS, "market")
    if raw["sport"] not in SPORTS:
        raise ValueError("SCREENSHOT_SPORT_UNSUPPORTED")
    return Market(**raw)


def _quote(market: Market, price: int, capture: dict,
           image_digest: str, offer_number: int) -> dict:
    # Explicit LOCAL transcription IDs, NEVER an invented provider-native ID.
    identity = json.dumps({
        "market": market.identity(), "screenshot": image_digest,
        "offer_index": offer_number,
    }, sort_keys=True, separators=(",", ":")).encode()
    d = sha256(identity).hexdigest()
    period_group = sha256(json.dumps([
        market.sport, market.event_id, market.kind, market.period,
        market.team_id, market.player_id, market.stat,
        market.settlement, abs(float(market.line)) if market.kind == "SPREAD" else market.line,
    ], separators=(",", ":")).encode()).hexdigest()
    local_id = "LOCAL_SCREEN_" + d[:30]
    return {
        "market": dict(zip(MARKET_FIELDS_ORDER, market.identity())),
        "odds_american": price,
        "book": "DraftKings",
        "provider_id": "MANUAL_SCREENSHOT_UNVERIFIED",
        "provider_event_id": "LOCAL_EVENT_" + sha256(market.event_id.encode()).hexdigest()[:20],
        "provider_market_id": "LOCAL_GROUP_" + period_group[:30],
        "quote_id": local_id,
        "receipt_id": local_id,
        "raw_payload_sha256": image_digest,
        "observed_at_utc": capture["observed_at_utc"],
        "received_at_utc": capture["received_at_utc"],
        "event_start_utc": capture["start_utc"],
    }


MARKET_FIELDS_ORDER = (
    "sport", "event_id", "kind", "period", "selection",
    "line", "team_id", "player_id", "stat", "settlement",
)


def _fresh_capture(capture: dict, now: datetime) -> tuple[datetime, datetime]:
    obs = _iso(capture["observed_at_utc"])
    received = _iso(capture["received_at_utc"])
    if not obs <= received <= now:
        raise ValueError("SCREENSHOT_OBSERVATION_CLOCK_INVALID")
    if now - obs > timedelta(seconds=300):
        raise ValueError("SCREENSHOT_PRICE_STALE_OVER_300_SECONDS")
    return obs, received


def prepare_line_capture(frozen_slate: dict, screenshots: dict,
                         *, now: datetime | None = None) -> dict:
    """Prepare two real-independent-model research runs, one per bet side.

    Never backfill prices or alter the frozen team's feature file/manifest.
    A pre-existing real-PIT projection_ref must be supplied separately.
    Any unsupported screenshot market remains visible in blocked_offers.
    """
    clock = datetime.now(timezone.utc) if now is None else now
    clock = _iso(clock.isoformat())
    _strict_keys(screenshots, frozenset(("schema", "captures")), "root")
    if screenshots["schema"] != SCHEMA:
        raise ValueError("SCREENSHOT_SCHEMA_UNSUPPORTED")
    captures = screenshots["captures"]
    if type(captures) is not list or not 0 < len(captures) <= MAX_CAPTURES:
        raise ValueError("SCREENSHOT_CAPTURE_COUNT_INVALID")
    if (type(frozen_slate) is not dict or
        frozen_slate.get("schema") != SLATE_SCHEMA or
        set(frozen_slate.get("sports", [])) - SPORTS):
        raise ValueError("PREGAME_FROZEN_SLATE_REQUIRED")
    # All scheduled events remain present even if the screenshot has no offers.
    registry = {}
    for row in frozen_slate.get("expected_events", []):
        key = (row["sport"], row["event_id"])
        if key in registry:
            raise ValueError("SCREENSHOT_DUPLICATE_SCHEDULE_EVENT")
        registry[key] = _iso(row["start_utc"])
    originals = {}
    for row in frozen_slate.get("event_inputs", []):
        key = (row["sport"], row["event_id"])
        if key not in registry or key in originals:
            raise ValueError("SCREENSHOT_FROZEN_EVENT_MISMATCH")
        m = row["manifest"]
        if "projection_ref" not in m or "projection" in m or m.get("markets") != []:
            raise ValueError("PREGAME_INDEPENDENT_UNPRICED_PROJECTION_REQUIRED")
        if _iso(m["projection_ref"]["asof_utc"]) >= registry[key]:
            raise ValueError("PREGAME_MODEL_FREEZE_NOT_BEFORE_START")
        originals[key] = m
    if not registry:
        raise ValueError("SCREENSHOT_NO_PREDECLARED_SCHEDULE")
    if not originals:
        raise ValueError("SCREENSHOT_NO_FROZEN_MODELS")
    observations = []
    preblocked = []
    used_image = set()
    total = 0
    for cap_index, capture in enumerate(captures):
        _strict_keys(capture, CAPTURE_FIELDS, "capture")
        if capture["source_surface"] not in SOURCE_SURFACES:
            raise ValueError("SCREENSHOT_SOURCE_SURFACE_UNRECOGNIZED")
        image_digest = capture["image_sha256"]
        if image_digest in used_image:
            raise ValueError("SCREENSHOT_SAME_IMAGE_REUSED_AS_NEW_CAPTURE")
        used_image.add(image_digest)
        _private_image(capture["image_path"], image_digest)
        obs, received = _fresh_capture(capture, clock)
        entries = capture["offers"]
        if type(entries) is not list or not entries:
            raise ValueError("SCREENSHOT_NO_TRANSCRIBED_PRICE")
        total += len(entries)
        if total > MAX_OFFERS:
            raise ValueError("SCREENSHOT_TOO_MANY_OFFERS")
        for offer_index, raw_offer in enumerate(entries):
            _strict_keys(raw_offer, OFFER_FIELDS, "offer")
            if (type(raw_offer["market"]) is dict and
                set(raw_offer["market"]) == MARKET_FIELDS and
                raw_offer["market"]["sport"] in SPORTS and
                raw_offer["market"]["kind"] == "SGP"):
                preblocked.append({
                    "market": [raw_offer["market"][k] for k in MARKET_FIELDS_ORDER],
                    "reason": "SCREENSHOT_SGP_NOT_SUPPORTED_NO_JOINT_MODEL",
                    "source_authenticated": False, "approved_stake_u": 0,
                })
                continue
            market = _side_market(raw_offer["market"])
            if type(raw_offer["odds_american"]) is not int:
                raise ValueError("SCREENSHOT_AMERICAN_PRICE_INTEGER_REQUIRED")
            price = _american(raw_offer["odds_american"])
            key = (market.sport, market.event_id)
            if key not in registry:
                raise ValueError("SCREENSHOT_EVENT_NOT_IN_FROZEN_SLATE")
            if obs >= registry[key] or received >= registry[key]:
                raise ValueError("SCREENSHOT_AFTER_GAME_START")
            model = originals.get(key)
            if model is None:
                # Absent independent model cannot be substituted with odds.
                observations.append({
                    "market": market, "key": key,
                    "blocked": "NO_FROZEN_INDEPENDENT_EVENT_MODEL",
                })
                continue
            if _iso(model["projection_ref"]["asof_utc"]) > obs:
                observations.append({
                    "market": market, "key": key,
                    "blocked": "MODEL_NOT_FROZEN_BEFORE_SCREENSHOT",
                })
                continue
            observation = {
                "market": market, "key": key, "price": price,
                "capture": {**capture, "start_utc": registry[key].isoformat()},
                "sha": image_digest, "index": cap_index * (MAX_OFFERS+1) + offer_index,
            }
            observations.append(observation)
    seen = {}
    for entry in observations:
        identity = entry["market"].identity()
        seen.setdefault(identity, []).append(entry)
    blocked = list(preblocked)
    valid = []
    for entry in observations:
        matches = seen[entry["market"].identity()]
        if "blocked" in entry:
            reason = entry["blocked"]
        elif len(matches) != 1:
            reason = "DUPLICATE_SCREENSHOT_OFFER_IDENTITY"
        else:
            opp = [x for x in observations if (
                x is not entry and "blocked" not in x and
                entry["sha"] == x["sha"] and
                entry["market"].opposite(x["market"]))]
            reason = (None if len(opp) == 1 and len(seen[opp[0]["market"].identity()]) == 1
                      else "MISSING_OR_AMBIGUOUS_OPPOSITE_PRICE")
        if reason:
            blocked.append({
                "market": list(entry["market"].identity()), "reason": reason,
                "source_authenticated": False, "approved_stake_u": 0,
            })
        else:
            valid.append(entry)
    pairs = {}
    for e in valid:
        matches = [x for x in valid if (x is not e and
                    e["sha"] == x["sha"] and
                    e["market"].opposite(x["market"]))]
        if len(matches) != 1:
            raise ValueError("SCREENSHOT_PAIR_CENSUS_NOT_BIJECTIVE")
        other = matches[0]
        pair_identity = tuple(sorted((e["market"].identity(), other["market"].identity())))
        pairs[pair_identity] = tuple(sorted((e, other), key=lambda r: r["market"].identity()))
    # One immutable source quote per side is used only ONCE in each run.
    # The opposite side is evaluated in a *separate* research run, not
    # masqueraded as a second original quote within the same slate census.
    variants = []
    for orientation in (0, 1):
        slate = deepcopy(frozen_slate)
        for event in slate["event_inputs"]:
            event["manifest"]["markets"] = []
        mapped = {(r["sport"], r["event_id"]): r["manifest"]
                  for r in slate["event_inputs"]}
        for entry_a, entry_b in pairs.values():
            primary = (entry_a, entry_b)[orientation]
            opposite = (entry_b, entry_a)[orientation]
            market = primary["market"]
            key = primary["key"]
            quote1 = _quote(market, primary["price"], primary["capture"],
                            primary["sha"], primary["index"])
            quote2 = _quote(opposite["market"], opposite["price"],
                            opposite["capture"], opposite["sha"], opposite["index"])
            mapped[key]["markets"].append({
                "market": dict(zip(MARKET_FIELDS_ORDER, market.identity())),
                "dk_quote": quote1, "dk_opposite_quote": quote2,
            })
        variants.append(slate)
    return {
        "schema": "sportsedge-screenshot-line-preflight-v1",
        "captured_offers": len(observations),
        "paired_markets": len(pairs),
        "blocked_offers": blocked,
        "capture_sha256": sorted(used_image),
        "source_authenticated": False,
        "approved_stake_u": 0, "official_counted": 0,
        "review_runs": tuple(variants),
    }


def run_line_capture(frozen_slate: dict, screenshots: dict,
                     *, now: datetime | None = None) -> dict:
    clock = datetime.now(timezone.utc) if now is None else now
    prep = prepare_line_capture(frozen_slate, screenshots, now=clock)
    first, second = prep["review_runs"]
    # Never alter an upstream frozen model, only the two price views.
    outputs = (run_slate(first, now=clock), run_slate(second, now=clock))
    if any(out["approved_stake_u"] != 0 or out["official_counted"] != 0
           for out in outputs):
        raise ValueError("SCREENSHOT_RESEARCH_RELEASE_BYPASS")
    return {
        "schema": "sportsedge-screenshot-pricing-report-v1",
        "source_authenticated": False,
        "model_source_independently_authenticated": False,
        "status": "PAPER_0U_OR_BLOCKED_ONLY",
        "captured_offers": prep["captured_offers"],
        "paired_markets": prep["paired_markets"],
        "blocked_offers": prep["blocked_offers"],
        "capture_sha256": prep["capture_sha256"],
        "orientations": list(outputs),
        "official_counted": 0, "approved_stake_u": 0,
        "wager_card": None,
        "next_requirements": [
            "PREGAME_ORIGINAL_BOOK_AUTHENTICATION",
            "AUTHENTICATED_INDEPENDENT_PLAYER_AND_TEAM_DATA",
            "FORWARD_VALIDATED_MARKET_DISTRIBUTIONS",
            "ISSUE10_RELEASE_GATES_A_TO_E",
        ],
    }


def _read_json(path):
    raw = Path(path).read_bytes()
    if not raw or len(raw) > 20_000_000:
        raise ValueError("SCREENSHOT_INPUT_JSON_SIZE_INVALID")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_keys,
                      parse_constant=_deny_nonfinite_json)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="PAPER-only line screenshot handoff")
    parser.add_argument("frozen_slate_json")
    parser.add_argument("transcribed_screenshots_json")
    parser.add_argument("new_report_json")
    p = parser.parse_args(argv)
    locations = [Path(a).resolve() for a in
                 (p.frozen_slate_json, p.transcribed_screenshots_json,
                  p.new_report_json)]
    if len(set(locations)) != 3 or any(
        x == REPO or REPO in x.parents for x in locations):
        raise ValueError("SCREENSHOT_PRIVATE_DISTINCT_PATHS_REQUIRED")
    report = run_line_capture(_read_json(locations[0]), _read_json(locations[1]))
    raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode()+b"\n"
    with locations[2].open("xb") as file:
        file.write(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
