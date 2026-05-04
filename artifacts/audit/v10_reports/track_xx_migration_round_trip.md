# Track XX v10 — Migration Round-Trip on Snapshot DB (NEW LENS)

**Repo**: `/Users/marselkei/VS/intra`
**Branch**: `rc-1.5-curated` @ `c0481033d8c2db10dd4b92c9832da2fc17667e7a`
**Run timestamp**: 2026-05-03
**Scratch DB**: `algotrading_xx_test` (dropped at end — confirmed)
**Prod DB**: `algotrading` (untouched — `SELECT COUNT(*) FROM orders` = 1369 before & after)

## Method executed

1. Created `algotrading_xx_test` on `trading_platform_db_paper`.
2. `alembic upgrade head` from empty → SUCCESS, ends at `20260503_000001 (head)`. 17 migrations applied, linear chain (no branches).
3. Round-trip 1 step (`downgrade -1` / `upgrade +1`): schema dump byte-identical except for random `\restrict` session tokens. PASS.
4. Round-trip 3 steps (`downgrade -3` / `upgrade +3` covering `20260503_000001`, `20260502_000001`, `20260303_000001`): schema dump byte-identical except for tokens. PASS.
5. AST-walked recent migrations for `upgrade()` vs `downgrade()` op-count parity.
6. Test-data round-trip on `orders`: inserted a valid row, downgraded by 1 (drops CHECKs), upgraded back. Row survived; CHECK constraints re-enforce after upgrade. PASS.
7. **Full reverse trip (`downgrade base`)** — FAILED mid-stream. Investigation below.
8. ORM drift via `alembic check` — multiple findings.
9. Cleanup: `DROP DATABASE algotrading_xx_test`.

## Findings

### Finding 1 (HIGH) — `downgrade base` is broken: `ec197100938a` references a constraint that was never created

**Severity**: High. Means **disaster-recovery rollback past `83ec4ee73d7d` is impossible** without manual SQL surgery.

**Reproduction**:
```
DATABASE_URL=... alembic upgrade head           # OK
DATABASE_URL=... alembic downgrade base          # FAILS at ec197100938a -> 706e00fe1a28
```

**Root cause**: `backend/migrations/versions/ec197100938a_add_idempotency_constraints_and_order_.py:147`

```python
try:
    op.drop_constraint('uq_orders_account_client_order', 'orders', type_='unique')
except Exception:
    pass
```

The constraint name `uq_orders_account_client_order` is referenced **only here**:

```
$ grep -rn "uq_orders_account_client_order" backend/migrations/ backend/infra/
backend/migrations/versions/ec197100938a_add_idempotency_constraints_and_order_.py:147
```

It's never created in the matching `upgrade()` (or anywhere else). The Python `try/except: pass` is **a trap** — it catches the SQLAlchemy exception, but Postgres has *already aborted the surrounding transaction* the moment the failed `ALTER TABLE ... DROP CONSTRAINT` was sent. Every subsequent statement in this `downgrade()` (the `DROP TABLE daily_ledger`, `DROP TABLE order_events`, `DROP COLUMN account_id`) errors with `InFailedSqlTransaction`.

Verified by manual psql replay of the downgrade ops in a transaction:
```
=== step 11: drop uq_orders_account_client_order ===
ERROR:  constraint "uq_orders_account_client_order" of relation "orders" does not exist
=== step 12: drop_table daily_ledger ===
ERROR:  current transaction is aborted, commands ignored until end of transaction block
... (steps 13, 14 also fail)
```

**Fix**: Either (a) remove the dead `op.drop_constraint(...)` call entirely (cleanest — the constraint was never made, no need to drop), or (b) wrap it in a savepoint:
```python
conn = op.get_bind()
conn.execute(sa.text("SAVEPOINT sp"))
try:
    op.drop_constraint('uq_orders_account_client_order', 'orders', type_='unique')
    conn.execute(sa.text("RELEASE SAVEPOINT sp"))
except Exception:
    conn.execute(sa.text("ROLLBACK TO SAVEPOINT sp"))
```
A bare Python `try/except` is **not** sufficient inside Postgres transactional DDL.

### Finding 2 (HIGH) — CHECK constraint disagrees with the partial index `ix_orders_active_status`; status enum is incomplete

**Severity**: High. The new `ck_orders_status` CHECK is **incompatible with the partial index that the same `orders` table carries** and **incompatible with statuses the live engine writes elsewhere**.

