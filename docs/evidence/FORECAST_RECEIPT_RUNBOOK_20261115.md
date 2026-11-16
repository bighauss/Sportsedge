# Prospective forecast receipt — seven-sport research only

**Status:** PAPER / 0u. This contract archives a digest of the model's *actual
saved predictions* and binds it to a previously saved point-in-time (PIT) freeze.
It does **not** attest who supplied the sources, that the wall clock was trusted,
which markets DraftKings offered, what true closing prices were, or that the
model was calibrated. It does not produce a wagerable card or satisfy Gate A–E.

## Private execution — one trusted shared registry

The operator must supply actual authorized, as-of source bytes and original
model output files. No provider credentials or private source material belong
in this public repository. This tool cannot fetch originals or manufacture
predictions.

1. First create a genuinely pregame seven-sport PIT freeze with
   `python -m sportsedge.validation.seven_sport_pit_freeze PRIVATE_REQUEST.json --out PRIVATE_FREEZE.json`.
   Retain the unchanged original code, configuration, feature data and freeze.
2. Provision **one persistent, shared and owner-only registry** for forecast
   receipts. It must be an absolute existing directory of mode 0700, owned by
   the running account, with no symlink aliases, outside the public checkout
   and runner working directory. Every worker must use the **same** namespace.
3. After the model produces its original probabilities before the event, run:

   ```bash
   mkdir -m 700 /private/sportsedge/forward-forecast-registry
   python -m sportsedge.validation.prospective_forecast_receipt \
     --freeze PRIVATE_FREEZE.json \
     --forecast PRIVATE_FORECAST.json \
     --registry-root /private/sportsedge/forward-forecast-registry
   ```

   The receipt path is generated automatically as
   `forecast-receipt-<sha256-of-sport-event-market-period-original-freeze>.json`.
   The CLI prints that private path. An optional explicit `--out` is accepted
   **only** if it is exactly the canonical location. A second output under a
   different filename or directory is refused.
4. Retain the unchanged original freeze/forecast bytes and private digest
   receipt. The report stores hashes, source counts and identity hashes only:
   **no model probabilities, personal player names or bet prices**. Original
   files are never overwritten; the 0600 receipt is create-only and fsynced.

The original forecast must be generated and captured after the earlier freeze
and before kickoff, with a claimed capture no older than five minutes when
the receipt is written. Missing actual as-of publication evidence remains a
blocking gap; local hash verification is not an independent time attestation.

## Scope and limitations of canonical uniqueness

The source-to-forecast receipt now has one operator-shared physical slot per
**(sport, event, market family, period, original PIT freeze SHA)**. Changing
probabilities or output filename cannot create a second receipt for that
identity; two concurrent processes contend for one `O_EXCL` path.
**This is not a global uniqueness proof**: a different registry root on another
host, administrator rewrite/removal, or a separately generated original freeze
can still yield competing local claims. The operator must attest a common
shared mount and eventually export a signed immutable external history. The
pure `assess()` helper is a read-only diagnostic, not a production admission
path. Original source-clock/authentication gates remain OPEN.

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
