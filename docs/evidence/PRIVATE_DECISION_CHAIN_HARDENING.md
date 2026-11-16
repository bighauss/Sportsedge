# Private research decision chain — defensive rules

This document describes a **local**, untrusted, append-only SportsEdge
research-decision log: `sportsedge/odds/storage.py` / `EvidenceChain`.

- The path must be outside the public Git checkout. Both the lexical location
  and symlink-resolved destination are checked before any directory creation.
- The log is created with owner-only permissions; an existing file with group
  or world permissions is refused instead of being silently trusted.
- Prior entries are verified before every append. Reused decision IDs, missing
  required identity/time/stake fields, duplicate JSON keys, non-finite JSON
  literals, invalid hashes, broken sequencing and partial lines fail closed.
- No private quote payloads or credentials are admitted in the decision log;
  use a restricted evidence store for raw captures and receipts.

A SHA-256 hash chain stored only on the same writable filesystem is **not**
immutable. Without independent head anchoring, original provider attestation,
and protected storage it cannot prove past existence or authentic odds. All
research log records remain `PAPER / 0u` and are not wagering instructions.

Tests: `python -m unittest sportsedge.odds.test_issue10_offline -v`.
