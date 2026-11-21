# Paper batch grading

Run a private, no-network grading batch with Python:

```sh
python -m sportsedge.validation.paper_grade_batch /private/grade-batch.json
python -m sportsedge.validation.paper_grade_batch /private/grade-batch.json \
  --database /private/result-only.sqlite
```

The first form is dry-run. The second appends exact wins, losses and pushes idempotently to the existing paper ledger format. Use a dedicated result-only SQLite database: the legacy price and CLV ledger stores a richer, different record for the same pick ID. This command never mutates either grade to attach prices later.

The manifest is a private JSON object with `schema` set to `sportsedge-paper-grade-batch-v1` and an `entries` list. Each entry has `kickoff_utc`, a `pick` evidence reference, and optional `final` and `taken` evidence references. Each reference has a relative `path`, the original bytes' lower-case hexadecimal `sha256` and `captured_at_utc`. The pick object has `pick_id`, `kickoff_utc`, `decision_at_utc`, `home_id`, `away_id` and the full canonical `market` object. The final uses the original ledger's final shape plus `final_available_utc`; the same event and ordered teams must match the frozen pick. No missing score split, player stat or unplayed result is inferred.

The command reports aggregate pick, result, quote and append states separately. An absent price does not prevent grading. A malformed or post-decision price is flagged separately; even an exact two-sided matching price is not authenticated by this command. Pending results are not written as losses. Do not place private evidence or the SQLite file in a checkout.

This is an offline consumer of archived evidence. It does not pull official scores, run a schedule, support a new market, settle PGA tournament markets, or authorize stakes. Provider-specific final and player-stat adapters must preserve original responses and not invent availability clocks.
