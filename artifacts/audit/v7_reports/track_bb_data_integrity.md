# Track BB v7 — Data Integrity & Invariants Audit

Repo: `/Users/marselkei/VS/intra`
Branch: `rc-1.5-curated` @ `d44eace`
Database: `trading_platform_db_paper` / `algotrading` / `trading`
Mode: read-only (`SELECT` queries; no DML)
Date: 2026-05-02

---

## TL;DR

The DB schema is permissive: orders, executions, audit_logs, outbox_events
have **no business-rule CHECK constraints** (no `qty>0`, no status enum, no
side enum). The most important production tables that exist precisely so
the platform can be reconstructed forensically — `audit_logs`,
`executions`, `order_events`, `realized_trades`, `position_lots`,
`risk_violations`, `emergency_stops`, `daily_ledger` — are **completely
empty in the live paper deployment**, while `orders` has 1,369 rows and
`outbox_events` has 1,398 rows. The lot-tracking, audit-trail, and
realized-trade ledger are wired into Python classes but **not invoked from
any code path that runs in production**. High-blast events (drawdown-kill,
governance halt, risk breach) fire `send_alert()` to Slack but write
nothing to `audit_logs` — they are unqueryable post-incident. The brain
manifest's full save (`save()`) is atomic via `.tmp_save` → swap, but the
parallel `save_essential_state()` path mutates files in place with no
all-or-nothing guarantee. **Bugs found: 11.**

---

## 1. Database constraint inventory

### 1.1 CHECK constraint matrix (Table × Constraint × ORM × DB × Verdict)

Source of truth:
- ORM declarations in `backend/infra/schemas.py`
- DB constraints from `pg_constraint WHERE contype='c'` in `algotrading`

| Table | Business rule | ORM declares | DB has | Verdict |
|---|---|---|---|---|
| `orders` | `qty > 0` | NO | NO | **BUG-1** missing |
| `orders` | `filled_qty >= 0` | NO | NO | **BUG-1** missing |
| `orders` | `filled_qty <= qty` | NO | NO | **BUG-1** missing |
| `orders` | `side IN ('buy','sell')` | NO | NO | **BUG-2** missing — column is `String(10)` with no enum/check |
| `orders` | `status IN (…fixed set…)` | NO | NO | **BUG-2** missing — `status` is `String(20)` and 14+ distinct values are used in code (`accepted`, `submitted`, `submitting`, `pending`, `pending_new`, `pending_cancel`, `pending_replace`, `new`, `partially_filled`, `filled`, `cancelled`, `rejected`, `expired`, `deferred`, `replaced`) |
| `orders` | `tif IN ('day','gtc','ioc','fok')` | NO | NO | **BUG-2** missing |
| `orders` | `order_type IN (…)` | NO | NO | **BUG-2** missing |
| `orders` | `client_idempotency_key UNIQUE` | YES | YES (`ix_orders_client_idempotency_key`) | OK |
| `executions` | `fill_qty > 0` | NO | NO | **BUG-3** missing |
| `executions` | `fill_price >= 0` | NO | NO | **BUG-3** missing |
| `position_lots` | `qty > 0` | YES | YES (`ck_position_lots_chk_position_lots_qty`) | OK |
| `position_lots` | `remaining_qty >= 0` | YES | YES (`ck_position_lots_chk_position_lots_remaining_qty`) | OK |
| `position_lots` | `remaining_qty <= qty` | NO | NO | **BUG-3** missing — invariant violated would silently corrupt lot state |
| `position_lots` | `status IN ('open','closed')` | NO (comment only) | NO | **BUG-2** missing |
| `realized_trades` | `qty > 0` | YES | YES | OK |
| `realized_trades` | `realized_pnl_percent` finite | NO | NO | acceptable |
| `outbox_events` | `attempts >= 0` | NO | NO | **BUG-3** missing |
| `outbox_events` | `status` enum | YES (PG enum `outbox_status`) | YES | OK |
| `outbox_events` | `next_attempt_at` server default | YES (Python `_utcnow_aware`) | NO | **BUG-4** Python-only default — raw INSERTs would NULL-violate |
| `outbox_events` | `attempts` server default `0` | YES (Python `default=0`) | NO | **BUG-4** Python-only default |
| `outbox_events` | `status` server default `pending` | YES (Python `default="pending"`) | NO | **BUG-4** Python-only default |
| `audit_logs` | `action IN (AuditAction enum)` | NO | NO | **BUG-2** missing — actor/action/entity are free-text |
| `audit_logs` | `hash_chain` UNIQUE (chain integrity) | NO | NO | **BUG-5** missing — tamper-detection chain is not DB-enforced |
| `positions` | `qty != 0` (else delete row) | NO | NO | acceptable |
| `signals` | `confidence BETWEEN 0 AND 1` | NO (DECIMAL(5,4) only) | NO | weak — column type allows 9.9999 |
| `risk_metrics` | `status IN (…)` | YES | YES | OK |
| `risk_violations` | `severity IN (…)` | YES | YES | OK |
| `risk_limits` | `warning < critical` | YES | YES | OK |
| `emergency_stops` | `status IN ('active','resolved')` | YES | YES | OK |
| `backtests` | `status IN (…)` + dates + capital | YES | YES | OK |
| `tick_telemetry` | `tick_number > 0` | NO | NO | acceptable |

