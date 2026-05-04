# Track S v5 — Stress & Failure-Mode Audit

Test how the platform behaves under external failures: network partition,
broker burst, DB drop, container OOM, clock skew, disk-full, Redis outage,
outbox backpressure. The platform's correctness assumes its dependencies
are alive; this track audits the failure paths.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d43dbec`.

## Files in scope

Anything in the failure path of:
- WebSocket: `backend/integrations/alpaca_stream.py`
- HTTP broker: `backend/integrations/alpaca_broker.py`, `backend/data/alpaca_client.py`
- DB: `backend/infra/db.py`, every service taking `AsyncSession`
- Redis: `backend/services/cache.py`
- Outbox: `backend/infra/outbox.py`, `backend/infra/outbox_worker.py`
- Brain save: `backend/organism/brain_persistence.py`
- Risk / governance: `backend/organism/governance.py`, `backend/risk/`
- Tick loop: `backend/organism/live_engine.py`, `backend/organism/scheduler.py`
- Lifespan: `backend/api/lifespan.py`

## Method

For each scenario below, statically analyze the code path AND, where safe,
run a synthetic probe. Record outcome per scenario.

### Network / WebSocket failures

1. **WS disconnect mid-trade**: alpaca_stream WS drops between order submit and
   fill. What happens? Audit:
   - Does the gap-fill on reconnect (`_gap_fill_after_reconnect`) actually
     close the missed-fill gap?
   - If a fill happened during the disconnect window, does the next reconcile
     pick it up via the broker REST API?
   - If WS never reconnects (max-reconnect cap reached): does
     `_handle_max_reconnects` correctly route to alerting + halt? (V4 wave-12f
     P-P0-4 fix wired this.)
   - State of `_pending_entry` after a disconnect-and-reconnect cycle.

2. **WS staleness without disconnect** (alive but not delivering): the
   "ALL symbols stale" path. What blocks entries? Does it block exits too?

3. **Broker REST 503 burst**: 5 consecutive 503s on submit_order. Circuit
   breaker behavior:
   - Does it trip after 3 failures? (Track P P-P0-4 verifies the alert
     path works post-Wave-12f.)
   - Does the engine continue to manage existing positions while submit
     is blocked? Should it.
   - Recovery semantics: how long does the breaker stay open? Half-open
     transition correct?

4. **Broker submission hangs (timeout)**: HTTP request never returns.
   Are timeouts set everywhere? `httpx.AsyncClient` reuse?

### Database failures

5. **Postgres connection drop mid-tick**: every `AsyncSession` user. What
   happens to:
   - Tick telemetry write (V4 wave-12c just fixed the import).
   - Outbox claim_batch (V4 wave-12b lease assumes session.commit succeeds).
   - LotTracker.close_lots_fifo (wave-13e added with_for_update — verify the
     row lock is correctly released on connection drop).
   - Position reconciliation service.

6. **Postgres connection pool exhaustion**: 30 concurrent sessions held;
   31st request. Does it queue or fail-fast? Configured timeout?

7. **DB write succeeds but commit fails**: any code path where business
   logic is observable post-write but pre-commit?

### Redis failures

8. **Redis outage**: `redis_available = False` mid-operation. Does:
   - Quote cache fall back to in-memory (Q-Q5 verifies the cap holds)?
   - Symbol metadata fallback work?
   - Any code path *requires* Redis (no fallback)?

9. **Redis slow (latency spike)**: timeout set on every Redis call?
   `socket_timeout=1` is hard-coded in `_init_sync_fallback` — is it on the
   async path too?

### Container / OS failures

10. **Container OOM mid-tick**: container restarts. Brain restore path
    integrity. After Wave 12d ensemble is saved via essential_state, the
    next restart will load the ensemble — verify via grep that the load
    path is invoked. Any state held only in memory (not persisted) that
    a restart loses?

11. **Disk full mid-brain-save**: atomic-rename pattern (`trade_history.csv.tmp`
    rename) protects against partial writes; verify other save sites also use
    write-then-rename. What happens to the manifest if disk fills between
    `_save_*` calls but before manifest write?

12. **Clock skew**: NTP drift +5s, -5s. Affects:
    - `is_market_hours` checks
    - Bar-boundary detection (R-F-4: bypasses `_now_fn()` — verify wave-15
      didn't ship a fix; this may still be open)
    - Stale-streaming staleness threshold
    - Cooldown timers (drawdown cooldown, governance change-rate)

13. **Daylight Saving transition**: pre and post DST border. Audit-K closed
    a few; this is a re-test of the same axis on the post-wave-15 code.

### Outbox / queue failures

14. **Outbox backpressure**: large batch claimed, broker slow, lease
    expires before mark_sent. New `_CLAIM_LEASE_SECONDS = 300` from N-C-3 —
    is 5 min sufficient for slowest realistic broker submission? What
    happens if it isn't (re-claim + re-submit)?

15. **Outbox worker death mid-flight**: claimed events, no commit yet. The
    lease bump from wave-12b means status='pending' but next_attempt_at is
    in the future. After the lease expires, the worker re-claims. Verify
    no permanent lockup.

### Streaming / market data

16. **Bar provider returns empty / NaN**: `_passes_liquidity_gate` is fail-closed
    (verified wave 16a). What about feature pipeline — does it fail-closed?
    Drop NaN rows but proceed?

17. **Quote provider mid-tick failure**: `_streaming_provider.get_latest_quote`
    raises. Is the tick loop resilient?

## Output

`artifacts/audit/v5_reports/track_s_stress.md` with:

- Scenario × audit-method × verdict × open-finding-id (if any) table
- Critical-path failure-mode coverage map (each external dep × graceful?)
- "Bugs found: N" + TL;DR

## Constraints

Read-only on production. `docker stats`, `docker logs`, `psql` SELECTs ok.
NO mutation, NO docker rebuild, NO actual partition/kill of running infra.

## Quality bar

Expect 4-8 issues. Especially:
- Missing timeout on a network call
- A path that requires Redis with no fallback
- A state held only in memory that a restart loses
- Race between component-A heartbeat and component-B work

End with a one-paragraph summary: report path, bugs found, most concerning.
