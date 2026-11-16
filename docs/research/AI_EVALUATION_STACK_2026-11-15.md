# SportsEdge observability & AI evaluation — research v1

This is a **read-only evaluation companion**. The frozen betting models,
selected markets, stake rules, historical cards and A–E release gates are
unchanged. All output is **PAPER / 0u**, NOT official.

## What's integrated

| Layer | Current wiring | Status |
| --- | --- | --- |
| Native quality gate | `integrations/observability/quality_gate.py` | CI-tested stdlib-only; local private JSONL input |
| Whylogs | `optional_sinks.write_whylogs_local` | Optional local binary profile; install `whylogs pandas` |
| MLflow | `optional_sinks.write_mlflow_local` | Optional local experiment tracking; install `mlflow` |
| Promptfoo | `promptfoo/promptfooconfig.yaml` | Pinned offline fixture workflow, no actual AI model |
| Langfuse | `optional_sinks.trace_langfuse_aggregate` | Off by default; explicit owner opt-in and credentials required |
| Arize Phoenix / DeepEval / TruLens / W&B Weave / OpenLIT | Not connected | Avoid redundant tracing layers |
| Oxylabs MCP | Not connected | External web-data service is not a verified sportsbook source |

**Critical:** Hash strings and operator-declared timestamps validate *format and
relative chronology*, not actual bookmaker/provider authentication, independent
publication time or genuine historical point-in-time availability. A strong
source-to-result report is NOT an odds feed, a calibrated model, authentic CLV,
or evidence of positive EV. Nothing here changes `sportsedge_v5.py`.

## Input contract (private, one JSON object per JSONL line)

One line represents ONE frozen proposed selection / original quote, with
these required groups:

- `sport` (NFL/CFB/CBB/NBA/MLB/NHL/PGA), `event_id`, `period`,
  `market`, `side`, `tipoff_utc`; `line` for lines/totals/props;
  `subject_id` for player props.
- `model`: `sha256`, `trained_until_utc`, `freeze_utc`,
  `probability` (strictly between 0 and 1).
- `source`: `provider`, `sha256`, `data_through_utc`,
  `published_utc`, `captured_utc` with
  through ≤ published ≤ captured ≤ model freeze.
- `quote`: `book`, `sha256`, `captured_utc`,
  `price_american` before model freeze and event start.
- Optional **post-event** `outcome`: `result` (W/L/P) and `settled_utc`.
  Result must be recorded after tipoff; pushes are preserved, not treated
  as wins or losses for binary Brier/log loss.
- Optional `close`: same event, book, market, side, period, line and player
  ID as take; original SHA, capture time between take and event start,
  and American price. Mismatches are BLOCKED, not approximated.

All timestamps must be explicit `YYYY-MM-DDTHH:MM:SSZ` in UTC. This is a
strict *single frozen decision* inspector. Multiple quote observations of
the same selection aren't separately counted wagers; ALL repeated selection
decisions are quarantined in the output. Different alternate lines and
different player identities remain separate rows.

An illustrative **synthetic** payload (NOT a real book capture):

```json
{
  "sport":"CBB", "event_id":"synthetic-1",
  "period":"FG", "market":"total", "side":"over", "line":"149.5",
  "tipoff_utc":"2026-11-15T19:00:00Z",
  "model":{"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
           "trained_until_utc":"2026-11-14T21:00:00Z",
           "freeze_utc":"2026-11-15T17:45:00Z","probability":0.58},
  "source":{"provider":"synthetic",
            "sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "data_through_utc":"2026-11-15T16:00:00Z",
            "published_utc":"2026-11-15T16:15:00Z",
            "captured_utc":"2026-11-15T17:00:00Z"},
  "quote":{"book":"synthetic_book",
           "sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
           "captured_utc":"2026-11-15T17:30:00Z","price_american":-110}
}
```

Example intentionally has no real evidence. Do not put any genuine provider
records, private player identifiers, source URLs, authenticated receipts or
credentials in this **public** repository.

## Use in a private Python job

