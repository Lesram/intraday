# Track BB3 v9 — Data Integrity Phase 2

- **Run date**: 2026-05-03 (executed 2026-05-02 session, post-EOD)
- **Branch / SHA**: `rc-1.5-curated` @ `0826dad` (work tree). Prompt referenced `db1a3fc`; current HEAD is two commits ahead with audit-only changes.
- **DB**: `trading_platform_db_paper` (Up 3 hours, healthy) / database `algotrading` / user `trading`.
- **Mode**: read-only SELECT against Postgres + read-only file inspection. No mutations.

---

## 0. Method recap

V8 BB2 left 6 dark tables with 0 row counts and flagged the BB-8/BB-10 wiring as conditionally verified. BB3 deepens the audit:

1. FK / UNIQUE / CHECK catalog with delete-rules.
2. Transaction boundary scan (commit/rollback pairing, session lifecycle).
3. Dark-table re-audit with last-write timestamp.
4. Hash-chain integrity at scale.
5. Race-condition replay (concurrent fills).
6. Brain ↔ DB consistency.
7. Migration `downgrade()` availability for the most recent 3 migrations.
8. NULL-leak scan on critical columns.

Sources of truth used: `information_schema`, `pg_indexes`, `alembic_version`, `organism_brain/manifest.json`, `organism_brain/trade_history.csv` (line count), and the `services/audit_service.py` / `services/lot_tracker_service.py` / `integrations/alpaca_stream.py` source.

---

## 1. Constraint catalog (delta vs V8 BB2)

### Foreign keys (20 total) — all delete-rules verified

| Table | FK column | References | ON DELETE | Concern |
|---|---|---|---|---|
| `backtests` | `strategy_id` | `strategies.id` | CASCADE | OK |
| `chart_templates` | `user_id` | `users.id` | CASCADE | OK (user-scoped data) |
| `emergency_stops` | `user_id` | `users.id` | CASCADE | Compliance concern: emergency stop history is wiped if a user is deleted |
| `emergency_stops` | `triggered_by` / `resolved_by` | `users.id` | NO ACTION | OK |
| `executions` | `order_id` | `orders.id` | CASCADE | Compliance concern (see Finding F2) |
| `model_lifecycle_events` | `model_id` | `model_registry.id` | SET NULL | OK |
| `model_monitoring_snapshots` | `model_id` | `model_registry.id` | SET NULL | OK |
| `order_events` | `order_id` | `orders.id` | NO ACTION | OK |
| `position_lots` | `order_id` | `orders.id` | CASCADE | Compliance concern (see F2) |
| `realized_trades` | `lot_id` / `open_order_id` / `close_order_id` | `position_lots.id`, `orders.id` | CASCADE | Compliance concern (see F2) |
| `risk_*` | `user_id` | `users.id` | CASCADE | Compliance concern: risk-violations history wiped on user delete |
| `watchlists`, `watchlist_symbols` | various | various | CASCADE | OK |

**Tables with NO FK at all to `users`**: `orders`, `audit_logs`, `positions`, `signals`, `outbox_events`, `tick_telemetry`, `daily_ledger`. For `orders` this is structural: the column `orders.user_id` is `character varying` (default `'admin'`) and is **completely unrelated to `users.id` (integer)** — there is no referential link possible. See Finding F1.

### UNIQUE constraints / unique indexes

- `orders.client_idempotency_key` is enforced via `ix_orders_client_idempotency_key` (UNIQUE INDEX). Idempotency safety net is intact for all 1,369 orders.
- `orders.broker_order_id` has TWO non-unique indexes (`idx_orders_broker_order_id`, `ix_orders_broker_order_id`). No UNIQUE constraint. In practice the live data has 0 duplicates and 5 NULLs (the cancelled/expired orders that never received broker ack), but the absence of a uniqueness guarantee leaves a race window if the gap-fill reconcile path races with the WS handler. Low risk, worth noting.
- `model_registry (name, version)`, `daily_ledger (account_id, day_utc)`, `risk_limits (user_id, limit_name)`, `users.email`, `users.username`: all properly enforced.

### CHECK constraints (named, application-level)

- `orders`: `ck_orders_status`, `ck_orders_tif`, `ck_orders_order_type`, `ck_orders_side`, `ck_orders_filled_qty_lte_qty`, `ck_orders_filled_qty_nonnegative`, `ck_orders_qty_positive` — strong domain integrity (added 2026-05-03 wave-30 per filename).
- `position_lots`: `chk_position_lots_qty`, `chk_position_lots_remaining_qty`. Good.
- `realized_trades`: `chk_realized_trades_qty`. Good.
- `risk_metrics`, `risk_violations`, `backtests`, `emergency_stops`: status / severity / threshold validators in place.

