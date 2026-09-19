# Proposed paper partial-fill accounting correction — 2026-09-19

**Status: isolated proposal; not deployed, merged, or authorized for activation.**
Branch `codex/paper-partial-fill-accounting`, based on `b2785b6`. No paper orders,
broker changes, strategy tuning, historical rewrites, or forward-clock changes.

## Problem and concrete correction

The September-19 read-only broker reconciliation matched all 27 post-freeze
ledger closes to 61 filled paper orders. Their gross cash flow is **$89.819991**;
the ledger records **$84.922414**, an understatement of **$4.897577**. Six
`ml_reversal` scale-outs differ by more than a cent. They were also unflagged
because the reason lacks the word `partial`. These are accounting discrepancies,
not evidence of missing orders, profitability, or a better strategy.

For example, TSLA bought 6 at $321, sold 1 at $322.73 and 5 at $321.81.
The old close applies the final price to all 6 shares: $4.86. This proposal
uses all confirmed proceeds minus entry cost: **$5.78**.

`backend/organism/live_engine_fills.py` adds a read-only lookup anchored to the
stored entry-order UUID. The pure calculation uses decimal cash flows and
weighted entry/exit prices. It requires one attributed flat-to-flat position,
positive finite prices, terminal order states, unique local and broker IDs,
whole-share total quantity, and exact equality of total entry and exit quantity.
Canceled or expired orders contribute their confirmed partial fills. Filled
status with a contradictory filled/requested quantity is rejected. Reasons do
not determine whether a position scaled out.

The database wrapper separately rejects same-symbol active orders submitted
before reconciliation, even those predating the entry. It also rejects older
positive fills updated after entry because their lifetime attribution is
uncertain. Conflicting sources, missing identity, stale/incomplete order rows,
later positions in the same lifetime window, and database failure all leave
complete accounting unavailable. This conservative check may retain approximate
accounting for otherwise valid trades; it never cancels an order or edits rows.

`OrganismLiveEngine._reconcile_fills` uses the complete result when available.
`TradeRecord.price_source="db_position_fills"` means quantity-conserved,
attributed **database order** cash flows, not an independent broker verification
at close. Its entry/exit prices are weighted averages and its PnL includes every
leg. `had_partial_exits` then means multiple filled exit orders regardless of
reason. Historical `fill`/`db_fill` tags remain historical data.

When complete evidence is unavailable, the existing approximate fallback
amount is retained, with final-fill sources explicitly labeled
`fill_approximate` or `db_fill_approximate`. Quote/bar fallback tags remain as
before. **Fallback rows are still recorded once and feed normal learner and
risk paths; there is no later correction/retry in this patch.** Missing all
prices still follows the existing skip behavior. The old restart classification
also stays intact: a close with no explicit exit reason, cached fill or held
bars remains a `reconciliation_adjustment`, even if its cash flows are complete,
and stays excluded from learning and symbol-risk statistics.

The only additional source change documents these price-source semantics in
`continuous_learner.py`; that file's executable behavior is unchanged.

## Future state, historical state and limits

Corrected future closes change new TradeRecords, learner cumulative PnL and
history, symbol daily PnL/win-loss counters, regime Kelly history, prediction
outcome calibration, and persisted brain values through the existing save path.
Those can affect later gates, sizing and learning even though the entry/exit
strategy algorithms are unchanged. This is a runtime behavior change.

No existing ledger, manifest, learner counter, order, shadow row or brain file
is migrated. The inherited 609 learner / 610 all-record distinction is retained.
Existing daily/longer-term state is neither replayed nor reset. Startup recovery
without the entry-order identity can still use the legacy approximation.

No fee or slippage model is added. The running 3 bps round-trip cost convention
and the July protocol's 3 bps per side remain an unresolved policy distinction;
this patch selects neither. The historical broker figures are gross order-average
cash flows. Database completeness/freshness is a prerequisite: matching recorded
quantities cannot prove an unrecorded broker order never occurred. Concurrent
order-row updates and late execution attribution therefore remain operational
limitations requiring ongoing read-only broker/ledger reconciliation.

