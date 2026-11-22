"""NFL beta pregame evidence intake, fail closed.

Use externally captured quote bytes and a separately timestamped model scenario
file. SHA hashes prove byte integrity only, NOT publisher authentication.
This tool never promotes a bet or infers unavailable touchdown order.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from nfl_beta_last_four import price_beta


def _utc(s):
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None or d.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    return d.astimezone(timezone.utc)


def ingest(quote_bytes, model_bytes, *, decision_utc):
    quotes = json.loads(quote_bytes)
    model = json.loads(model_bytes)
    if not isinstance(quotes, dict) or set(quotes) != {"offers", "captured_at_utc", "source"}:
        raise ValueError("QUOTE_ENVELOPE_INVALID")
    if quotes["source"] != "DraftKings":
        raise ValueError("NOT_DRAFTKINGS")
    if not isinstance(model, dict) or set(model) != {"scenarios", "model_asof_utc", "event_id"}:
        raise ValueError("MODEL_ENVELOPE_INVALID")
    if not isinstance(quotes["offers"], list) or not isinstance(model["scenarios"], list):
        raise ValueError("INVALID_ROWS")
    capture = _utc(quotes["captured_at_utc"])
    asof = _utc(model["model_asof_utc"])
    decision = _utc(decision_utc)
    if not asof <= capture <= decision:
        raise ValueError("LOOKAHEAD_OR_FUTURE_CAPTURE")
    if (decision - capture).total_seconds() > 300:
        raise ValueError("STALE_CAPTURE")
    quote_sha = "sha256:" + hashlib.sha256(quote_bytes).hexdigest()
    model_sha = "sha256:" + hashlib.sha256(model_bytes).hexdigest()
    offers = []
    for item in quotes["offers"]:
        if not isinstance(item, dict):
            raise ValueError("INVALID_QUOTE")
        if item.get("event_id") != model["event_id"]:
            raise ValueError("EVENT_MISMATCH")
        # The envelope, not user-supplied offer metadata, establishes hashes/time.
        if any(k in item for k in ("captured_at_utc", "model_asof_utc",
                                  "source_sha256", "model_sha256", "book")):
            raise ValueError("CONFLICTING_OFFER_PROVENANCE")
        offers.append(dict(item, captured_at_utc=quotes["captured_at_utc"],
                           model_asof_utc=model["model_asof_utc"],
                           source_sha256=quote_sha, model_sha256=model_sha,
                           book="DraftKings"))
    result = price_beta(model["scenarios"], offers, decision_utc=decision_utc)
    result["quote_sha256"] = quote_sha
    result["model_sha256"] = model_sha
    result["external_authentication"] = "UNVERIFIED"
    result["calibration"] = "UNVALIDATED"
    return result


def main():
    p = argparse.ArgumentParser(description="Offline PIT NFL beta evidence intake")
    p.add_argument("--quotes", required=True, type=Path)
    p.add_argument("--model", required=True, type=Path)
    p.add_argument("--decision-utc", required=True)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    result = ingest(a.quotes.read_bytes(), a.model.read_bytes(),
                    decision_utc=a.decision_utc)
    output = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if a.output:
        a.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
