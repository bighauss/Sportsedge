# SportsEdge AI/ML observability adoption (research only)

Prioritize a **dependency-free local run-manifest contract** before external services. This makes provenance auditable without shipping sportsbook receipts, player data, credentials or private model inputs to third-party SaaS.

- **MLflow**: optional later self-hosted experiment registry; only sanitized metadata, pinned version/config hashes and deterministic seed, never original restricted bytes.
- **Whylogs**: optional future aggregate input-drift diagnostics; disable telemetry and use private storage, test for sensitive-value leakage.
- **Arize Phoenix / Langfuse / OpenLIT**: optional agent traces, only after privacy review and explicit authorization; raw prompts may contain sensitive source material.
- **DeepEval / Promptfoo**: optional offline tests for unsupported betting claims and prompt injection; no requirement for paid API keys.
- **Oxylabs**: web-access integration, **not** evidence of sportsbook rights or independent bookmaker provenance.

`research/observability/run_manifest_contract.py` verifies local raw-source hashes, complete original source inventory, strict provider-claimed chronology, model hash and seed. It returns only PAPER/0u status. Source clocks are **self-reported, not independently attested**. Model SHA is a claim until the caller separately hashes pinned code; this module does not fetch files or run models.

No change to frozen v5, existing picks, risk, Gate A–E, provider permissions or wager execution. Original bytes and manifests must remain in restricted private storage outside the public Git checkout. Future integration must bind model/config artifacts and external timestamps independently before promotion.