### 1.2 FOREIGN KEY drift

| Table | FK | ORM `ondelete` | DB `ON DELETE` | Verdict |
|---|---|---|---|---|
| `executions.order_id` | → `orders.id` | CASCADE | CASCADE | OK |
| `position_lots.order_id` | → `orders.id` | CASCADE | CASCADE | OK |
| `realized_trades.open_order_id` | → `orders.id` | CASCADE | CASCADE | OK |
| `realized_trades.close_order_id` | → `orders.id` | CASCADE | CASCADE | OK |
| `realized_trades.lot_id` | → `position_lots.id` | CASCADE | CASCADE | OK |
| `order_events.order_id` | → `orders.id` | **CASCADE** (ORM line 191) | **NONE** | **BUG-6 ORM/DB drift** — migration `ec197100938a` created the FK without `ondelete='CASCADE'` (line 41) but `schemas.py` line 191 declares `ondelete="CASCADE"`. Deleting an order today would leave dangling `order_events` rows. |
| `position_lots.user_id` | (no FK) | none (V4 N-H-1: dropped FK because DB type is varchar) | none | acceptable but documented |
| `realized_trades.user_id` | (no FK) | none | none | acceptable but documented |
| `positions.symbol` | (no FK to user/account) | none | none | acceptable (single-account assumption) |
| `model_monitoring_snapshots.model_id` | → `model_registry.id` | SET NULL | SET NULL | OK |
| `model_lifecycle_events.model_id` | → `model_registry.id` | SET NULL | SET NULL | OK |
| `risk_*.user_id` | → `users.id` | CASCADE | CASCADE | OK |

### 1.3 NOT NULL drift

Spot checks (for the safety-critical tables) confirmed ORM `nullable=False` matches DB `NOT NULL` in `orders`, `position_lots`, `realized_trades`, `executions`, `outbox_events`, `audit_logs`. **Exception: `users.created_at` and `users.updated_at`** are declared `timezone=False` (naive timestamps) while the rest of the schema is `timezone=True`; documented internally as N-M-1 (planned migration). Not a Track-BB priority but flagged.

---

## 2. State machine invariants

### 2.1 `orders.status`

**Vocabulary used in code** (grep across `backend/services`, `backend/infra`, `backend/integrations`):
```
accepted, submitted, submitting, pending, pending_new, pending_cancel,
pending_replace, new, partially_filled, filled, cancelled, rejected,
expired, deferred, replaced, shadow
```
Plus inline literals like `"shadow"` returned from `outbox_worker._process_order_submitted` when execution mode is shadow.

**Currently in DB** (1,369 rows): `filled` (1,359), `cancelled` (5), `accepted` (4), `expired` (1).

**Intended canonical lifecycle** (deduced from `OrdersRepo.create` + `attach_broker_result` + alpaca_stream `INTERNAL_STATUS_MAP`):

