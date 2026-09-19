# Track TT3 v11 — Performance Phase 3

V10 TT-2 added the tick watchdog. **TT3 profiles a real tick under realistic load + identifies remaining hot paths.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`.

## Method

### 1. Live tick latency since rebuild

```
docker logs intra-api-1 --since 2h 2>&1 | grep -E "tick.*duration|Live tick.*[0-9]+s|Tick complete" | head -50
```

Compute p50, p95, p99 from log lines. Compare to V10 baseline (p50=2.6s, p95=7.5s, p99=13.0s).

### 2. Watchdog timeouts (TT-2)

```
docker logs intra-api-1 --since 24h 2>&1 | grep -E "TT-2.*watchdog FIRED" | wc -l
```

If > 0 since deploy, the watchdog is engaging. Investigate top hits.

### 3. cProfile a synthetic tick

If the test harness allows:
```
./venv/bin/python -c "
import cProfile, pstats, asyncio
# Build minimal engine with mocks
profiler = cProfile.Profile()
profiler.enable()
# run a single tick
profiler.disable()
pstats.Stats(profiler).sort_stats('cumtime').print_stats(20)
"
```

Top-5 cumulative-time functions = optimization targets.

### 4. SQL query latency audit

For the top SQL queries in `backend/`, run EXPLAIN ANALYZE against a sample:
```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "EXPLAIN ANALYZE SELECT * FROM orders WHERE status='filled' ORDER BY submitted_at DESC LIMIT 10;"
```

Look for Seq Scan on big tables. Compare to V10 TT-3 finding (Seq Scan on `attributes->>'source'`).

### 5. TT-4 async rate-limit verify

`grep -n "self._rate_limit()" backend/data/alpaca_client.py` should only show 2 sites (the sync ones); 4 should be `await self._async_rate_limit()`.

### 6. TT-5 list bounds verify

`MomentumPyramider._pyramid_count` is now telemetered (wave-53 DD4-4). Are any new unbounded lists since V10?

### 7. Memory growth over an hour

```
docker stats intra-api-1 --no-stream
```

Note current memory; check again in 30 min. Slope?

### 8. DB connection pool

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*), state FROM pg_stat_activity WHERE datname='algotrading' GROUP BY state;"
```

Should be < 10. If > 20, sessions are leaking.

### 9. Async task accumulation

```
docker exec intra-api-1 python -c "
import asyncio
loop = asyncio.get_event_loop()
print('pending tasks:', len(asyncio.all_tasks(loop)))
" 2>&1 | tail -3
```

(May fail if uvicorn doesn't expose introspection; document if so.)

### 10. Hot-path optimizations to ship in V12

Based on cProfile + EXPLAIN, propose top 3 optimizations.

## Output

`artifacts/audit/v11_reports/track_tt3_performance_phase3.md` with metrics + findings.

Quality bar: 1-3 findings.
