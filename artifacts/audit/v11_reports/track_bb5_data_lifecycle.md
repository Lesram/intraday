# V11 Track BB5 — Data Lifecycle (TTL, Retention, GDPR, Txn Boundaries)

- Repo: `/Users/marselkei/VS/intra`
- Branch: `rc-1.5-curated` @ `3778344`
- DB: `algotrading` on `trading_platform_db_paper` (paper)
- API container: `intra-api-1` (healthy, but tick loop quiescent — only auth/health hits in the last few minutes; engine has not run a `_persist_telemetry_to_db()` cycle).
- Mode: SELECT only.

---

## Snapshot — table sizes & alembic state

`pg_stat_user_tables.n_live_tup` (top non-empty tables, paper DB):

| Table | live rows | dead | last_autovacuum |
|---|---|---|---|
| `outbox_events` | **1 398** | 311 | (never) |
| `orders` | 1 332 | 4 | 2026-05-01 19:40 |
| `audit_logs` | 332 | 0 | (never) |
| `users` | 3 | 10 | (never) |
| every other table | 0 | 0/1 | — |

Disk: `outbox_events` heap 2 264 kB / indexes 2 712 kB (8 indexes); `orders` 2 328 kB heap / 3 800 kB index; `audit_logs` 208 kB. Small in absolute terms, but those numbers are *60 days* of paper traffic — in a busier prod regime the trajectory matters.

Alembic head in DB: **`20260503_000001`**. Files on disk go up to `20260503_000003_xx_3_portfolio_history`. So `_000002` (orders status check widening) and `_000003` (portfolio_history table) **have not been applied** to this paper DB.

---

## Findings

### F1 — `outbox_events` accumulates `sent` rows forever; only manual SQL purges it (HIGH)

`backend/infra/outbox_worker.py` (full file traced) calls only:

- `mark_sent`  → `UPDATE outbox_events SET status='sent', sent_at=now()` (`backend/infra/outbox.py:210-224`)
- `mark_retry` → `UPDATE … attempts/next_attempt_at`
- `mark_failed` → `UPDATE … status='failed'` (DLQ in-place, see L750-815)

No `DELETE`, no TTL, no archive. Repo-wide grep for `DELETE FROM outbox`, `outbox.*delete`, `prune.*outbox`, `purge` returns exactly one match — **`scripts/db/clear_outbox.sql`**, a manual SQL playbook that operators must run by hand:

```sql
-- scripts/db/clear_outbox.sql
DELETE FROM outbox_events
WHERE status = 'pending' AND attempts >= 5;
```

It only targets stuck-pending rows; it never touches `sent`. Live state confirms:

```
status |  count |              min                |              max
-------+--------+---------------------------------+--------------------------------
 sent  |  1 393 | 2026-03-02 16:08:02.803192+00   | 2026-05-01 19:42:07.568793+00
 failed|      5 | 2026-03-04 21:00:54.027368+00   | 2026-04-08 13:35:35.882365+00
```

So 1 393 successful events from 60 days back are still present, plus the 8 indexes (`ix_outbox_status_next_attempt`, `ix_outbox_topic_status`, `ix_outbox_events_payload_gin`, etc.) all keep growing. `claim_batch` uses `FOR UPDATE SKIP LOCKED` over `(status, next_attempt_at)` — that index *is* selective enough today (only 5 non-`sent` rows), but write-amplification on `sent_at`/`status` UPDATE plus GIN-on-payload reindexing means each new `order.submitted` event pays a cost proportional to the unbounded heap. There is also no autovacuum (the `last_autovacuum` column is NULL for `outbox_events`).

Required: a periodic purge (e.g. delete `status='sent' AND sent_at < now() - interval '7 days'`) wired into a worker or pg_cron job, not a hand-run SQL script.

---

### F2 — GDPR / right-to-be-forgotten is structurally unimplementable: financial tables are not FK'd to `users`, and `audit_logs.actor` is hash-chained (HIGH)

Two coupled defects make a clean user-deletion impossible.

**(a) `orders.user_id` has no foreign key to `users`.** From `\d orders`:

```
 user_id | character varying(255) | not null | 'admin'::character varying
Indexes: idx_orders_user_id, idx_orders_user_status   (no FK constraint)
```

Confirmed via `information_schema.referential_constraints`: **no row** lists `orders` → `users`. Same for `executions`, `order_events`, `position_lots`, `realized_trades`, `daily_ledger` (none of them reference `users`; they reference `orders`, which has cascade chains: `executions ON DELETE CASCADE`, `position_lots ON DELETE CASCADE`, `realized_trades.{lot_id, open_order_id, close_order_id} ON DELETE CASCADE`).

