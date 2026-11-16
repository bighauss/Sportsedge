# Seven-sport prospective point-in-time freeze contract (research-only)

File: `sportsedge/validation/seven_sport_pit_freeze.py`. Applicable to **NFL, CFB, CBB, NBA, MLB, NHL and PGA** individually and in parallel. It is not a fitted prediction engine, live odds connector, grader or an authenticated timestamp authority. Every successful output is `PAPER_0U_LOCAL_CHRONOLOGY_ONLY`, 0 approved units and 0 counted selections.

## Purpose
Create an *actual prospective*, create-once private record tying together:
- the existing exact model source-code SHA (read-only `.py` file inside canonical repo);
- a private model config artifact with its original SHA;
- each original private feature source file with original SHA and claimed `data_through <= published <= observed <= captured <= freeze` UTC;
- a registered training cutoff, model version, market family/period, event kickoff and evaluation end date;
- the locked research-policy identifier `SPORTSEDGE_STRICT_V21_V22_20261115_R1`.

The model code must live under the matching `models/<sport>/` directory (for example, a PGA freeze must point to `models/pga/`, never an NFL or shared module). This check binds a sport label to its intended source tree; it does not establish that the model was trained, fitted or calibrated for that sport.

The script compares its local current UTC against the declared freeze (must be within the next five minutes *after* the freeze and still before the event). A historical retrospective row **cannot** be presented as newly frozen. Source/provider clock claims still need independent external attestation.

## Private request schema

Save a `0600` request JSON in a `0700` private folder OUTSIDE this public checkout. All referenced feature/config files must likewise be private `0600` files; source-code path is relative to repo root. An example structure is:

```json
{
  "schema": "sportsedge-seven-sport-pit-freeze-request-v1",
  "sport": "NFL",
  "event_id": "REAL_CANONICAL_EVENT_ID",
  "market_family": "SPREAD",
  "period": "FG",
  "model_version": "RESEARCH_REVISION_ID",
  "training_cutoff_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "registered_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "freeze_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "event_start_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "evaluation_end_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "model_code": {
    "path": "models/nfl/discrete_score_pit.py",
    "sha256": "sha256:EXACT_64_LOWERCASE_HEX"
  },
  "model_config": {
    "path": "/private/sportsedge/nfl/versioned_config.json",
    "sha256": "sha256:EXACT_64_LOWERCASE_HEX"
  },
  "feature_sources": [{
    "source_id": "NFL_SOURCE_ID_AND_SNAPSHOT",
    "file": {
      "path": "/private/sportsedge/nfl/original_release.json",
      "sha256": "sha256:EXACT_64_LOWERCASE_HEX"
    },
    "data_through_utc": "YYYY-MM-DDTHH:MM:SSZ",
    "published_utc": "YYYY-MM-DDTHH:MM:SSZ",
    "observed_utc": "YYYY-MM-DDTHH:MM:SSZ",
    "captured_utc": "YYYY-MM-DDTHH:MM:SSZ"
  }]
}
```

The placeholders are schematic only; the JSON cannot run until each placeholder has been replaced by actual data, exact SHA and real future timestamps. Do **not** backdate any clock. Every market/period requires separate source and model evidence.

Run from the repo root:

```sh
python -m sportsedge.validation.seven_sport_pit_freeze /private/sportsedge/nfl/request.json --out /private/sportsedge/nfl/new_frozen_event.json
python -m unittest sportsedge.validation.test_seven_sport_pit_freeze -v
```

Archive output is exclusively created mode `0600`, fsynced, and never overwrites an earlier event. Only hash/census and claimed clocks are emitted; private paths/raw bytes are not copied into output. Standard filesystem modes and local UTC are *not* external signatures or WORM storage.

## What a green test **does not** establish
No genuine DK/independent second-book original receipt, odds/market inventory completeness, as-of provider publication signature, registered 3-cycle walk-forward calibration, independently matched settled CLV, or connected market-specific release. No empirical model fit, actual frozen play or forward grade has been claimed by running synthetic fixtures. CBB Nov 9's original 496-side historical file remains unrecovered: do not regenerate it and label it original.

To close Issue #10 for each sport/market, add the independently authenticated external proof, append-only private decision/settlement receipt and signed owner promotion after the other separate gate requirements. **Do not edit frozen v5.**
