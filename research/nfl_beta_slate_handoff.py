"""Full-slate research handoff. Never manufactures forecasts or releases bets."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _decode(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 64000000:
        raise ValueError("INVALID_EVIDENCE_BYTES")
    def reject(_):
        raise ValueError("NONFINITE_JSON")
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=reject)


def _ingest(quotes, model, decision):
    from nfl_beta_evidence_intake import ingest
    return ingest(quotes, model, decision_utc=decision)


def run_slate(expected_events, packages, *, decision_utc):
    """Keep every expected game and quote, including missing-model failures.

    IDs and timestamps are declarations, not independently authenticated facts.
    Input packages contain event_id, quote_bytes, and optional model_bytes.
    """
    decision = datetime.fromisoformat(decision_utc.replace("Z", "+00:00"))
    if decision.tzinfo is None or decision.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    if not isinstance(expected_events, list) or not expected_events or any(type(x) is not str or not x.strip() for x in expected_events):
        raise ValueError("EXPECTED_EVENT_IDS_REQUIRED")
    if len(set(expected_events)) != len(expected_events) or not isinstance(packages, list):
        raise ValueError("INVALID_SLATE")
    indexed = {}
    for package in packages:
        if not isinstance(package, dict) or set(package) - {"event_id", "quote_bytes", "model_bytes"}:
            raise ValueError("INVALID_PACKAGE")
        event = package.get("event_id")
        if type(event) is not str or event not in expected_events or event in indexed:
            raise ValueError("DUPLICATE_OR_UNEXPECTED_EVENT")
        indexed[event] = package
    games = []
    for event in expected_events:
        game = dict(event_id=event, status="PAPER_HOLD_0U", stake_u=0,
                    model_confidence=None, reasons=[], rows=[], attempted_quotes=None)
        games.append(game)
        package = indexed.get(event)
        if package is None or package.get("quote_bytes") is None:
            game["reasons"].append("NO_PRICE_PACKAGE")
            continue
        try:
            quotes = _decode(package["quote_bytes"])
            if not isinstance(quotes, dict) or set(quotes) != {"source", "captured_at_utc", "offers"} or quotes["source"] != "DraftKings" or not isinstance(quotes["offers"], list):
                raise ValueError("INVALID_QUOTE_ENVELOPE")
            seen = set()
            for offer in quotes["offers"]:
                if not isinstance(offer, dict) or offer.get("event_id") != event:
                    raise ValueError("QUOTE_EVENT_MISMATCH")
                key = offer.get("quote_id")
                if type(key) is not str or not key or key in seen:
                    raise ValueError("DUPLICATE_OR_MISSING_QUOTE_ID")
                seen.add(key)
                game["rows"].append(dict(offer=offer, status="PAPER_HOLD_0U", stake_u=0, beta_probability=None, beta_ev=None, reasons=["NOT_EVALUATED"]))
            game["attempted_quotes"] = len(quotes["offers"])
            game["quote_sha256"] = "sha256:" + hashlib.sha256(package["quote_bytes"]).hexdigest()
            if not quotes["offers"]:
                game["reasons"].append("NO_OFFERS")
                continue
            if package.get("model_bytes") is None:
                game["reasons"].append("NO_MODEL_PACKAGE")
                continue
            model = _decode(package["model_bytes"])
            if not isinstance(model, dict) or model.get("event_id") != event:
                raise ValueError("MODEL_EVENT_MISMATCH")
            result = _ingest(package["quote_bytes"], package["model_bytes"], decision_utc)
            priced = result.get("rows") if isinstance(result, dict) else None
            if not isinstance(priced, list) or len(priced) != len(game["rows"]):
                raise ValueError("PRICER_DENOMINATOR_MISMATCH")
            for offer, row in zip(quotes["offers"], priced):
                if not isinstance(row, dict) or row.get("offer_id") != offer["quote_id"] or row.get("event_id") != event or row.get("status") != "PAPER_HOLD_0U" or type(row.get("stake_u")) is not int or row["stake_u"] != 0:
                    raise ValueError("PRICER_IDENTITY_OR_PAPER_VIOLATION")
            game["rows"] = priced
            game["reasons"].append("RESEARCH_ESTIMATES_UNCALIBRATED")
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, UnicodeError):
            game["reasons"].append("INVALID_EVIDENCE_OR_PRICER_RESULT")
    return dict(status="RESEARCH_PAPER_0U", games=games, expected_games=len(expected_events),
                submitted_games=len(indexed), official_bets=0, approved_stake_u=0,
                source_authentication="UNVERIFIED", calibration="UNVALIDATED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = _decode(args.manifest.read_bytes())
    if not isinstance(manifest, dict) or set(manifest) != {"expected_events", "packages", "decision_utc"}:
        raise ValueError("INVALID_MANIFEST")
    packages = []
    for item in manifest["packages"]:
        if not isinstance(item, dict) or set(item) - {"event_id", "quotes_path", "model_path"}:
            raise ValueError("INVALID_PACKAGE_PATHS")
        package = {"event_id": item["event_id"]}
        for role in ("quotes", "model"):
            path = item.get(role + "_path")
            if path is not None:
                try:
                    package["quote_bytes" if role == "quotes" else "model_bytes"] = (args.manifest.parent / path).read_bytes()
                except FileNotFoundError:
                    pass
        packages.append(package)
    result = run_slate(manifest["expected_events"], packages, decision_utc=manifest["decision_utc"])
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")


if __name__ == "__main__":
    main()
