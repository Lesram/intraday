# Phase 7.7 Data Integrity And Persistence Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`
HEAD reviewed before remediation commit: `3d2fa805f3ab6a6a87aa65ebc09e21c8735ee153`

## Executive Summary

The paper runtime is safe to keep collecting evidence: broker positions are flat,
the scheduler reconciliation loop reports zero open broker orders and zero
discrepancies, the audit-log hash chain validates, migrations are at head, and
the brain manifest reconciles with the current CSV PnL.

The data warehouse is closer to research-grade after the safe P7.7 remediation,
but it is not finished. Exact duplicate `realized_trades` rows were removed,
the stale accepted April 8 failed submissions were marked terminal, and the
strategy health endpoint remains right to expose strategy-only CSV attribution
separately from DB accounting tables.

The remaining accounting risk is narrower and more important: 16 non-exact
duplicate realized-trade relationship groups remain. They may represent partial
fills, repeated close events, or historic insertion drift. They should not be
deleted and should not be constrained until replay fixtures prove the correct
idempotency key.

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

## Remediation Applied

The low-ambiguity cleanup was applied only after a binary PostgreSQL snapshot
and a dry-run report.

| Control | Evidence |
|---------|----------|
| Snapshot | `artifacts/db_snapshots/p7_7_pre_data_integrity_remediation_20260506T143321Z.dump`, SHA-256 `b314c3ae77f32c3bbd32b49cc393a1fb96a4e87cae7c72a9edf9801dddb52000`, size `1.2M`. |
| Script | `scripts/db/phase7_data_integrity_remediation.py`; defaults to dry-run. |
| Apply gate | Requires `--apply --confirm PHASE7_DATA_INTEGRITY_REMEDIATE`. |
| Exact duplicate rule | Deletes only rows with identical non-identity realized-trade fields, keeping the oldest row. |
| Stale order rule | Marks an old `accepted` order `failed` only when `broker_order_id IS NULL`, `filled_qty=0`, and a matching failed outbox row references the order id. |
| Ambiguous groups | Reported only; no mutation. |

Applied deltas:

| Metric | Before | After | Status |
|--------|--------|-------|--------|
| `orders.status='accepted'` | `4` | `0` | PASS |
| Stale accepted failed submissions | `4` | `0` | PASS |
| Exact duplicate realized rows to remove | `5` | `0` | PASS |
| `realized_trades` row count | `926` | `921` | PASS |
| `realized_trades` PnL sum | `-963.524385` | `-959.614385` | PASS |
| DB positions with `qty <> 0` | `0` | `0` | PASS |

Generated evidence:

- `artifacts/phase7/data_integrity_remediation_dry_run.json`
- `artifacts/phase7/data_integrity_remediation_applied.json`
- `artifacts/phase7/data_integrity_remediation_post_apply.json`

## Findings

### High: `realized_trades` Is Not Yet An Authoritative Research Ledger

Status: partially remediated.

Evidence:

- `realized_trades` count before remediation: `926`.
- `realized_trades` count after remediation: `921`.
- `organism_brain/trade_history.csv` data rows: `520`.
- `realized_trades` PnL sum before remediation: `-963.524385`.
- `realized_trades` PnL sum after remediation: `-959.614385`.
- CSV all-record PnL: `-674.285856`.
- CSV strategy-only PnL: `-810.535856`.
- Relation duplicate groups by `(open_order_id, close_order_id, lot_id)` before
  remediation: `19`.
- Relation duplicate groups after remediation: `16`, all non-exact and left
  untouched.
- Exact duplicate extra realized rows before remediation: `5`.
- Exact duplicate extra realized rows after remediation: `0`.
- `realized_trades` has only a primary-key uniqueness constraint; no uniqueness
  or idempotency guard exists for realized lot/close-order relationships.

Interpretation: the DB accounting ledger is cleaner, but still not clean enough
for strategy research, KPI reporting, or promotion decisions until the remaining
non-exact duplicate groups are explained and future insertion becomes
idempotent.

Recommendation: run a second accounting slice around
`backend/services/lot_tracker_service.py` with partial-fill replay fixtures and
then add the narrowest proven idempotency guard. Do not guess a unique key around
partial fills without replay evidence.

### Medium: Stale Accepted Orders And Failed Outbox Rows From April 8

Status: remediated for the low-ambiguity rows.

Evidence:

- `orders` status counts before remediation: `accepted=4`, `cancelled=5`,
  `expired=1`, `filled=1422`.
- `orders` status counts after remediation: `cancelled=5`, `expired=1`,
  `failed=4`, `filled=1422`.
- The four remediated rows were XLE sell orders from
  `2026-04-08T13:33-13:35Z`, each with `filled_qty=0` and
  `broker_order_id=NULL`.
- Matching `outbox_events` rows are `failed`, each with 5 attempts and Alpaca
  403 errors such as potential wash trade / insufficient quantity.
- Broker reconciliation currently reports zero open orders and zero
  discrepancies.

Interpretation: this did not appear to be live exposure, but stale local state
could overstate open order risk. The four safe cases are now terminal while
preserving the original outbox failure evidence.

Recommendation: keep the stale-order classifier as a reusable audit tool and add
a prevention/gate check so old accepted rows with failed broker submission
evidence cannot silently accumulate again.

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

1. Add the remediation script to regular audit gates so exact duplicates and
   stale failed submissions are visible before reports are trusted.
2. Add tests proving duplicate realized insertion is prevented or idempotently
   skipped in the lot-closing/backfill path.
3. Design the correct uniqueness key for realized trades with partial-fill
   replay coverage; do not blindly unique `(open_order_id, close_order_id,
   lot_id)` until partial close behavior is proven.
4. Add bounded retention/reporting for `corrupt_head_*` directories.
5. Document whether `order_events` is legacy schema or wire it deliberately in a
   future order-event audit slice.

## Phase Position

P7.7 should continue before Track B promotion work. The current data is good
enough for paper runtime safety and passive evidence collection, but not good
enough for a personal hedge-fund-style research warehouse without cleanup and
idempotency guards.