---

## 2. Transaction boundary audit

Total commit sites: 127 across `backend/`. Spot-checked the highest-traffic paths:

| File | Lines | Wraps with try/except? | Rollback? |
|---|---|---|---|
| `backend/database/connection.py:60-68, 80-83` | session generator | Yes | Yes |
| `backend/infra/db.py:120-129` (`get_db_session`) | session generator | Yes | Yes |
| `backend/integrations/alpaca_stream.py:537, 606` | `_process_trade_update` | Outer `try/except` (line 444 / 689) catches and logs; **no explicit rollback on the outer except** | Inner BB-8 lot block has try/rollback (line 614) |
| `backend/api/routes/watchlists.py:77, 170, 217, 280, 335, 391` | route handlers | No try/except inline | Relies on session-wrapper rollback |
| `backend/api/routes/auth.py:288, 332` | login / register | rollbacks present (2) | Yes |
| `backend/services/audit_service.py:268` | `log()` flushes only; commit deferred to caller's session | N/A | N/A |

Pattern: routes generally rely on the FastAPI dependency `get_db_session` (in `infra/db.py:112-135`) to do `try → yield → commit → except → rollback → finally → close`. That wrapper is correct, so a route that raises after committing once will not double-commit (it'll just get a no-op commit from the wrapper after the route returns). However, **routes that mix `await db.commit()` inline AND raise an exception before returning will have committed partial state** — the wrapper's rollback won't revert the prior commit. Watchlists routes do this pattern repeatedly with no try/except; risk is low because the operations are simple (single insert/update) but the pattern is fragile.

Long-lived sessions across non-DB I/O: `_process_trade_update` (alpaca_stream.py:502-687) holds a session open across an `httpx` call to Alpaca (only in `_gap_fill_after_reconnect`, line 749) and across the `broadcast_order_update` socketio path (line 679). Holding a session through socket I/O is a well-known anti-pattern (DB connection sits idle on the pool). Not a correctness bug but a pool-pressure concern under load.

---

## 3. Dark-table re-audit (BB2-F2 follow-up)

| Table | Rows | Last write | Status |
|---|---|---|---|
| `orders` | 1,369 | 2026-05-01 19:42:07Z | Active (1,359 filled, 5 cancelled, 4 accepted, 1 expired) |
| `outbox_events` | 1,398 | 2026-05-01 19:42:07Z | Active (1,393 sent, 5 failed; all topic `order.submitted`) |
| `audit_logs` | 103 | 2026-05-03 08:04:25Z | Active (login events) |
| `executions` | **0** | — | **Dark** |
| `positions` | **0** | — | **Dark** |
| `position_lots` | **0** | — | **Dark** |
| `realized_trades` | **0** | — | **Dark** |
| `order_events` | **0** | — | **Dark** |
| `risk_violations` | **0** | — | **Dark** |
| `risk_metrics` | **0** | — | **Dark** |
| `risk_limits` | **0** | — | **Dark** |
| `daily_ledger` | **0** | — | **Dark** |
| `signals` | **0** | — | **Dark** |
| `tick_telemetry` | **0** | — | **Dark** |
| `emergency_stops` | **0** | — | **Dark** |
| `strategies` | **0** | — | **Dark** |
| `model_registry` | **0** | — | **Dark** |

**14 of 17 substantive tables are empty.** This is the dominant finding — see F2.

---

## 4. Hash-chain integrity

The `audit_logs` schema uses a single `hash_chain` (text) column rather than the `prev_hash` / `current_hash` pair the prompt assumes. The verification path is `services.audit_service.verify_chain()` which walks `ORDER BY ts ASC`, reconstructs each record's expected hash via `_compute_hash(prev_hash, ts, action, entity, entity_id, actor, payload)`, and compares to the stored value.

Schema-level checks executed (read-only):

- `count(*) = 103`, `count(hash_chain) = 103` — **0 NULL hashes**.
- `count(DISTINCT hash_chain) = 103` — **all hashes unique** (no accidental copy/replay).
- `LAG(ts) OVER (ORDER BY ts)` analysis: 112 adjacent pairs, **0 timestamp ties**, so the `_get_last_hash()` lookup (which uses `ORDER BY ts DESC LIMIT 1`) is unambiguous.

These are necessary conditions for chain integrity but not sufficient — only `verify_chain()` rerun in the app context can confirm the SHA-256 chain itself is intact. The structural prerequisites are clean. No tampering signal.

---

## 5. Race-condition replay (read-only review)

Concurrent fill scenario: WS handler delivers fill A (10 sh @ $100, BUY) and 50ms later fill B (5 sh @ $101, SELL same symbol).

- `_process_trade_update` (`alpaca_stream.py:437`) has **no asyncio.Lock** at the entry point. Two tasks can interleave.
- Inside, each handler acquires its own session via `get_session_context()`. They are independent transactions.
- For the BUY path: `LotTracker.create_lot` simply inserts a new row keyed by `order_id` — no contention possible.
- For the SELL path: `LotTracker.close_lots_fifo` (line 86, lot_tracker_service.py) executes `SELECT ... WHERE status='open' AND remaining_qty > 0 ORDER BY open_date ASC FOR UPDATE` (line 129). The `with_for_update()` clause **does serialize** two concurrent SELL handlers on the same symbol — the second waits for the first commit before reading. Code comment at line 113-119 documents this as fix V4 N-H-2.

**Conclusion**: race protection is correctly placed for the high-risk SELL path. BUY+SELL interleave is safe because `create_lot` always commits a fresh row. Two concurrent SELLs are correctly serialized. The race-protection design is sound — but it currently has zero coverage in production because the lots tables are empty (Finding F2).

---

## 6. Brain-state ↔ DB consistency

| Source | Trades / events |
|---|---|
| `organism_brain/manifest.json` `total_trades` | 498 |
| `organism_brain/trade_history.csv` line count (incl. header) | 499 (= 498 trades) |
| DB `realized_trades` row count | **0** |
| DB `orders` filled count | 1,359 |
| DB `position_lots` row count | **0** |

The brain CSV is the only system-of-record for closed trades. The DB lots/realized tables are completely dark despite 1,359 fills having been recorded as orders. BB-8/BB-10 wiring is **not functioning** in the live deployment — see Finding F2.

V8 BB2 noted that `alpaca_stream.py:553-617` adds the LotTracker call on the live WS path (the wave-30 fix). The code is present (verified in the file), so either:

- (a) the WS handler isn't being invoked for fills (broker-side issue); or
- (b) the handler is invoked but the `if internal_status in ("filled", "partially_filled") and filled_qty and avg_fill_price ...` gate falls through silently; or
- (c) the lot-tracking try/except (line 607-617) is swallowing errors at scale.

**Diagnostic gap**: there is no telemetry (counter / log line) to distinguish (a) from (b) from (c). The `logger.warning("BB-8: lot-tracking failed ...")` would tell us if (c), but only if anyone is reading. With 1,359 filled orders and 0 lots, this is the most consequential live-system bug surfaced.

---

## 7. Migration round-trip safety

Last 3 migrations (by mtime):

| File | `downgrade()` non-empty? |
|---|---|
| `20260503_000001_orders_check_constraints.py` | Yes — drops 7 named CHECK constraints |
| `20260502_000001_add_drawings.py` | Yes — drops 3 indexes + table |
| `20260303_000001_add_tick_telemetry.py` | Yes — drops 2 indexes + table |

`alembic_version` head = `20260503_000001`. Round-trip property holds for the recent stack. V8 OO MIGRATION-GAP fix from wave-37 is preserved.

---

## 8. NULL-leak scan on critical columns

| Column | NULLs |
|---|---|
| `orders.user_id` | 0 (all are literal `'system'`) |
| `orders.symbol` | 0 |
| `orders.qty` | 0 |
| `orders.broker_order_id` | 5 (matches the 5 cancelled-before-ack orders) |
| `audit_logs.action` / `entity` / `actor` / `hash_chain` | 0 / 0 / 0 / 0 |

Position-lot / realized-trade NULL checks elided — the tables are empty.

---

## Findings

### F1 — `orders.user_id` is a free-form varchar with no FK to `users`, hardcoded to `'system'`

**Severity**: medium (compliance / multi-tenancy gap, not a live trading bug)

`orders.user_id` is declared as `character varying` with default `'admin'`, currently set to `'system'` for all 1,369 rows. `users.id` is `integer`. The two cannot be joined. Consequence:

- Every audit trail / risk attribution that joins `orders → users` is impossible.
- The `idx_orders_user_id` and `idx_orders_user_status` indexes provide no actual filtering benefit beyond a single-value scan.
- If the platform ever onboards a second user, there is no enforcement mechanism preventing two users' orders from collapsing into the same `'system'` bucket.
- `audit_logs.actor` is also free-form varchar (e.g. `'user:admin@example.com'`) — same shape, but defensible for compliance (audit must outlive user records).

The `user_id` design parallels `audit_logs.actor` (a tag, not a key). For audit logs that's intentional. For `orders` it's a real referential gap — orders should FK to a real users.id. Recommend: convert `orders.user_id` to `INTEGER NOT NULL REFERENCES users(id)` with backfill.

### F2 — Six (now 14) dark tables: BB-8 / BB-10 wiring is silently failing in production

**Severity**: high (V8 BB2 said "conditionally verified"; BB3 confirms it is **not** working)

All ledger / position / realized-trade / risk / signal / telemetry tables are empty:

- `executions = 0` — broker fill reports are not being persisted as rows.
- `position_lots = 0` — `LotTracker.create_lot` is not being called (or is silently failing).
- `realized_trades = 0` — `close_lots_fifo` is not being called.
- `order_events = 0` — order lifecycle events are not being recorded.
- `risk_metrics = 0`, `risk_violations = 0`, `risk_limits = 0` — the entire risk-tracking surface is unused.
- `daily_ledger = 0` — day-rollups never materialized.
- `signals = 0`, `tick_telemetry = 0` — the strategy decision trail is not being persisted.
- `strategies = 0`, `model_registry = 0` — registries empty (expected for a brain-only deployment, but worth noting that `backtests.strategy_id` FK has no parents to point to).

The brain (`manifest.total_trades = 498`, CSV = 498) is the **sole system of record** for closed trades. 1,359 filled orders left no trace beyond the `orders` row. The wave-30 BB-8 wiring code is physically present in `alpaca_stream.py:553-617` but produces zero rows — there is no telemetry to pinpoint whether the gate condition fails, the broker payload is malformed, or the lot-tracking try/except (line 607-617) is silently swallowing errors. Recommend: add a counter (e.g. `entries_blocked_reason["bb8_lot_skipped"]`) to distinguish gate-fall-through from exception-swallow, and re-verify on next live session.

### F3 — `executions`, `position_lots`, `realized_trades` cascade-delete on `orders.id`

**Severity**: low (compliance / forensic concern)

`fk_executions_order_id_orders`, `fk_position_lots_order_id_orders`, `fk_realized_trades_open_order_id_orders` and `..._close_order_id_orders` all use `ON DELETE CASCADE`. If an `orders` row is ever deleted (admin clean-up, GDPR right-to-erasure), all child fills, lots, and realized-trade history are wiped silently. For a regulated trading platform this is the wrong default — fills and realized trades should outlive their parent order (RESTRICT or set up archive shadow). Currently moot because the children are empty (F2), but the policy is wrong-by-default. Recommend: switch to `ON DELETE RESTRICT` for the four FKs above.

### F4 — `orders.broker_order_id` has no UNIQUE constraint

**Severity**: low (defense-in-depth)

Only `client_idempotency_key` is uniquely indexed. `broker_order_id` has two non-unique btree indexes. In practice no duplicates exist (verified: 0 duplicates, 5 NULLs). But if the gap-fill reconcile loop (`alpaca_stream.py:709`) and the WS handler (`alpaca_stream.py:437`) ever interleave on a yet-unattached order, two `attach_broker_result()` calls could in principle attach the same broker id to two different rows. The `with_for_update()` lock on `position_lots` does not protect this path. Recommend: promote `ix_orders_broker_order_id` to UNIQUE (with NULL allowed for pre-ack orders).

---

## TL;DR

Schema-level invariants on `rc-1.5-curated @ 0826dad` are mostly sound — the wave-30 CHECK constraints on `orders` are in place, idempotency is protected by a unique index on `client_idempotency_key`, the audit-log hash chain has 0 NULLs / 100% unique values / no timestamp ties, the FIFO lot-closing path correctly uses `SELECT ... FOR UPDATE`, all recent migrations have non-empty `downgrade()`, and the FastAPI session dependency wraps commit/rollback correctly. The dominant problem surfaced by BB3 is non-structural: 14 of 17 substantive tables are empty after 1,369 filled orders, including `executions`, `position_lots`, `realized_trades`, `order_events`, and the entire `risk_*` family. The wave-30 BB-8 wiring code in `alpaca_stream.py:553-617` is physically present but produces zero rows in production with no telemetry to distinguish gate-fall-through from silent exception swallow — the brain CSV is the sole system of record for 498 closed trades. Secondary findings: `orders.user_id` is a free-form varchar hardcoded to `'system'` with no FK to `users.id` (referential dead-end), the four `executions`/`position_lots`/`realized_trades` FKs use `ON DELETE CASCADE` (compliance-wrong default that would silently wipe fill history if an order is ever deleted), and `orders.broker_order_id` lacks a UNIQUE index (low-risk race window between gap-fill and WS handler). Add a `bb8_lot_skipped` counter, promote `broker_order_id` to UNIQUE, and switch the four order-children FKs to RESTRICT.