The `20260503_000001` migration adds:
```sql
CHECK (status IN ('pending','accepted','submitted','partially_filled','filled',
                  'cancelled','expired','rejected','pending_cancel','pending_replace',
                  'replaced','stopped','suspended','calculated','deferred','failed',
                  'filled_during_cancel'))
```

But migration `20260201_000003` created a partial index whose `WHERE` predicate includes statuses `'new'` and `'pending_new'`:
```sql
CREATE INDEX ix_orders_active_status
ON orders (status, symbol, created_at DESC)
WHERE status IN ('new', 'pending_new', 'accepted', 'partially_filled', 'pending_cancel');
```

Verified empirically on the scratch DB:
```
INSERT ... status='new'         -> ERROR ck_orders_ck_orders_status violated
INSERT ... status='pending_new' -> ERROR ck_orders_ck_orders_status violated
```

The repo also has independent app-layer code paths that name `'new'` as an active status:
```
backend/infra/repositories/orders.py:385:
    active_statuses = ["accepted", "submitting", "submitted", "partially_filled"]
```
(`'submitting'` is yet another value not in the CHECK, though not currently in the index.)

**Operational risk**: If any deployed code path tries to insert an order with `status='new'` or `'pending_new'` (the names the partial index was built to optimize for), the insert will fail with a CHECK violation in production. The migration was reviewed against current paper-DB content (1369 rows, all in {`filled`, `cancelled`, `accepted`, `expired`}), so it didn't fail the `VALIDATE` step — but **today's safe data does not equal tomorrow's safe code paths**.

**Cosmetic side-finding**: every CHECK is named `ck_orders_ck_orders_*` (double prefix) because Alembic auto-prefixes with `ck_orders_` on top of the user-supplied `ck_orders_qty_positive`, etc. Drop the leading `ck_orders_` from the names supplied to `op.create_check_constraint` to get clean `ck_orders_qty_positive` etc.

**Fix**: Reconcile the three sources of truth. Either expand `_VALID_STATUSES` to include `'new'`, `'pending_new'`, `'submitting'` (and audit `live_engine`/`order_service` for the canonical set), OR drop the partial index and unify `repositories/orders.py` on the migration's enum.

### Finding 3 (MEDIUM) — Significant ORM-vs-DB drift; autogenerate would emit ~50 ops

**Severity**: Medium. `alembic check` against `target_metadata = Base.metadata` against the freshly-migrated head schema reports the schema is NOT in sync with the ORM. Selected drift items:

- **Missing migration for `portfolio_history` table** — declared in `backend/infra/schemas.py` (with FK to `users.id`, 3 indexes) but NO migration creates it. App code referencing this table will 500 on a cold-start DB. Same class of bug that the `20260502_000001` migration was added to fix (drawings table).
- **`daily_ledger` table** — present in DB (created by migration `ec197100938a`) but **not in the ORM**. Autogenerate wants to drop it.
- **`orders.account_id` column** — present in DB (migration `ec197100938a`), not in ORM. Autogenerate wants to drop it.
- **No CHECK constraints in ORM** — the seven `ck_orders_*` constraints from `20260503_000001` aren't declared in the SQLAlchemy model. Autogenerate is silent on them only because `compare_type` defaults skip CHECKs, but the source-of-truth is now split.
- **No partial / GIN indexes in ORM** — `ix_orders_active_status`, `ix_orders_attributes_gin`, `ix_outbox_events_payload_gin`, `ix_order_events_event_data_gin` all flagged as removed.
- **13 indexes naming-convention drift** — ORM uses `ix_<table>_<col>` (alembic naming convention), migrations used `idx_<table>_<col>` or `ix_<table>_<short>`. Examples: `ix_risk_metrics_name` → `ix_risk_metrics_metric_name`, `idx_orders_user_id` → `ix_orders_user_id`. Each is a duplicate index on the same column, wasting RAM/disk.
- **3 unique constraints removed** — `strategies.name`, `users.email`, `users.username` declared `unique=True` in ORM but no UNIQUE constraint on the DB column.

Total drift: 4 add_index, ~13 remove_index, ~3 modify_type/nullable, 1 add_table, 1 remove_table, 1 remove_column, 3 remove_constraint, 1 add_fk modification.