```sh
python integrations/observability/quality_gate.py \
  --input /private/sportsedge_frozen_decisions.jsonl \
  --out /private/sportsedge_quality_2026-11-15.json

cd integrations/observability
python -m unittest -v test_quality_gate.py test_optional_sinks.py test_promptfoo_policy.py
```

The evaluator creates a new report and refuses to overwrite a prior report.
It contains a per-row index and 16-character source-row digest prefix,
blocked reasons and sanitized aggregate counts. It never modifies source
records or predictions. The digest prefix is a local debugging aid, not proof
of independent provenance.

**Metrics** are purely descriptive: Brier/log loss only on decided W/L
records, and closing-price probability gain only on matched identical
selection/book/line prices. This is **not** no-vig CLV; it does not establish
market win probability, calibrated forward performance or profitability.
Rows with no closing receipt are counted as unmatched. A reported "clean"
record still has `source_authenticated=false` and `official=false`.

## Optional local Whylogs & MLflow outputs

Install in a **private** environment, not the default SportsEdge requirements:

```sh
python -m pip install whylogs pandas mlflow
python integrations/observability/export_aggregates.py \
  --report /private/sportsedge_quality_2026-11-15.json \
  --whylogs-bin /private/quality_2026-11-15.bin \
  --mlflow-dir /private/mlruns
```

Only a fixed allowlist of numerical aggregate metrics is sent to these sinks.
Whylogs uses only a LOCAL writer without calling `why.init()`.
MLflow is forced to a local `file://` tracking directory; no remote server.
These SDK adapters have synthetic stubs in CI; successful real installation
and data profiling must be verified in a separate private environment.
Keep `mlruns/`, `*.bin`, provider data and generated reports out of GitHub.

## Promptfoo offline regression

```sh
npm exec --yes --package=promptfoo@0.125.1 -- promptfoo eval \
  --config integrations/observability/promptfoo/promptfooconfig.yaml --no-cache
```

This tests a local deterministic Python fixture provider, ensuring a
structured research response with `official:false`, `stake_u:0`,
`source_authenticated:false` stays marked `PAPER / 0u`, and unexpected
EV/official price/stars/unit claims are BLOCKED. It does **not** yet run
SportsEdge's real generative agent, test factual claims, or measure its token
costs. To evaluate a real agent later, bind actual **sanitized** outputs
to the same `candidate` schema and keep a private trace/evaluation ledger.
The GitHub workflow `promptfoo-offline.yml` runs only offline fixtures.

## Langfuse opt-in only

Unlike the local options, Langfuse can send telemetry to an external
service. The adapter is **disabled by default**. To opt in, install the
current SDK in a private runtime, set `SPORTSEDGE_ENABLE_LANGFUSE=1`
and your own `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` in secure
environment variables, review the host/retention policy and run:

```sh
python integrations/observability/export_aggregates.py \
  --report /private/sportsedge_quality_2026-11-15.json --langfuse
```

Only aggregate count/metric tags are emitted; no raw prompts, receipts, user
identifiers or event-specific predictions. This call has not been executed
against a live Langfuse account. NEVER commit keys to GitHub or attach them in
chat.

## Gates & remaining work

1. Connect private original frozen source/quote/outcome ledgers with a
   first-party, verified identity bridge; current adapter expects a prepared
   JSONL and **does not automatically run on RUN IT**.
2. Independently attest source capture/publication and book quotes; do not
   confuse a file SHA with an external signed receipt.
3. Establish an immutable versioned forecast registry and forward score/
   calibration evaluation with uncertainty and market baselines.
4. Attach the actual agent runtime to Promptfoo/Langfuse *only after*
   legitimate model/provider account setup and a privacy review.
5. Independently pass per-market gates A–E. No official staking is enabled.

References: Whylogs <https://docs.whylabs.ai/docs/whylogs-overview/>;
MLflow <https://mlflow.org/docs/latest/ml/tracking>;
Promptfoo <https://www.promptfoo.dev/docs/providers/python/>;
Langfuse <https://github.com/langfuse/langfuse-python>.
