# September 24 streaming and readiness repair

## Approved September 25 extension

Marsel approved including the composite-indicator correction and its replay
validation. The helper now supports its three existing scalar-numerator callers
using `abs(a)`, retaining Series alignment and zero/zero/epsilon behavior. This
restores computed strategy inputs; it is deliberately recorded as a frozen
surface change, not a strategy-weight or threshold adjustment. The feature and
composite modules now participate in the candidate source freeze, and runtime
snapshots expose the actual canonical composite column list.

New tests must fail against the defective helper and verify all three callers,
the complete composite master and the actual ML feature path. Paired deterministic
trading replay compares the defective and corrected helper on identical synthetic
data, including admitted orders and exits. It does not reconstruct September 24
or establish a profitable strategy. Current acceptance receipts are under
`artifacts/composite_indicator_repair/`; earlier defect/prototype evidence under
`artifacts/streaming_readiness_repair/` remains unchanged as historical evidence.

The running paper deployment and active cutoff are unchanged by this candidate.
The legacy fallback policy is retained. The ML cache remains excluded, and no
feature-speedup claim is made.

The September 24 session ran without restart but submitted no orders. Scanner
discovery worked, while its expanding feature universe was never synchronized
with streaming subscriptions. The alpha routing path requires recent streaming
receipts, so discovery alone did not create an eligible entry path. Ordinary
scanner replay omitted the streaming provider and did not exercise this link.

The candidate repairs that integration with a bounded, retried synchronization
after the existing broker-position query. Original base/benchmark dependencies
and held symbols remain subscribed. New symbols must receive actual bars;
subscription acknowledgment is never evidence of fresh prices. Any unresolved
subscription operation or stale symbol blocks entries while exits continue.

Candidate telemetry now separates heuristic, regime, stream receipt age and
confidence routing reasons. Aggregate alpha-build counters reconcile within one
tick and explicitly exclude later combined ranking/sizing/submission decisions.
Actual fetch origin and the two distinct freshness clocks are reported. Wall
segments measure where processing time is spent without changing replay hashes.
Performance optimization requires the accompanying fixed-input profile, not a
causal interpretation of the cross-day 13.4-to-17.1-second observation.

The fixed-input benchmark identified repeated ML feature calculations as the
dominant measured CPU work. The cache prototype is excluded from this release:
the review exposed an existing scalar-division defect that makes the feature
pipeline silently substitute zeros for all seven composite indicators. Retaining
those fallback results could suppress retries. Its source-bound reproduction,
test-coverage analysis and unaccepted prototype are retained in the evidence
directory. The indicator correction was subsequently approved September 25 and
is covered by the extension above. Feature-store QA, snapshot generation, cache
exclusion and all unchanged computation paths remain explicit acceptance limits.

Readiness now observes the real scheduler and returns typed, bounded PostgreSQL
and Redis outcomes. Existing deadlines, trading gates and recovery authority are
preserved. Market-closed and warmup states are explicitly distinguished from an
unresponsive scheduler. The watchdog consumes only fixed, allowlisted diagnostic
fields; private dependency exception text is never exposed.

Critical-log collection now advances only through fully inspected windows in
oldest-first order. Each pass starts with 60-second windows and halves overflowing
windows down to one second, with at most 12 queries and a 10-second total budget
(plus at most one second to clean up its own read-only log process). Each response
is capped at 262,144 bytes and must contain fewer than 1,000 lines. Truncated,
failed or malformed-cursor windows retain explicit backlog; they cannot move the
cursor past unread evidence. Missing first-run state alone permits bootstrap.
Recovery decisions and notification authority remain unchanged.

Acceptance requires real streaming-provider/fake-transport replay demonstrating
discovery, first-bar waiting, failure retries, actual admitted simulated orders,
and protective/EOD exits while entry gating is active. Each final admission
continues to use the exact decision frame and bar-start age. Required safety,
reconciliation and configuration suites plus the complete artifact pack must
pass; a separately verified candidate freeze records the deliberate source
changes while the active host cutoff remains unchanged until release.

The global any-stale-symbol policy remains a material limitation: subscribing a
larger universe can cause more stand-down cycles on sparse feeds. This candidate
does not certify actual feed capacity, an optimal 20-second rule, or strategy
profitability. Natural fills, uncertain acknowledgments and active exits still
need forward paper evidence. Strategy tuning, feed changes and the parked engine
decomposition remain outside scope.
