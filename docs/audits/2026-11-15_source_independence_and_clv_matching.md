# Strict source independence, identity and closing-line matches — 2026-11-15

**What this repairs:** The prior Issue #10 research comparator rejected a secondary quote from the same upstream *book* but could treat two different book logos delivered by one aggregator/capture chain as structurally independent. A market moneyline with an empty line and the same moneyline with "0" yielded different canonical keys. Yes/no TD markets incorrectly tolerated a numeric line. The CLV triple permitted three different upstream bookmakers or provider-market IDs to be scored as a comparable same-market closing-line move.

**Changes:** Canonicalize MONEYLINE blank/zero aliases, reject numeric TD yes/no lines; fail closed for shared provider or shared upstream-provider capture path; require consistent upstream bookmaker, collection path and provider event/market ID for all opening/taken/closing receipts, and strictly later observed close after taken.

**Eight synthetic regression tests** verify both false-positive suppression and retention of valid distinct-source research-only behavior. Existing flow remains NO WAGER/PAPER 0u. No DK, BestBook, paid or third-party live endpoint is assumed or accessed. No claims of externally authenticated prices, signed quote timestamps, or profitable EV.

**Why this matters for Gate A and D:** Same-aggregator dual logos do not satisfy independent-source chains; cross-book closing odds are valid **comparators** only when clearly labeled and must not be counted as same-book CLV triples. Provider source IDs are still self-reported schema fields. A real source attestation and 200 settled matched close records are required before Gate D.
