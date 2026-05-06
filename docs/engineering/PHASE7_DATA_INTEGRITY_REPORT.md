# Phase 7.7 Data Integrity And Persistence Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`
HEAD reviewed: `f102972dd7feb81861fd40cfce3fd282d087e30a`

## Executive Summary

The paper runtime is safe to keep collecting evidence: broker positions are flat,
the scheduler reconciliation loop reports zero open broker orders and zero
discrepancies, the audit-log hash chain validates, migrations are at head, and
the brain manifest reconciles with the current CSV PnL.

The data warehouse is not yet research-grade. The most important finding is
that `realized_trades` contains duplicate realized rows and no uniqueness
constraint that would prevent re-insertion of the same realized lot/close-order
relationship. The strategy health endpoint is therefore right to expose
strategy-only CSV attribution separately from DB accounting tables.

Do not run a mutating cleanup immediately before market open. The right next
step is an explicit P7.7 remediation PR: snapshot DB, build an idempotent
dedupe/backfill plan, add constraints/tests where the schema can support them,
and only then apply cleanup.

## Read-Only Evidence

| Surface | Evidence | Status |
|---------|----------|--------|
| Container/runtime gate | Authenticated Phase 7 checkpoint: 14 pass, 0 warn, 0 fail. | PASS |
| Audit log chain | `/api/v1/audit/chain-detail`: `all_valid=True`, `rows=990`; DB columns are `id,ts,actor,action,entity,entity_id,payload,hash_chain`. | PASS |
| Migration head | `alembic_version=20260503_000003`. | PASS |
| Broker/local exposure | DB positions with `qty <> 0`: `0`; startup reconciliation logs report Alpaca `position_count=0` and `Open: 0, Closed: 728, Discrepancies: 0`. | PASS |
| Brain manifest | `generation=182`, `total_trades=520`, `cumulative_pnl=-674.29`, `saved_at=2026-05-06T07:45:46.533469+00:00`, `ml_is_trained=true`. | PASS |
| Trade history CSV | `520` data rows; all-record CSV PnL `-674.285856`; strategy-only rows `513`; strategy-only PnL `-810.535856`; reconciliation artifact rows `7`. | PASS |
| Strategy health endpoint | `n_trades=513`, `total_pnl=-810.5359`, `win_rate=0.3314`, `sharpe_ratio_per_trade=-1.4279`, `is_profitable=false`, `excluded_reconciliation_artifacts=7`. | PASS, negative edge |
| Phase 5 telemetry | `candidate_filter_shadow_telemetry.jsonl`: `62` rows, last event May 5 market session. | PASS |
| Phase 6 telemetry | `strategy_evidence_events.jsonl` absent. Expected until the next candidate after final telemetry-enabled rebuild writes an event. | WATCH |
| Backups | `organism_brain/backups`: `5` snapshots, bounded as intended, latest at `2026-05-06T07:45:46`. | PASS |
| Corrupt-head snapshots | `5` preserved dirs, total about `9M`; two new May 6 `00:40` dirs contain the same valid gen-182 manifest saved at `07:37:40`. | WATCH |

## Findings

### High: `realized_trades` Is Not An Authoritative Research Ledger

Evidence:

- `realized_trades` count: `926`.
- `organism_brain/trade_history.csv` data rows: `520`.
- `realized_trades` PnL sum: `-963.524385`.
- CSV all-record PnL: `-674.285856`.
- CSV strategy-only PnL: `-810.535856`.
- Duplicate realized groups by `(open_order_id, close_order_id, lot_id)`: `19`.
- Extra duplicate rows in those groups: `28`.
- `realized_trades` has only a primary-key uniqueness constraint; no uniqueness
  or idempotency guard exists for realized lot/close-order relationships.

Interpretation: the DB accounting ledger is useful as operational evidence, but
not clean enough for strategy research, KPI reporting, or promotion decisions
until duplicates are removed and insertion becomes idempotent.

