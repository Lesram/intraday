# Session evidence repair — September 22, 2026

The September 21 paper session closed nine trades for $12.30 gross, with all closes reconciled to the broker. Its scheduled evidence pack was nevertheless BLOCKED: four observed entries exceeded the collector's 120-second bar-age limit, and deployed logs could not establish formal tick coverage. Eight watchdog samples also reported a reachable but not-ready API without retaining the dependency that failed.

The implementation scope is recorded in `artifacts/session_evidence_repair/plan.json`. Work takes place on a feature branch in an isolated checkout. The running paper installation, its credentials, models, historical records, private approval binding and forward cutoff are not changed by preparing this PR.

## Repairs that preserve trading decisions

### Log production and session collection

Use a real JSON serializer and timezone-aware UTC event timestamps derived from the log record's creation time. Quotes, nested structured messages, exceptions and multiline messages must remain one valid JSON record per line.

Future session collection must have an explicit canonical source that does not mix new valid evidence with all historical malformed rotations. The session stream is append-only, separated by UTC date, and preserved across process restarts. The collector records the source contract in its immutable pack. It must still withhold coverage when the requested session stream is missing, malformed, inconsistent or incomplete. Old packs retain their original interpretation; Monday is not retroactively approved by this repair.

Acceptance covers the actual deployed logging configuration through the actual collector, including date rollover, restart append, escaped messages, invalid or missing records, duplicate/rotation handling, and gaps exceeding the existing 120-second coverage budget.

### Readiness failure evidence

Retain bounded HTTP status, known component checks and fixed failure categories for unsuccessful readiness probes. Do not retain arbitrary response bodies, exception messages, credentials, URLs or headers. A malformed or oversized response must produce a controlled diagnostic outcome.

Existing decisions to notify, recover or refrain from restarting remain unchanged. A reachable but not-ready service must not become eligible for a restart merely because the new diagnostic decoder can explain the failure. Successful readiness retains its existing compatibility contract.

Non-ready observations add `readiness.diagnostics`: an optional numeric HTTP status, fixed body parse status, boolean checks for database/broker/brain-loaded/tick-recent, and fixed component reason codes. Unknown reasons become `unclassified`; response prose, URLs, headers and exception text are omitted. Bodies are capped at 8,192 bytes. These diagnostics become available only after controlled deployment; Monday's missing response bodies cannot be recovered.

### Deterministic test setup

The nightly run had 64 failures and 62 errors. Repair deterministic test fixtures against the current schema and service interfaces, with an isolated test database and explicit ownership of records. Authentication fixtures must support both SQLite and PostgreSQL. Async resources must be created and disposed on the same test event loop.

External API/market-data tests require separately declared services and credentials. An unavailable external integration is not a passing test. Do not give the suite production credentials, invoke the installed paper service, blanket-skip failures or remove trading assertions to manufacture a green result. Coverage-related CPU timeouts and historical-reference dependencies require targeted evidence and an explicit test-lane design; they are not runtime strategy changes.

The repaired nightly workflow requires two fatal test lanes: core tests retain coverage, while the seven demonstrated CPU timeout cases run with their assertions unchanged and without coverage, using a 120-second default and preserving existing longer test markers. Both use an explicit random seed and retain separate JUnit/log evidence. Collection fails if any required replay node disappears. Selection manifests list external-dependent tests as `UNAVAILABLE`, keep ordinary database/model tests from the same directory in the core inventory, and disclose the actual post-marker selection. The existing core `not slow` selection is unchanged; for example, database-idempotency cases marked slow remain excluded by that existing filter and are not newly certified. The workflow summary remains explicit that external integration verification is unavailable even if both software lanes pass.

Shared API fixtures use the application's own event loop and database pool for real password login. PostgreSQL requires an explicit `INTRA_TEST_DATABASE_URL` with a local test-named database and user, migrated through Alembic; otherwise each API test receives a private SQLite database. Strategy tests own their transaction and use savepoints so service commits cannot leak rows between tests. The V12 archive check addresses the verified historical commit directly instead of requiring a locally materialized branch or inventing an archive at HEAD.

