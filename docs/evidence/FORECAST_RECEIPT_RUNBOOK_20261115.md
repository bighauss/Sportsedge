# Prospective forecast receipt — seven-sport research only

**Status:** PAPER / 0u. This contract archives a digest of the model's *actual
saved predictions* and binds it to a previously saved point-in-time (PIT) freeze.
It does **not** attest who supplied the sources, that the wall clock was trusted,
which markets DraftKings offered, what true closing prices were, or that the
model was calibrated. It does not produce a wagerable card or satisfy Gate A–E.

## Private execution

The operator must supply genuine authorized, as-of source bytes and forecast
outputs. No source material or credentials belong in this public repository.
This tool does not fetch them and never manufactures absent predictions.

1. First create a pregame freeze with
   `python -m sportsedge.validation.seven_sport_pit_freeze PRIVATE_REQUEST.json --out PRIVATE_FREEZE.json`.
   It must contain an exact digest of the model code, config and each feature
   source. Its original source bytes stay in owner-private storage.
2. After the model actually writes the original probability-output JSON (not
   retrospectively generated), execute:
   ```bash
   python -m sportsedge.validation.prospective_forecast_receipt \
      --freeze PRIVATE_FREEZE.json \
      --forecast PRIVATE_FORECAST.json \
      --out PRIVATE_NEW_RECEIPT.json
   ```
3. Retain all three original files and model input sources. The receipt only
   records SHA-256 digests; it contains **no predictions**, prices or player names.
   No file is overwritten. Capture must be before the event start and within
   five minutes of running the receipt command.

Use a private directory with mode 0700 and files with mode 0600; symlinks and
paths inside the public checkout are refused. This requires a local computer,
trusted storage or an authorized execution environment. It is *not* a live feed
or a phone-only sports-data connection.

## Forecast file contract

Strict UTF-8 JSON, one event / one sport-market family / one period. Every
field is mandatory and additional fields are rejected. The following is a
**schema example only**; placeholder hashes are not source evidence.

```json
{
  "schema": "sportsedge-prospective-forecast-v1",
  "state": "PAPER_0U",
  "sport": "NFL",
  "event_id": "EVENT_ID_FROM_SAVED_FREEZE",
  "market_family": "TOTAL",
  "period": "FG",
  "model_version": "VERSION_FROM_SAVED_FREEZE",
  "freeze_record_sha256": "sha256:REPLACE_WITH_EXACT_ORIGINAL_FREEZE_FILE_DIGEST",
  "model_code_sha256": "sha256:REPLACE_WITH_FREEZE_MODEL_CODE_DIGEST",
  "model_config_sha256": "sha256:REPLACE_WITH_FREEZE_MODEL_CONFIG_DIGEST",
  "feature_source_hashes": {
    "SOURCE_ID_FROM_FREEZE": "sha256:REPLACE_WITH_EXACT_SOURCE_DIGEST"
  },
  "generated_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "captured_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "predictions": [
    {
      "market_identity": [
        "NFL", "EVENT_ID_FROM_SAVED_FREEZE", "TOTAL", "FG", "OVER",
        "42.5", "", "", "", "INCLUDES_OT"
      ],
      "model_probability": "0.55"
    }
  ]
}
```

The ten market-identity fields are, in order: sport, event, family, period,
selection, line, team ID, player ID, stat, and settlement. Field values must be
printable ASCII without leading/trailing whitespace or the pipe separator.
The first four fields must match the freeze. Selection and settlement cannot
be blank. The tool casefolds identity values to reject duplicate selections;
every model probability must be a **decimal string strictly between 0 and 1**
(no NaN, Infinity, or rounding a price into a fake model probability).

The forecast input must contain 1–5,000 distinct selections, keep the complete
original freeze feature-source hash census, and use precisely the earlier
model/config digests. The two original JSON files are hashed as bytes, and
the receipt binds those hashes without copying raw forecast values.

## Audit interpretation

A valid local receipt only says: **these original forecast bytes were present
when this local command ran and self-reported a pre-event timestamp**, and they
refer to this earlier locally hashed freeze. It is **not** an independent trusted
time anchor, WORM storage, provider authentication, or proof of forecast
profitability. Later honest evaluation still requires original bookmaker
quotes, source authorization, independently verified results, all losses,
preregistered calibration rules and authentic closing-line records. Until
those checks pass, official counts and approved stake remain zero.
