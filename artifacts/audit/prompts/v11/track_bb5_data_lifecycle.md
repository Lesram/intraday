# Track BB5 v11 — Data Lifecycle (TTL, Retention, GDPR, Txn Boundaries)

V10 BB4 verified position_lots reach. **BB5 audits data lifecycle**: TTL/retention on every table, GDPR right-to-be-forgotten, archive paths, transactional boundaries under load.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`. Postgres `trading_platform_db_paper`.

## Method

### 1. Table-by-table retention audit

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT schemaname, tablename, n_live_tup
   FROM pg_stat_user_tables
   ORDER BY n_live_tup DESC LIMIT 30;"
```

For each table with > 100 rows, identify:
- TTL policy? (e.g. `tick_telemetry` claims 7-day retention; verify `_cleanup_old_telemetry` actually runs).
- Archive destination?
- Partitioning?
- Index bloat?

Specifically `audit_logs` (compliance) and `tick_telemetry` (operational).

### 2. GDPR right-to-be-forgotten scenarios

If a user requests deletion:
- `DELETE FROM users WHERE email='X'` — what cascades?
- Are `orders`, `position_lots`, `realized_trades` cleaned via FK CASCADE?
- Does `audit_logs.actor` field get scrubbed (or anonymized)?

The audit_logs hash chain breaks if a row is deleted. Mitigation?

### 3. Transactional boundaries under load

For each `await session.commit()` site in `backend/`, is the lock released cleanly even on timeout / cancellation?

```
grep -rn "session.commit\|await session.commit" backend/ --include='*.py' | head -20
```

Sample 5 sites; trace the surrounding transaction. Identify any site that holds a transaction across a network call (DB lock + HTTP wait = deadlock risk).

### 4. Archive / cold-storage paths

Look for any code that writes to:
- S3 / object storage
- `archive/` directories
- Backup destinations

```
grep -rn "boto3\|s3\|archive_dir\|backup_dir" backend/ --include='*.py' | head -10
```

Document: does anything actually archive, or do all tables grow forever?

### 5. trade_history.csv + organism_brain growth

```
ls -la organism_brain/ | head -20
wc -l organism_brain/trade_history.csv
```

What's the bound? When does pruning happen?

### 6. Outbox pattern integrity

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*) AS outbox_rows, MIN(created_at), MAX(created_at)
   FROM outbox;"
```

Are processed rows being purged? If outbox grows unbounded, write-amplification kicks in.

### 7. Partial fills + LotTracker lifecycle (wave-43 DD3-2 follow-through)

Now that wave-43 DD3-2 + the rebuild are LIVE:
- `position_lots` row counts since last fill.
- Any duplicate `(order_id, ...)` rows still landing?
- Quote LIMIT 5 most recent rows.

### 8. Foreign key cascade map

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "
SELECT tc.table_name, kcu.column_name, ccu.table_name AS ref_table, rc.delete_rule
FROM information_schema.referential_constraints rc
JOIN information_schema.table_constraints tc ON rc.constraint_name = tc.constraint_name
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON rc.constraint_name = ccu.constraint_name
ORDER BY tc.table_name;"
```

Audit which FKs cascade vs restrict vs SET NULL. Critical: anything to/from `audit_logs` or `users`.

### 9. wave-61 portfolio_history apply (verify)

Run `alembic upgrade head` against a SCRATCH DB; verify portfolio_history table is created with all expected columns + indexes.

## Output

`artifacts/audit/v11_reports/track_bb5_data_lifecycle.md` with per-section findings.

Quality bar: 1-4 findings.