Recommendation: create a dedicated P7.7 remediation PR with a DB snapshot,
read-only duplicate report, deterministic dedupe/backfill script, tests around
`backend/services/lot_tracker_service.py`, and a migration/constraint only after
the correct uniqueness key is proven. Do not guess a unique key around partial
fills without replay fixtures.

### Medium: Stale Accepted Orders And Failed Outbox Rows Remain From April 8

Evidence:

- `orders` status counts: `accepted=4`, `cancelled=5`, `expired=1`,
  `filled=1422`.
- The four `accepted` rows are XLE sell orders from `2026-04-08T13:33-13:35Z`,
  each with `filled_qty=0` and `broker_order_id=NULL`.
- Matching `outbox_events` rows are `failed`, each with 5 attempts and Alpaca
  403 errors such as potential wash trade / insufficient quantity.
- Broker reconciliation currently reports zero open orders and zero
  discrepancies.

Interpretation: this does not appear to be live exposure, but it is stale local
state. Dashboards or reports that look only at `orders.status='accepted'` can
overstate open order risk.

Recommendation: add a read-only stale-order classifier first, then a controlled
cleanup/backfill that marks broker-rejected failed submissions terminal without
deleting history.

### Medium: Corrupt-Head Snapshot Growth Is Bounded But Still Noisy

Evidence:

- Current `corrupt_head_*` dirs: `5`, about `1.8M` each.
- Two new dirs appeared around the May 6 pre-market rebuild window:
  `corrupt_head_20260506_004045_759831` and
  `corrupt_head_20260506_004046_346622`.
- Their manifests are valid gen-182 snapshots, not obviously corrupt files.
- Backup retention is bounded at 5 snapshots; corrupt-head retention is
  preserved but not obviously bounded by a current operating policy.

Interpretation: the recovery path is preserving forensic state, which is good,
but it is too chatty around rebuild/save races. This is not large today, but it
will become confusing if every deploy creates new forensic directories.

Recommendation: add explicit logging/reporting for why a corrupt-head capture
was triggered and a bounded retention policy for forensic dirs after they are
known safe.

### Low: `order_events` Is Empty Despite Active Orders/Executions

Evidence:

- `order_events` count: `0`.
- `orders`: `1432` rows.
- `executions`: `1473` rows.
- `outbox_events`: `917` rows.

Interpretation: either `order_events` is intentionally unused legacy schema, or
event sourcing is incomplete. It should not be presented as part of the
authoritative order audit trail unless populated.

Recommendation: document as legacy/unused or wire it deliberately in a future
order-event audit slice.

## Clean Areas

- No nonzero DB positions.
- No duplicate non-null `broker_order_id` values.
- No orphan `executions`, `position_lots`, or `realized_trades` rows against
  their declared foreign keys.
- Audit log hash chain validates through the authenticated API.
- Migration tree is readable and at the expected head.
- Backup directory is bounded at 5 snapshots.
- Strategy health excludes the 7 reconciliation artifacts from strategy-only
  expectancy.

## Recommended P7.7 Remediation Queue

1. Take a DB snapshot before any mutation.
2. Add a read-only data-integrity script that emits stale orders, failed outbox,
   duplicate realized groups, PnL deltas, backup/corrupt-head counts, and
   telemetry file state as JSON.
3. Add tests proving duplicate realized insertion is prevented or idempotently
   skipped in the lot-closing/backfill path.
4. Design the correct uniqueness key for realized trades with partial-fill
   replay coverage; do not blindly unique `(open_order_id, close_order_id,
   lot_id)` until partial close behavior is proven.
5. Build a deterministic dedupe/backfill script that writes a dry-run report
   first and mutates only behind an explicit flag.
6. Mark the four April 8 failed accepted XLE submissions terminal through a
   controlled cleanup, preserving the original order and outbox records.
7. Add bounded retention/reporting for `corrupt_head_*` directories.

## Phase Position

P7.7 should continue before Track B promotion work. The current data is good
enough for paper runtime safety and passive evidence collection, but not good
enough for a personal hedge-fund-style research warehouse without cleanup and
idempotency guards.