This is the silent third-finding behind Finding 1 — the team is hand-writing migrations and the ORM has drifted away from being the source of truth. Going forward the choice is: (a) make ORM authoritative and re-baseline, OR (b) drop `target_metadata` from `env.py` and embrace migration-as-source-of-truth (but then `alembic check`/autogenerate become useless).

## Round-trip raw results

| Step | Action | Result |
|---|---|---|
| 1 | `upgrade head` from empty | OK (17 migrations, 1984 lines schema) |
| 2 | `downgrade -1` then `upgrade +1` | Schema diff: 0 lines (modulo restrict tokens) |
| 3 | `downgrade -3` then `upgrade +3` | Schema diff: 0 lines (modulo restrict tokens) |
| 4 | INSERT row, `downgrade -1`, `upgrade +1`, SELECT row | Row preserved, CHECKs re-enforced |
| 5 | `downgrade base` | **FAILS** at `ec197100938a` — Finding 1 |
| 6 | Cleanup `DROP DATABASE` | OK |

## downgrade() completeness for 3 most-recent migrations

| Migration | upgrade ops | downgrade ops | Verdict |
|---|---|---|---|
| `20260303_000001_add_tick_telemetry` | 3 (1 table + 2 indexes) | 3 (2 drop_index + 1 drop_table) | Complete |
| `20260502_000001_add_drawings` | 4 (1 table + 3 indexes) | 4 (3 drop_index + 1 drop_table) | Complete |
| `20260503_000001_orders_check_constraints` | 7 (7 CHECKs) | 1 stmt = for-loop dropping 7 CHECKs | Complete (semantically 7-for-7) |

## Lock-time analysis (forward-looking)

None of the 17 migrations use `postgresql_concurrently=True` or wrap index creation in `CREATE INDEX CONCURRENTLY`. At paper scale (1369 rows on `orders`) this is a non-issue. At production scale on `orders`:

- `20260503_000001`: 7 × `op.create_check_constraint` → 7 × `ALTER TABLE orders ADD CONSTRAINT ... CHECK (...)`. Each takes `ACCESS EXCLUSIVE` and does a full sequential scan to validate. At 10M rows on `orders`, expect each constraint to take 10–60s blocking writes; total ~1–7 minutes of write-blocking. Mitigation: add as `NOT VALID` first, then `VALIDATE CONSTRAINT` separately (the latter takes only a row-share lock).
- `20260201_000003`: GIN indexes on JSONB columns + partial index — `CREATE INDEX` (not CONCURRENTLY) holds `SHARE` lock blocking writes. Add `postgresql_concurrently=True` for production-sized tables.
- `add_user_id_to_orders`: `ALTER TABLE orders ADD COLUMN user_id ... NOT NULL DEFAULT 'admin'` — Postgres ≥ 11 handles `NOT NULL DEFAULT` as metadata-only (fast), so this one is fine.

## Cleanup confirmation

```
$ docker exec trading_platform_db_paper psql -U trading -d postgres -c "SELECT datname FROM pg_database"
postgres / algotrading / template1 / template0   (algotrading_xx_test absent)

$ docker exec trading_platform_db_paper psql -U trading -d algotrading -c "SELECT COUNT(*) FROM orders"
1369   (unchanged)
```

## TL;DR

Migration round-trips of the 3 most recent revisions are clean (schema-level byte-identical, test data survives), and `downgrade()` op-counts match `upgrade()` for those revisions. **However, full disaster-recovery `downgrade base` is broken**: migration `ec197100938a` calls `op.drop_constraint('uq_orders_account_client_order', ...)` for a constraint that was never created, and the surrounding `try/except: pass` does not save the transaction (Postgres aborts the whole txn the moment the failed DDL is issued, so the next three ops — including dropping `daily_ledger` and `order_events` — die with `InFailedSqlTransaction`). Compounding this, the new `ck_orders_status` CHECK from `20260503_000001` is incompatible with statuses (`new`, `pending_new`) that the partial index `ix_orders_active_status` was built for and that `repositories/orders.py:385` lists as active — meaning a code path that writes those statuses will throw a CHECK violation in production despite passing the migration's `VALIDATE` against today's safe data. Schema-vs-ORM drift is also significant (~50 autogenerate ops, including a missing `portfolio_history` table — same bug class that `20260502_000001` was created to fix for `drawings`). Recommended fixes: delete the dead `op.drop_constraint` line in `ec197100938a`, reconcile the orders status enum across migration/index/repository, and either re-baseline the ORM as authoritative or remove `target_metadata` from `env.py`.
