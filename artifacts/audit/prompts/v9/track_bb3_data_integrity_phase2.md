# Track BB3 v9 — Data Integrity Phase 2

V8 BB2 verified wave-30 BB-8/BB-10 wiring under available conditions and flagged 6 dark tables (BB2-F2, deferred). **BB3 goes deeper into schema-level invariants, FK cascades, transaction boundaries, and the dark-table list.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `db1a3fc`. Postgres on `trading_platform_db_paper` (per V8 BB2 correction).

## Method

### 1. Schema invariants — FK / unique / partial-index audit

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "
SELECT
  tc.table_name, tc.constraint_name, tc.constraint_type, kcu.column_name,
  ccu.table_name AS ref_table, ccu.column_name AS ref_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
LEFT JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
WHERE tc.table_schema = 'public' AND tc.constraint_type IN ('FOREIGN KEY', 'UNIQUE', 'CHECK')
ORDER BY tc.table_name, tc.constraint_type;
"
```

For each FK, verify `ON DELETE` behavior is appropriate:
- `orders.user_id → users.id` should be RESTRICT or CASCADE (NOT SET NULL silently).
- `position_lots.symbol` should reference a symbols dimension OR have a CHECK constraint.
- `audit_logs` chains rely on hash; verify no FK cascade can break the chain by deleting parent rows.

### 2. Transaction boundary audit

For each `await session.commit()` site in `backend/`, identify:
- Is there a corresponding `try/except` that rolls back on failure?
- Are there long-lived sessions that hold locks across non-DB I/O (HTTP / broker)?

```
grep -rn "session.commit\|await session.commit" backend/ --include='*.py' | head -30
```

For each, walk back 30 lines and verify:
- A try/except wraps the commit.
- The except has `await session.rollback()`.
- The session lifetime is scoped via `async with` / context manager.

### 3. Dark-table re-audit (BB2-F2 follow-up)

For each of the 6 dark tables:
- `executions`: row count + last write timestamp.
- `positions`: row count + recency.
- `order_events`: row count + recency.
- `risk_violations`: row count.
- `daily_ledger`: row count + day-coverage.

If any table is empty or stale > 7 days, mark for wire-or-drop decision.

### 4. Hash-chain integrity at scale

Re-verify with a larger window than BB2:

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "
WITH chain AS (
  SELECT id, prev_hash, current_hash, ts,
         LAG(current_hash) OVER (ORDER BY id) AS expected_prev
  FROM audit_logs
)
SELECT count(*) AS broken FROM chain
WHERE expected_prev IS NOT NULL AND prev_hash != expected_prev;"
```

Expected: 0.

### 5. Race-condition replay

Simulate two concurrent fills landing for the same symbol:
- Position A: 10 shares filled at $100.
- Position B: arrives 50ms later — same symbol, 5 shares at $101.
- Does LotTracker handle both correctly without double-counting?

(Read-only — review code in `backend/integrations/alpaca_stream.py:_process_trade_update` for the lock or idempotency strategy.)

### 6. Brain-state file vs DB consistency

```
cat organism_brain/manifest.json | jq '.total_trades'
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*) FROM realized_trades;"
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*) FROM orders WHERE status='filled';"
```

Cross-reference: if `manifest.total_trades` >> `count(realized_trades)`, BB-8 wiring still has a gap.

### 7. Migration round-trip safety check (limited)

V8 OO MIGRATION-GAP was resolved in wave-37 (smoke check). Verify:
- The HEAD migration's `downgrade()` is non-empty for each schema-changing migration.
- Specifically check the most recent 3 migrations (wave-30 BB constraints, etc.).

```
ls backend/migrations/versions/ | tail -3 | while read f; do
  echo "=== $f ==="
  grep -A 5 'def downgrade' "backend/migrations/versions/$f"
done
```

### 8. NULL-leak scan on critical columns

Same as V8 BB2 but extended to:
- `orders.user_id`, `orders.symbol`, `orders.qty`
- `position_lots.symbol`, `position_lots.opened_at`
- `realized_trades.realized_pnl`
- `audit_logs.action`, `audit_logs.entity`, `audit_logs.actor`

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "..."
```

## Output

`artifacts/audit/v9_reports/track_bb3_data_integrity_phase2.md` with FK / constraint catalog, transaction boundary analysis, dark-table status, hash-chain re-verification, race-condition review, brain-vs-DB consistency, downgrade availability, NULL-leak.

Quality bar: 2-4 findings. End with one-paragraph TL;DR.
