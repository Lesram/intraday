# September 24 streaming and readiness repair

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
directory. Correcting the indicator inputs needs explicit additional scope
approval and replay; this release includes no composite correction or claimed
feature-speedup. Feature-store QA, snapshot generation and computation remain
unchanged.

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
