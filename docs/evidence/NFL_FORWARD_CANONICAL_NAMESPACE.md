# NFL player forward forecast: canonical private freeze and grade namespace

**Status: research PAPER / 0u. No independently authenticated sportsbook, lineup, publication-clock or model calibration evidence.** This work closes only the **single-shared-registry** cherry-picking loophole documented in [Issue #50](https://github.com/bighauss/Sportsedge/issues/50).

## One trusted registry root — not one output filename per operator

Provision ONE persistent, owner-only private directory on a shared filesystem visible to every writer for that SportsEdge deployment. It must be an absolute path, a real directory, owned by the running account and **exactly mode 0700**, without symlink components, outside the public Git checkout and execution working directory. Use the same root on every writer and grading host. Never change the environment or mount to a different root per run.

The CLI requires `--registry-root` for both commands and refuses any `private_output_json` that isn't its derived canonical path:

```sh
mkdir -m 700 /private/sportsedge/forward-player-registry
python -m sportsedge.validation.forward_player_evidence freeze /private/input/freeze-request.json \
  /private/sportsedge/forward-player-registry/freeze-2026-w11-GAME1.json \
  --registry-root /private/sportsedge/forward-player-registry

python -m sportsedge.validation.forward_player_evidence grade /private/input/grade-request.json \
  /private/sportsedge/forward-player-registry/grade-2026-w11-GAME1-<original-64-character-sha256-hex>.json \
  --registry-root /private/sportsedge/forward-player-registry
```

Actual event, season, week, source-file names and SHA must come from an original verified research manifest; the example `GAME1` is **synthetic**, not a 2026 NFL game or live forecast. Use the original freeze SHA returned by the prior command in the grade output name. Do not backdate `forecast_asof_utc` or claim a current public asset was available in a historic season.

- Canonical freeze identity: `freeze-{season:04d}-w{week:02d}-{event_id}.json`.
- Canonical grade identity: `grade-{season:04d}-w{week:02d}-{event_id}-{original_frozen_sha256_without_prefix}.json`. Before grading any final, the original frozen file must reside at its canonical freeze location under the **same** trusted root, have original matching SHA, be a regular owner-only file, and bind the exact event+season+week.
- Outputs use `O_CREAT|O_EXCL|O_NOFOLLOW` with mode `0600` and `fsync`. Two concurrent processes trying to write a second freeze/grade in the same namespace cannot both succeed; the first original is not rewritten. An alternate output directory or name is rejected rather than producing a competing valid research archive.
- The low-level pure functions `freeze_player_forecasts`, `grade_frozen_capture` and `_write_private_create_only` remain testable utility functions. **They are not the canonical admission path**. Only the strict CLI with one operator-controlled `--registry-root` enforces the namespace.
- Refusal is an exception before writing an alternate accepted report. Full refusal histories (including failed attempts) need independent append-only operator logs; the archive is not a provider-signed or notarized receipt.

## Limits of the guarantee

This is a **single local/shared-filesystem namespace**, not a distributed global uniqueness proof. Operators with control of the registry root, filesystem, process or host can copy/delete/move files, change roots, or suppress runs. A caller could invoke low-level Python functions directly without the CLI. Symlink/permission and `O_EXCL` checks prevent ordinary accidental aliases/races but are not a substitute for write-once externally attested storage, mount-pinned registry ID, independent time anchoring, provider-native signed source records, and owner review. If any other host cannot access the same trusted root, **HOLD / NO CERTIFICATION**; do not merge separate roots retrospectively.

The pre-existing source and lineup chronology checks still require independent source and as-of evidence. Even if the CLI completes successfully, `source_authenticated_independently=false`, `model_probabilities_calibrated=false`, `approved_stake_u=0`, `official_counted=0`, and every market Gate A–E in [Issue #10](https://github.com/bighauss/Sportsedge/issues/10) stays OPEN. Do not infer EV or generate official bets.

Run adversarial offline regression:

```sh
python -m unittest sportsedge.validation.test_forward_player_evidence -v
```

Includes same-event different-name refusal, canonical grade source binding, copied-source alias refusal, insecure/symlink root refusal, independent process competition on one canonical file, and backwards-compatible synthetic feature/lineup and final grading contracts.