```
                            ┌────────────────────────┐
                            │  insert via            │
                            │  OrdersRepo.upsert_*   │ default = 'accepted'
                            └────────┬───────────────┘
                                     │
                                     ▼
                              accepted ───────────► rejected (broker reject)
                                  │                      ▲
                                  ▼                      │
                            submitted ─────► pending_new ┘
                                  │                ▲
                                  ▼                │ (alpaca trade_update mapping)
                            new (broker)
                                  │
                                  ▼
                          partially_filled ──► filled
                                  │                │
                                  ▼                ▼
                              cancelled        expired
                                  │
                                  ▼
                          pending_cancel / pending_replace (transient)
```

**State transition enforcement audit**:

| Code path | Sets status to | Pre-check | DB-enforced? |
|---|---|---|---|
| `OrdersRepo.upsert_by_idempotency` | `accepted` (default) | none | NO |
| `outbox_worker._update_order_status` | `submitted`/`accepted`/`filled` | none | NO |
| `alpaca_stream._update_order_from_broker_event` | mapped from broker | none | NO |
| `risk_manager._cancel_order` | `cancelled` | filters by `status IN ('pending','new','partially_filled')` then sets `cancelled` (`backend/services/risk_manager.py:705`) | NO |
| `order_service.cancel_order_with_replacement` | `cancelled` then create new | per-order async lock (`_cancel_locks`) | NO |

**Bypass risk**: Any code that does `order.status = "..."` runs without a precondition. There is no DB CHECK or trigger to reject `status='banana'`. The `String(20)` column accepts any 20-char string.

**Verdict: BUG-2** — state machine is app-enforced only, with vocabulary spread across at least 8 modules. A typo or buggy mapping silently corrupts state.

### 2.2 `position_lots.status`

Vocabulary: `open` → `closed`. The `String(20)` column has no CHECK. `LotTracker.close_lots_fifo` is the only writer; it sets `closed` after `remaining_qty=0` (`backend/services/lot_tracker_service.py:113`). Reverse transition `closed → open` is structurally impossible because the FIFO query filters `status='open' AND remaining_qty > 0`, but if any other code path (or manual SQL edit) flipped status, nothing would object. Currently `position_lots` has 0 rows, so the invariant is currently vacuous.

### 2.3 `outbox_events.status`

Vocabulary enforced at DB via PG enum `outbox_status` = `pending|sent|failed`. **Lease semantics are the documented gotcha**:

- `OutboxRepo.claim_batch` does `SELECT … WHERE status='pending' AND next_attempt_at <= now() FOR UPDATE SKIP LOCKED`, then bumps `next_attempt_at = now + 5min` to lease the row across transactions (`backend/infra/outbox.py:181-200`). **It does NOT change `status` to `claimed` or `processing`**.
- Result: between worker A claiming and worker A's `_mark_event_succeeded`, the row is `status='pending'` but `next_attempt_at` is in the future. The lease is the only thing preventing re-claim. If the lease has been bumped `_CLAIM_LEASE_SECONDS` (5 min default) and worker A is still processing (e.g. broker call hung), worker B can claim and re-submit — duplicate broker order. Mitigated by `client_order_id` forwarding to Alpaca (`backend/integrations/alpaca_outbox.py:227`), which Alpaca dedupes on. So the broker-side dedupe is the safety net, not the DB.
- **BUG-7** Outbox `status` does not change to `claimed`/`processing` during inflight broker call. Concurrency safety relies on (a) lease duration ≥ broker timeout, and (b) broker-side `client_order_id` dedupe. Both are external invariants the DB does not enforce.

Distribution today: 1,393 sent, 5 failed; no `pending` rows backed up.

---

## 3. Position vs lot consistency

There are three views of "open positions":

