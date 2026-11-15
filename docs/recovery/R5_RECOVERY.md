# Recovered SportsEdge R5 research code — 2026-11-15

Source: SportsEdge_Integrated_Engineering_R5_20261113.zip, SHA256 `5ffad3d9a61b629aee8da2f2687f945ad46ab0b9e44a63b404a92535107eeb77`.
Independent closure source: SportsEdge_Independent_Closure_20261113.zip, SHA256 `708a0bc27a4e6b40812d337e82ed1ceeadb557b315061b7655cbcc190b8122a1`.

The frozen engine of record is `engine/sportsedge_v5.py`, byte-identical to `research/r5/nfl/sportsedge_v5.py`: SHA256 `72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f` (adopted Nov 11, 2026).

R5 NFL board guard, slate reconciler, projection integrity, model lineage, close pair, pass/kill and daily lane implementations are included as **research-only** source. Historical NFL board captures, results and receipt artifacts were NOT committed to this **public** repository; they remain on Drive. Consequently some original historical replay tests are intentionally omitted rather than committed as broken tests or marked successful without their fixtures.

The restored regression subset comprises CFB R2-R5 (48 assertions), NBA append guard (24), NFL family pass/kill (6), and NFL fail-closed input cases (9): **87 tests passed locally using synthetic data, with no historical board snapshots**.

The underlying models and rules are not demonstrated to produce positive forward EV. Outputs remain PAPER / 0u; no live execution or wagering is authorized. See `docs/audits/2026-11-15_migration_audit.md` and the original R5 README for historical context. No wrappers or prices were fabricated in recovery.