## Proposed freshness repair — explicit approval required before implementation

The current runtime's streaming freshness check measures elapsed wall time since a callback arrived. The collector measures order submission time minus the final feature bar's timestamp. These are different quantities. The four failing September 21 frames were already approximately 124–126 seconds old when captured; capture-to-submit delay was only about 0.1 seconds.

For the approved one-minute paper strategy, the proposed contract is:

1. Base entry freshness on the timezone-aware timestamp of the actual final bar used by the decision, with a maximum age of 120 seconds at final order admission.
2. Apply the same rule to streaming and REST fallback, alpha and pure-breakout entries. A newly received callback or REST response must not make old feature data fresh.
3. Fail closed on missing, invalid, ambiguous or future timestamps. Define timestamp/bar-completion semantics explicitly in the tests; do not substitute receipt time for provider event time.
4. Recheck at final submission. If a frame ages out during processing, block that entry and emit the fixed rejection reason and measured age. Protective exits remain available.
5. Keep the collector's threshold unchanged. Preserve original entry receipts and the September 21 blocked verdict.

This changes which entries can execute. It is a frozen trading-decision change even if implemented in a helper outside the originally enumerated hashes. Implementation therefore requires Marsel's explicit approval under AGENTS.md, followed by targeted tests, replay evidence, a runtime-config snapshot, reviewer acceptance and a separately approved deployment with a new forward measurement boundary. No cutoff is changed by this document or the non-decision repairs.

Required freshness tests include the inclusive 120-second boundary and values just beyond it; timezone offsets, absent/future timestamps, newly received old bars, stale REST fallback, delay between capture and submission, both entry paths, and preservation of protective exits. Historical counterfactual checks may identify entries blocked at their original instant, but must not claim that subtracting those trades predicts an alternative day's P&L.

The exact approval item is: **enforce the shared actual-bar age rule at final entry admission, including streaming and REST fallback, and establish a new forward evaluation cutoff when that decision change is released.** This does not authorize changing the data feed, tuning strategy parameters, replacing models, enabling learning/promotion or real-money trading.

## Completion and rollout evidence

Before merging the non-decision repair PR: targeted tests, config/system integration checks, organism state/exit/sizing/replay regressions, a full artifact pack, current audit index, independent review and read-only freeze verification must pass. Reports must distinguish offline defaults from the actual installed runtime.

Any later deployment must preserve user state and the original failed evidence, verify the actual logger-to-collector path and watchdog diagnostics, and update source/image bindings through the controlled release process. A healthy pre-open check is not a clean-session verdict. Natural-session evidence remains required, and software correctness alone does not establish a trading edge.

Synthetic release-handover checks now exercise two approved entry identities with the same cutoff and pinned historical ledger prefix. They preserve trade accounting while withholding qualification if the old identity is omitted, and reject old source/image/config/container identities as attestations of the current runtime. The complete affected collector module passes 85 tests, including these six new cases; no production code changed for this additional validation.

The current generated configuration snapshots describe this PR's isolated test run: their one-day defaults, zero default loss/notional limits and temporary telemetry paths are not installed paper settings. Both configuration snapshots explicitly identify their evidence scope and deny engine observation; the audit generator labels these values as configuration resolution on every run. The live-process snapshot remains unreachable and unverified. The earlier September 21 stopped-container configuration resolution is preserved separately in [historical resolved configuration](../../artifacts/session_evidence_repair/snapshot_provenance_historical_20260921_resolved_config_snapshot.json) and [historical legacy configuration](../../artifacts/session_evidence_repair/snapshot_provenance_historical_20260921_runtime_config_snapshot.json), with its original timestamp and source/image identity. Those archives establish historical expected settings, not current engine state. The [provenance receipt](../../artifacts/session_evidence_repair/snapshot_provenance_receipt.json) binds both archives and confirms that current configuration values were not changed by the labeling correction. Actual installation acceptance still requires a separately captured runtime observation.