So `DELETE FROM users WHERE email='X'` cascades only to: `chart_templates`, `emergency_stops` (user_id only — `triggered_by`/`resolved_by` are `NO ACTION`), `risk_limits` (user_id only — `updated_by` is `NO ACTION`), `risk_metrics`, `risk_violations`, `watchlists`. **Every financial record (orders, fills, lots, realized P&L, daily ledger) is left orphaned**, still keyed by the now-missing user's varchar identifier. No anonymise hook exists either — repo grep for `anonymize|scrub|forget|gdpr|right_to_be_forgotten` returns only logger PII scrubbers (`backend/utils/logger.py:107-187`), nothing for the audit/order tables.

**(b) `audit_logs.actor` is part of the hash chain.** `backend/services/audit_service.py:113-140`:

```python
data = {
    "prev": previous_hash or "GENESIS",
    "ts": timestamp.isoformat(),
    "action": action, "entity": entity, "entity_id": entity_id,
    "actor": actor,              # <-- in the hash input
    "payload": payload,
}
canonical = json.dumps(data, sort_keys=True, default=_json_serializer)
return hashlib.sha256(canonical.encode()).hexdigest()
```

`audit_logs` has no FK to users (verified — only the seven indexes; no `Referenced by` block in `\d audit_logs`). Live row sample shows actor field carries plaintext PII (`user:admin@example.com`, `user:audit_aa3_test@example.com`, etc., 332 rows). The service writes `prev_hash` from the most-recent row (`_get_last_hash()` line 199-211) and the verifier (`backend/services/audit_service.py:420-450`) walks the chain end-to-end. Any `UPDATE audit_logs SET actor='REDACTED' WHERE actor LIKE 'user:gdpr-deleted@%'` (or `DELETE`) will break verification for **every subsequent row**, exactly the bug class the chain was built to detect. The track prompt's "audit_logs hash chain breaks if a row is deleted. Mitigation?" is unanswered: there is no tombstone, no chain-segment break+reseed, no separate identity-mapping table. Right-to-be-forgotten currently requires either re-hashing the entire chain (defeating its purpose) or accepting non-compliance.

Required: (i) add real FK `orders.user_id REFERENCES users(id)` (with backfill for the legacy `'admin'` rows) so a deletion has a deterministic blast radius; (ii) introduce an actor-identity indirection table so `audit_logs.actor` stores an opaque ID, and PII lives in a separately deletable table — keeps the chain integrity intact while honouring deletion.

---

### F3 — `tick_telemetry` 7-day cleanup is in code, but the table is **0 rows** despite the V4 N-C-2 import fix; cleanup never runs against any data (MEDIUM)

`backend/organism/live_engine.py:6240-6261`:

```python
async def _cleanup_old_telemetry(self) -> None:
    """Delete telemetry rows older than 7 days."""
    ...
    cutoff = self._now_fn() - timedelta(days=7)
    async with get_session_context() as session:
        await session.execute(sa.delete(TickTelemetry).where(TickTelemetry.timestamp < cutoff))
        await session.commit()
```

Triggered once every 2 160 ticks (`live_engine.py:4458-4460`). The earlier ImportError-swallow bug (commented at lines 6190-6193 / 6246-6249) was fixed in V4 N-C-2 (`from backend.infra.db import get_session_context`) and the fix is on disk in the running container (verified `docker exec intra-api-1 grep V4 N-C-2 /app/backend/organism/live_engine.py`). But the table is still empty:

```
SELECT count(*), MIN(timestamp), MAX(timestamp) FROM tick_telemetry;
 count | min | max
-------+-----+-----
     0 |     |
```

Recent API logs (`docker logs intra-api-1 --tail 200`) show no telemetry-write log lines, no warnings — only auth/health 401/200s. The engine in this container is not ticking (paper rebuild, no live tick scheduler attached this session). So the in-engine retention policy is never exercised end-to-end on production data — it's only verifiable by a dedicated test, and nothing in `tests/` exercises `_cleanup_old_telemetry` (no hits for that name in tests). Until the live engine actually writes rows, the 7-day TTL claim is unverified, and on first turn-on the operator should expect a step-function in DB size before the first cleanup boundary at tick 2 160 (~6 hours at 10 s/tick). Worth wiring a scheduled job (or pg_cron) as a backstop independent of tick cadence.

---

### F4 — Wave-61 `portfolio_history` migration is on disk but unapplied; PortfolioStore writes will fail silently when the engine resumes (MEDIUM)

`alembic_version.version_num = 20260503_000001`, but `backend/migrations/versions/` contains:

- `20260503_000002_xx_2_widen_orders_status_check.py`
- `20260503_000003_xx_3_portfolio_history.py`

The wave-61 file (read in full) creates the `portfolio_history` table with FK `user_id → users(id) ON DELETE CASCADE`, three indexes, and a CHECK on `snapshot_type`. Verification: `SELECT EXISTS (… WHERE table_name='portfolio_history')` returns `f`. The header comment in the file calls out the failure mode explicitly:

> `backend/infra/schemas.py` (1135-1204) declares `PortfolioHistory` but no migration creates it — identical to the V7 BB / wave-25 `drawings` bug class. An existing `scripts/runtime/write_runtime_snapshot.py` and the FE `PortfolioStore` rely on this table; without the migration the live DB has no place to write.

So once the live engine resumes ticking on this DB, every PortfolioHistory write will raise `UndefinedTable` and (depending on the call site) be silently swallowed, exactly the V7 BB / wave-25 pattern this migration was authored to fix. Required before next deploy: run `alembic upgrade head` against the paper DB, then re-verify table+indexes exist.

---

## Notes (not standalone findings)

- **No archive / cold-storage path exists** for any DB table. Repo-wide grep for `boto3`, `s3`, `archive_dir` returns only `trade_history.csv` archives (gzipped, capped at 10 files, `backend/organism/brain_persistence.py:1537-1563`) and `DB_BACKUP_DIR` for pg_dump (`backend/database/database_config.py:55-56`, retention 30 days). Operational tables (`audit_logs`, `executions`, `order_events`, `daily_ledger`, `risk_metrics`, `model_monitoring_snapshots`) grow forever.
- **`organism_brain/trade_history.csv`**: 499 lines, 76 KB — well under `MAX_TRADE_ROWS=10_000`. Pruning logic is correct (`brain_persistence.py:1537-1563`). Two corrupt-head directories present (`corrupt_head_20260503_113644_*`) — separate concern, not a lifecycle bug per se but they will accumulate if recovery runs repeatedly.
- **Transaction-boundary scan** (53 `session.commit` sites, sampled 5): I did not find a commit holding a lock across an HTTP call. The risky pattern would be `attach_broker_result` (`backend/infra/outbox_worker.py:_update_order_status` lines 587-644) being inside the outer `_process_event` while `_submit_real_broker_order` is awaited — but the network call happens *before* `_update_order_status` opens its session (line 395 vs 587), so the broker HTTP roundtrip is not inside any open DB transaction. `alpaca_stream.py:600-670` is also clean: HTTP is in the outer Alpaca SDK callback, the DB session opens after the broker event is decoded.
- **`position_lots` / `realized_trades` are 0 rows** in this paper DB. Wave-43 DD3-2 LotTracker wire-up exists in `alpaca_stream.py:565-682` (verified), but it has not produced rows here — consistent with the engine being quiescent in this container. No duplicate `(order_id, …)` rows to investigate (the table is empty).
- **FK cascade map** (full dump in working notes): only `users` → child tables and `orders` → `executions`/`position_lots`/`realized_trades` cascade. `model_lifecycle_events` and `model_monitoring_snapshots` use `SET NULL`. `order_events.order_id` and `emergency_stops.{triggered_by, resolved_by}` use `NO ACTION` — deletion-blocking, fine for compliance but the operator should know.
- **`audit_logs` content**: 332 rows, 100% are `user.login` / `user.login_failed` (267 logins by `admin@example.com` alone). Despite the V10 YY-2 / Wave-52 wiring of `ORDER_FILLED` audit rows (`alpaca_stream.py:643-675`), zero `ORDER_FILLED` rows exist — coherent with the LotTracker zero-row state above (no fills processed in this container).

---

## Suggested follow-ups (priority order)

1. **F2 (GDPR)** — design + ship the actor-indirection + `orders.user_id` FK before any production deploy. Two-step migration: (i) introduce `actor_identities(id, scrubbed bool, …)`; (ii) add FK with backfill of legacy `'admin'`. Without this, GDPR requests cannot be honored without breaking either the audit chain or financial-record integrity.
2. **F1 (outbox)** — wire a 7-day purge for `status='sent'` rows; either a tiny periodic task in the existing OutboxWorker, or a `pg_cron` job. Easy fix.
3. **F4 (alembic)** — `alembic upgrade head` against paper before next engine restart, then verify `portfolio_history` exists and that `\d portfolio_history` shows the FK + 3 indexes from the migration.
4. **F3 (telemetry)** — keep the in-engine cleanup, but add a DB-side scheduled cleanup as a backstop, and write an integration test that exercises `_cleanup_old_telemetry` with rows present.
