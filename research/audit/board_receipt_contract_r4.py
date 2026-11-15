"""Research-only receipt contract; never authenticates an external sportsbook quote."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = {"sport", "event_id", "event_start_utc", "captured_utc", "book",
            "market", "period", "side", "price_american", "provider_quote_id",
            "receipt_sha256", "source_url"}

def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)

def validate(path):
    raw = Path(path).read_bytes()
    result = {"status": "BLOCK", "approved_stake_u": 0,
              "input_sha256": hashlib.sha256(raw).hexdigest(), "errors": []}
    try:
        reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("invalid or duplicate header")
        if not REQUIRED.issubset(reader.fieldnames):
            raise ValueError("missing required columns")
        rows = list(reader)
    except (ValueError, UnicodeError, csv.Error) as exc:
        result["errors"].append({"row": 1, "reason": "INVALID_CSV", "detail": str(exc)})
        return result
    if not rows:
        result["errors"].append({"row": 1, "reason": "EMPTY_BOARD"})
    seen = set()
    quote_ids = set()
    starts = {}
    for number, row in enumerate(rows, 2):
        errors = []
        if None in row or any(v is None for v in row.values()):
            errors.append("MALFORMED_CSV")
        def get(key):
            return (row.get(key) or "").strip()
        for key in REQUIRED:
            if not get(key):
                errors.append("MISSING_" + key.upper())
        try:
            captured, start = timestamp(get("captured_utc")), timestamp(get("event_start_utc"))
            if captured >= start:
                errors.append("POST_START_CAPTURE")
            event = (get("sport").upper(), get("event_id"))
            if event in starts and starts[event] != start:
                errors.append("CONFLICTING_EVENT_START")
            starts.setdefault(event, start)
        except ValueError:
            errors.append("INVALID_TIMESTAMP")
        quote_key = (get("book").casefold(), get("provider_quote_id"))
        if quote_key in quote_ids:
            errors.append("REUSED_PROVIDER_QUOTE_ID")
        quote_ids.add(quote_key)
        key = (get("sport").upper(), get("event_id"), get("book").casefold(),
               get("market").casefold(), get("period").casefold(), get("side").casefold(),
               get("line"), get("captured_utc"))
        if key in seen:
            errors.append("DUPLICATE_SELECTION_SNAPSHOT")
        seen.add(key)
        price = get("price_american")
        if not (len(price) >= 4 and price[0] in "+-" and price[1:].isdigit()
                and int(price[1:]) >= 100):
            errors.append("INVALID_AMERICAN_PRICE")
        if len(get("receipt_sha256")) != 64 or any(c not in "0123456789abcdefABCDEF" for c in get("receipt_sha256")):
            errors.append("INVALID_RECEIPT_HASH")
        if not get("source_url").startswith("https://"):
            errors.append("INVALID_SOURCE_URL")
        if errors:
            result["errors"].append({"row": number, "reasons": sorted(set(errors))})
    result["rows"] = len(rows)
    result["note"] = "Structural diagnostics only. Hash shape does not prove provider authenticity."
    return result

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("board")
    p.add_argument("--report")
    args = p.parse_args()
    output = json.dumps(validate(args.board), indent=2, sort_keys=True) + "\n"
    if args.report:
        with open(args.report, "x", encoding="utf-8") as handle:
            handle.write(output)
    else:
        print(output, end="")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