1. **Broker positions** (Alpaca account API). Authoritative.
2. **Local DB `positions` table**. Currently 0 rows (the table is unused; live engine doesn't update it).
3. **In-memory `LiveEngine.open_positions`**. Authoritative for trading decisions; persisted to brain.

`position_lots` is a fourth view (lot-level cost basis) but has 0 rows in production — `LotTracker.create_lot()` is only called from `backend/integrations/alpaca_stream_production.py`, and the lifespan startup wires `backend/integrations/alpaca_stream.py` (the older client) instead. **BUG-8** — `LotTracker` is dead code in the live deployment despite being the design's source of truth for cost basis and FIFO.

**Reconciliation**: `scheduled_reconciliation.run_scheduled_reconciliation()` is started in lifespan and runs every N minutes. It calls `PositionReconciliationService.get_reconciliation_summary()`, which compares filled DB orders to broker positions. Result: discrepancies are **only logged** (`backend/services/scheduled_reconciliation.py:75-86`), not persisted to `audit_logs`, `risk_violations`, or any DB table. **BUG-9** — drift detected by the reconciliation job is not queryable later; it lives only in container stdout logs which rotate.

---

## 4. Audit trail completeness

| High-blast event | Code path | Audit row written? | Alert sent? | Verdict |
|---|---|---|---|---|
| Order submitted | `order_service.submit_symbol_order` | NO | NO | **BUG-10** orders table holds the row but no `audit_logs` |
| Order filled | `alpaca_stream._update_order_from_broker_event` | NO | NO | **BUG-10** |
| Order cancelled | `risk_manager._cancel_order`, `order_service.cancel_order` | NO | NO | **BUG-10** |
| Position opened/closed | LiveEngine in-memory only | NO | NO | **BUG-10** (positions table unused, lots empty) |
| Drawdown-kill | `live_engine.py:1995-2044` | NO | YES (`send_alert` Slack/webhook, `live_engine.py:2018-2039`) | **BUG-10** alert is real-time only; no DB row for forensics |
| Governance halt | `governance.halt_trading()` (`live_engine.py:1953`) | NO (only state in `governance_state.json`) | YES | **BUG-10** |
| Daily max-loss | `live_engine.py:1953-1970` | NO | YES | **BUG-10** |
| ML model promotion | `backend/organism/promotion.py` | YES (writes `model_lifecycle_events`) | depends | OK |
| ML model rollback | `backend/organism/promotion.py` | YES | depends | OK |
| Configuration change (env var mid-run) | none | NO | NO | gap |
| Risk-limit breach | `risk_manager` may raise but doesn't insert into `risk_violations` | NO | depends | gap (table unused: 0 rows) |

**Concrete production evidence**:
- `audit_logs` rows: **0** (empty since DB creation despite 1,369 orders)
- `executions` rows: **0**
- `order_events` rows: **0**
- `realized_trades` rows: **0**
- `position_lots` rows: **0**
- `risk_violations` rows: **0**
- `emergency_stops` rows: **0**
- `daily_ledger` rows: **0**
- `model_lifecycle_events` rows: 455 — but `MAX(created_at) = 2026-02-24` (last write 2 months ago). Lifecycle telemetry stopped writing.

`AuditService.log()` is implemented and well-designed (SHA-256 hash chain, `payload`, `hash_chain` column) but is **only invoked by `backend/api/routes/audit.py`** (read-only viewer endpoints). Zero call sites in `services/`, `organism/`, or `infra/` write audit rows.

**Verdict: BUG-10** is the largest finding by volume. The platform has invested in compliance-grade audit infrastructure and chosen not to use it.

---

## 5. Compensating transactions

| Multi-step process | Failure scenario | Compensation? | Verdict |
|---|---|---|---|
| Order submission (orders.upsert + outbox.add_order_submit_event) | DB insert succeeds, outbox insert fails | Same transaction (single `session.commit`) | OK — atomic |
| Outbox dispatch (broker call + status update + mark_sent) | Broker accepts; status update fails | `_update_order_status` re-raises (`outbox_worker.py:660`); `_mark_event_succeeded` skipped → outbox stays `pending` → next claim re-submits → Alpaca dedupes via `client_order_id` | external safety net |
| Outbox dispatch | Status update commits; `_mark_event_succeeded` fails | DB has `status=submitted`/`filled` but outbox still `pending` → next claim → re-submits broker → Alpaca dedupes | external safety net |
| Lot close (`LotTracker.close_lots_fifo`) | position_lots updated; realized_trades insert fails | Single transaction; `with_for_update()` on lot rows; commit-or-rollback atomic | OK |
| Brain full save (`BrainPersistence.save`) | Crash mid-write | tmp_save dir + atomic swap (`brain_persistence.py:350-411`); `.brain_old` retained for rollback | OK |
| Brain `save_essential_state` (lighter path) | Crash between `_save_trade_history` and `_save_manifest` | Each file is per-file atomic (`.tmp` rename) but the **set is not transactional**. Trade history can grow, learning_state.json's `cumulative_pnl` can update, but manifest.json's `total_trades` may NOT advance. | **BUG-11** |
| Drawdown-kill | Halt state set; alert dispatch fails | Halt is in-memory; `_save_brain` later persists `governance_state.json`. Alert failure caught and logged (`live_engine.py:2040-2044`). | acceptable but no audit row |
| Position reconciliation discovers drift | DB orders disagree with broker positions | No compensation written; discrepancy is logged only | gap (BUG-9 already counted) |

**BUG-11**: `save_essential_state` writes 7+ files directly into `brain_dir`. If the process is killed between file writes, the on-disk view contains a half-updated brain (e.g. `trade_history.csv` advanced but `manifest.json.total_trades` stale). Wave-17d's reconciliation log catches the cumulative_pnl asymmetry, but other manifest fields (`generation`, `total_runs`, `ml_is_trained`) have no reconciliation. The full `save()` path has atomic-swap; `save_essential_state` does not.

---

## 6. Referential integrity

Live database checks (read-only):

```sql
SELECT count(*) FROM position_lots WHERE order_id NOT IN (SELECT id FROM orders);  -- 0
SELECT count(*) FROM realized_trades WHERE open_order_id NOT IN (SELECT id FROM orders)
                                       OR close_order_id NOT IN (SELECT id FROM orders)
                                       OR lot_id NOT IN (SELECT id FROM position_lots);  -- 0
```

No orphans. (Tables are empty so vacuously true.) `position_lots.user_id` and `realized_trades.user_id` were intentionally dropped from FK enforcement in V4 N-H-1 — defensible because column type is `varchar(100)` (username) while `users.id` is `Integer`. Documented in `schemas.py` lines 791-797 and 864.

The only structural drift is **BUG-6** (`order_events.order_id` FK lacks `ON DELETE CASCADE` at DB despite ORM declaring it).

---

## 7. Idempotency keys

**Format observed in production** (sampled from `orders`):
```
organism[_exit]_<SYMBOL>_<YYYYMMDD>_<8hex>_t<tick>
e.g. organism_AAPL_20260306_901b11b0_t694
     organism_exit_CRM_20260501_9e75d116_t37182
```
The 8-hex appears to be a per-session hash. The `t<tick>` is monotonically increasing within a session.

**Collision audit**:
```sql
SELECT count(*) AS dup_groups
FROM (SELECT client_idempotency_key, count(*) c FROM orders GROUP BY 1 HAVING count(*) > 1) t;
-- result: 0
```
No collisions across 1,369 orders. The DB UNIQUE on `client_idempotency_key` would have rejected duplicates anyway.

**Outbox payload-level idempotency**:
```sql
SELECT count(*) FROM (SELECT (payload->>'idempotency_key') AS k, count(*) c
                     FROM outbox_events WHERE payload ? 'idempotency_key'
                     GROUP BY 1 HAVING count(*) > 1) t;
-- result: 0
```
No outbox duplicates. The outbox table has **no DB-level UNIQUE on `(topic, payload->>'idempotency_key')`** — collision protection is by convention only (the order_service caches by key in-process and the orders table UNIQUE prevents duplicate orders). For non-order topics that don't flow through `orders.client_idempotency_key`, there would be no protection. Currently 100% of outbox rows are `topic='order.submitted'` so this is a latent risk only.

**Verdict**: idempotency works in practice. No collisions observed; format collision-resistant (session hash + tick). Caller `order_service` enforces UNIQUE before submitting to outbox.

---

## 8. Concurrency invariants

**Locks identified**:
- `LiveEngine._tick_lock` (`live_engine.py:692`) — outermost; serializes ticks.
- `OrderService._symbol_locks_lock` (`order_service.py:553`) — guards the `_symbol_locks` dict.
- `OrderService._symbol_locks[symbol]` — per-symbol entry lock.
- `OrderService._cancel_locks_lock` (`order_service.py:555`) — guards `_cancel_locks` dict.
- `OrderService._cancel_locks[order_id]` — per-order cancel lock.
- DB-level: `OutboxRepo.claim_batch` uses `FOR UPDATE SKIP LOCKED`; `LotTracker.close_lots_fifo` uses `with_for_update()` on lot rows (`lot_tracker_service.py:129`).

**Lock-ordering risk audit**:
- `_symbol_locks_lock` and `_cancel_locks_lock` are short-lived dict guards inside `submit_symbol_order` / `cancel_order` respectively. They are **never held simultaneously** — different code paths. No inversion possible.
- `_tick_lock` is acquired in `LiveEngine.step` and held while calling `_order_service.submit_symbol_order` / `cancel_order` which then take `_symbol_locks_lock`. Order: tick → symbol-lock-dict-lock → per-symbol lock. Consistent across call sites.
- `with_for_update()` in lot tracker is innermost — only acquired inside `LotTracker.close_lots_fifo` which is currently never invoked from the live path (`alpaca_stream_production` path is dormant).

**Nested transactions**: `grep "begin_nested\|begin(" backend/services backend/infra` returned no SQLAlchemy savepoints. The platform uses simple commit-or-rollback semantics, with one exception: `outbox_worker._mark_event_succeeded` opens its own session separate from the broker-call transaction, which is the intended split (so a broker-call rollback doesn't lose the lease). This was discussed in §5 above.

**Verdict**: no lock-ordering bugs found.

---

## 9. Time-series invariants

**`trade_history.csv`**:
- 499 rows (498 trades + header). `manifest.total_trades = 498`. Consistent.
- Per-row pnl now stored at 6 decimals (V5 B-T-2 fix) so `round(sum(CSV.pnl), 2)` matches `learning_state.cumulative_pnl` exactly.
- Atomic write: `_save_trade_history` writes `.tmp` then `replace()` (`brain_persistence.py:1404-1416`).
- Mutation log: each save replaces the file (not append). Older rows remain identical because they're re-written from in-memory `all_trades`. Immutability depends on in-memory state, which is reloaded from disk at startup. This is "monotonic by convention", not by file-system enforcement.

**`equity_curve.csv`**:
- 37,405 rows + header. **No timestamp column** — just raw `equity` values (`brain_persistence.py:1421-1423`).
- **No cap** observed in `_save_equity_curve` despite the V7 prompt referencing a "wave-14 cap". The MEMORY note may be stale or the cap may live elsewhere; grep shows no `MAX_EQUITY_ROWS` symbol.
- **Not atomic**: written via `df.to_csv(target / "equity_curve.csv", index=False)` directly, no `.tmp` rename. Process crash mid-write → truncated file → load failure on next startup. (Equity curve is not used for trading decisions, only display, so blast radius is minor.)
- "Monotonic per session" cannot be checked because there are no session boundaries persisted.

**`manifest.json.saved_at`**:
- Computed via `datetime.now(UTC)` (with `_now_fn` indirection per Wave-20b X-3). `_write_manifest_guarded` is the single writer. No multi-writer race because both call paths funnel through the guarded helper.

**Bar timestamps per symbol**: not persisted in DB; live in pandas frames sourced from `polygon` / `alpaca`. Out of Track-BB scope.

**`tick_telemetry`**: 0 rows in DB (V4 N-C-2 fixed the ImportError that swallowed every write; needs deploy). No invariant to check.

---

## 10. Brain manifest invariants

`manifest.json` schema (live): `{brain_format_version, saved_at, total_runs, generation, total_trades, cumulative_pnl, best_sharpe, ml_is_trained, feature_count}`.

| Manifest field | On-disk source of truth | Divergence path | Reconciled? |
|---|---|---|---|
| `generation` | `learning_state.json.generation` | `_save_manifest` reads it from `learner.state.generation`; `_save_learning_state` writes it. Both run inside `save()` / `save_essential_state` but in different files. Crash between writes → drift. | NO automatic reconcile |
| `total_runs` | n/a (manifest is canonical; incremented at session start) | source-of-truth lives in manifest only | acceptable |
| `total_trades` | `len(trade_history.csv) - 1` | `_save_trade_history` writes CSV; `_write_manifest_guarded` reads `learner.state.total_trades`. In `save_essential_state`, both run sequentially — crash between → CSV advanced, manifest stale | wave-17d reconcile-on-load only fixes `cumulative_pnl`; `total_trades` is checked in `_check_trained_overwrite_guard` (refuses fresh-overwrite-trained) but no reconciliation if both are non-zero and disagree |
| `cumulative_pnl` | `sum(trade_history.csv.pnl)` | wave-17d already catches divergence at load time and logs warning | Reconciled |
| `best_sharpe` | `learning_state.json.best_sharpe` | both written from in-memory state; can drift in `save_essential_state` if crash | NO |
| `ml_is_trained` | `signal_gen._is_trained` (in-memory) + presence of `ml_classifier.joblib` | `_check_trained_overwrite_guard` blocks overwrites of trained-with-untrained; but `ml_is_trained=True` and missing `ml_classifier.joblib` is possible if `save_essential_state` ran (it skips ML model writes) — V4 R-F-5 partially addressed this for the ensemble | partially reconciled |
| `feature_count` | `len(signal_gen._feature_cols)` | written by manifest; redundant with `ml_state.json.feature_cols` | low-blast |
| `saved_at` | wall-clock `_now_fn()` | should be monotonic across restarts because `now()` only goes forward | OK |

Current values look healthy: `total_trades=498`, `cumulative_pnl=-634.92` (matches `sum(trade_history.pnl) ≈ -634.92` after V5 B-T-2 6-decimal fix).

**Risk concentration**: `save_essential_state` is the more frequent save path (executed during walk-forward gates) and it lacks the directory-level atomic swap that `save()` has. This is BUG-11 above — re-emphasised here from the manifest perspective.

---

## Bugs Found: 11

| # | Severity | Bug |
|---|---|---|
| 1 | HIGH | `orders` table has no CHECK on `qty > 0` / `filled_qty >= 0` / `filled_qty <= qty`. A buggy code path or manual SQL edit could persist `qty=0`, `qty<0`, or `filled_qty > qty`, silently corrupting position math. |
| 2 | HIGH | No CHECK constraints on `orders.status`, `orders.side`, `orders.tif`, `orders.order_type`, `position_lots.status`, or `audit_logs.action`. State machine is enforced only in app code (which uses 14+ status values across 8 modules); typos/drift would not be rejected by DB. |
| 3 | MEDIUM | Missing CHECKs on `executions.fill_qty > 0`, `executions.fill_price >= 0`, `position_lots.remaining_qty <= qty`, `outbox_events.attempts >= 0`. |
| 4 | LOW | `outbox_events.status`, `outbox_events.attempts`, `outbox_events.next_attempt_at` declare Python `default=…` but **no DB `server_default`**. Raw SQL INSERTs that omit these columns will fail with NOT NULL violation. Cosmetic since ORM always sets them. |
| 5 | MEDIUM | `audit_logs.hash_chain` is meant to be tamper-detect chain (SHA-256 of prev_hash) but has **no DB UNIQUE constraint**. A duplicate hash would not be caught structurally; only a chain re-walk would detect it. The chain is also unused in production (audit_logs is empty). |
| 6 | HIGH | **ORM/DB drift**: `order_events.order_id` FK declared `ondelete="CASCADE"` in `schemas.py:191` but the actual DB FK has no cascade (migration `ec197100938a` line 41 omits it). Deleting an order would orphan order_events rows. |
| 7 | MEDIUM | Outbox claim does not transition `status` to `claimed`/`processing`. Cross-transaction safety relies on `next_attempt_at` lease + broker-side `client_order_id` dedupe. Worker outage longer than the 5-min lease creates a re-submit window; without Alpaca's dedupe, this would emit duplicate broker orders. |
| 8 | HIGH | `LotTracker` (the entire `position_lots`/`realized_trades` design) is **dead code in the live deployment**. Lifespan starts `alpaca_stream.py` (legacy), not `alpaca_stream_production.py` (the only caller of `LotTracker.create_lot`). Cost-basis ledger is therefore not maintained: `position_lots` and `realized_trades` are 0 rows despite 1,369 orders flowing through. |
| 9 | HIGH | Position reconciliation (`scheduled_reconciliation.run_scheduled_reconciliation`) detects DB-vs-broker drift but **only logs to stdout** — does not persist to `audit_logs`, `risk_violations`, or any DB table. Drift events are not queryable post-incident. |
| 10 | CRITICAL | **Audit trail is empty.** `AuditService.log()` is implemented with hash-chain tamper detection, but is invoked only by the read-only `/api/routes/audit.py` viewer. Zero writes from order/risk/governance/drawdown paths. Drawdown-kill, governance halt, daily-loss halt, risk-violation, order-submit, order-fill, and order-cancel all lack an audit row. The platform has invested in compliance infrastructure and chosen not to use it. Concretely: `audit_logs` has 0 rows, `risk_violations` has 0 rows, `emergency_stops` has 0 rows, `executions` has 0 rows, `order_events` has 0 rows, `realized_trades` has 0 rows, `daily_ledger` has 0 rows. |
| 11 | MEDIUM | `BrainPersistence.save_essential_state` is **not atomic at the directory level** — files are written directly into `brain_dir` (each per-file atomic via `.tmp`+rename, but the *set* of 7+ files is not). A SIGKILL between `_save_trade_history` and `_write_manifest_guarded` leaves the on-disk brain partially advanced. Wave-17d catches `cumulative_pnl` divergence on load but other fields (`total_trades`, `generation`, `best_sharpe`) have no reconcile. The full `save()` path uses `.tmp_save` + atomic swap and is not affected. |

---

## Summary

The Intra platform's database schema demonstrates a strong design intention — well-modeled tables for orders, lots, realized trades, audit logs with hash chain, risk violations, emergency stops, daily ledgers — but the live paper deployment uses only two of them (`orders` and `outbox_events`), leaving the entire compliance and forensic surface dark. Order-status / side / TIF / order-type are not constrained at the DB level despite the application using 14+ status values across 8 modules; a typo or buggy mapping would silently persist garbage. The `order_events` FK has ORM-vs-DB drift (cascade declared but not enforced). High-blast events — drawdown-kill, governance halt, daily-loss halt, risk-violation, order lifecycle transitions, position reconciliation drift — fire Slack alerts and write to logs, but never insert an audit row, so post-incident forensics are limited to live log retention. The `LotTracker` cost-basis ledger is implemented and tested but its sole caller (`alpaca_stream_production`) is not the one started at boot, so `position_lots` and `realized_trades` remain at 0 rows after 1,369 orders. The brain's full `save()` path is correctly atomic via tmp-dir swap, but the more-frequent `save_essential_state` path mutates files in place with no all-or-nothing guarantee — wave-17d reconciles cumulative_pnl on load but other manifest fields can silently drift. Idempotency works in practice (no collisions observed; `client_idempotency_key` UNIQUE plus broker-side `client_order_id` provides defense-in-depth), and lock-ordering across `_tick_lock` / `_symbol_locks` / `_cancel_locks` / outbox `FOR UPDATE SKIP LOCKED` is sound. Net: the platform is operationally healthy because Alpaca and the FOR-UPDATE-SKIP-LOCKED outbox absorb the gaps, but the compliance and forensic substrate that exists in code is not actually being populated, which becomes a real liability the moment an incident requires "show me what happened at 14:32 UTC" beyond log retention.
