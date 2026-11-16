# Gate A claimed-source lineage research

Run `python -m unittest discover -s research/evidence -p 'test_source_lineage_gate.py' -v`.

This fail-closed standalone candidate validator rejects duplicate aggregator chains, same upstream operator, stale or post-kickoff quotes, mismatched exact markets, missing identities and nonfinite prices/lines. It does **not** authenticate any provider or assert that declared source identities are true. Use only with future authorized captures kept in restricted storage. All results remain PAPER/0u. No source credentials, prices, wagers or original evidence are stored in this public repository.