## Frozen surface and proposed activation decision

The six source hashes, strategy configuration, exit environment, routing policy,
IEX feed and `FROZEN_AT=2026-07-07T20:36:49.008305+00:00` remain unchanged.
`phase2_freeze.py --verify` exits 0 under the recorded frozen environment;
the freeze file is byte-identical. Passing this check does **not** authorize a
change to future risk inputs or validate pooling the two accounting conventions.

Recommended decision for Marsel, **not implemented by this proposal**:

1. Approve a specific tested commit for a paper-only maintenance window while
   broker-flat and with no outstanding orders, after preserving a verified
   brain/database/config snapshot. The operational readiness PR is independent.
2. Apply the correction prospectively. Keep the historical brain and raw corpus
   intact; retain the old history as inherited state. Do not backfill learner
   PnL or change the historical counter in the same deployment.
3. Preserve the July parameter-freeze artifact as provenance, but explicitly
   start a **separate accounting evaluation cohort** at the approved activation
   timestamp/commit, with zero eligible new observations. This is an explicit
   decision about the forward verdict clock, not a silent continuation claim.
   Preserve and report the earlier 27 rows and their broker reconciliation as
   historical evidence; do not count them as newly observed corrected-runtime
   outcomes. No new timestamp or counter is installed until Marsel approves.
4. Record the approved treatment in a separate activation manifest and research
   protocol, including inherited-state provenance and the chosen cost basis.
   The existing frozen parameters and evolution restrictions still apply.

If Marsel instead wishes to retain the July evaluation cohort, that requires a
separate preregistered treatment of the accounting intervention and costs before
any verdict. The current patch supplies no basis to silently pool them.

## Verification evidence

`tests/test_live_engine_fill_accounting.py`: **39 passing tests** in the focused
run. These cover the six discrepant cases plus XOM, weighted entries, terminal
partial fills, quantity/status/source conflicts, missing/duplicate identifiers,
pre-entry active orders, fractional totals, database failure, read-only lookup,
real reconciliation risk updates exactly once, approximate fallback and restart
artifact exclusion. The fixture contains synthetic IDs and sanitized historical
prices/quantities; no credentials or raw broker identifiers.

The accounting replay fixture contains all **27 historical positions / 61
orders**. It reproduces gross **$89.819991** and seven partial positions without
mutating its input. This replays accounting only, not a counterfactual strategy,
execution path, expectancy or forward significance result.

The broader organism/state/exits/sizing/replay run passed **208 tests**. It
included 38 focused cases; the extra all-27 historical accounting replay was
then added and the final focused run passed all 39. The required order integrity
and reconciliation files passed **76 collected tests**; the legacy
`test_position_reconciliation.py` at this proposal's base defines no pytest
tests. Its four replacement acceptance tests belong to the separate Monday
operational repair, not this branch. The new database/reconciliation regressions
here exercise this correction directly.

The full artifact pack exited 0: **168 core tests, 28 replay tests and 20
semantic-invariant tests** passed, as did grep assertions and spec-drift checks.
Counts describe separate runs and must not be added as unique coverage. The
repository lint ratchet also passes with no new violations. Results are in
`artifacts/`, with supplemental evidence and the independent source-review
record in `artifacts/accounting_proposal/`.

The full pack and reconciliation run denied network access and access to the
original `.env`/brain, denied writes to the original checkout, and used isolated
test storage. Consequently the generated live-process snapshot is explicitly
**unreachable**, while code-default and resolved test-context snapshots are
available. This is not an observation that the running paper service is down
and is not evidence of live configuration coherence. A separately observed
actual runtime snapshot remains an activation requirement.

Initial focused test development failures were fixture errors
(SQLite UUID affinity and fixture argument names), corrected before acceptance.
The unchanged legacy lookup helpers retain two pre-existing Ruff BLE001
warnings; the new helper/test code adds no Ruff findings.

Activation, merge, historical migration, and a real broker order-flow acceptance
are outside this proposal's completed scope.
