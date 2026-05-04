# Track TT v9 — Performance / Latency (NEW LENS)

V8 OO meta-audit observed: 0 of ~278 findings came from performance class. The cycle has been blind to perf regressions; nothing measures tick latency, query plans, or memory growth. **Track TT ships the lens.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `db1a3fc`.

## Method

### 1. Tick latency p99 from logs

If application logs include tick durations:

```
grep -E "tick.*duration|tick.*[0-9]+ms" logs/application.log 2>/dev/null | tail -100 | \
  awk '{ match($0, /[0-9]+\.?[0-9]*\s*ms/); print substr($0, RSTART, RLENGTH) }' | \
  sort -n | awk '
    { a[NR]=$1 }
    END {
      print "n:", NR
      print "p50:", a[int(NR*0.50)]
      print "p95:", a[int(NR*0.95)]
      print "p99:", a[int(NR*0.99)]
      print "max:", a[NR]
    }
  '
```

Goal: tick budget is ~5s (live engine fires every 5s). If p99 > 4s, we're flirting with budget overrun.

### 2. cProfile a single live tick

If safe to enable:

```
./venv/bin/python -c "
import cProfile, pstats, asyncio
from backend.organism.live_engine import OrganismLiveEngine
# ... build engine with mocks ...
async def run():
    profiler = cProfile.Profile()
    profiler.enable()
    await engine.live_tick()
    profiler.disable()
    pstats.Stats(profiler).sort_stats('cumtime').print_stats(20)
asyncio.run(run())
"
```

Identify:
- The top 5 cumulative-time functions.
- Any function called > 1000 times per tick (likely a hot loop).
- Any I/O wait (broker / DB / file).

### 3. Query plan audit

For each `text()` SQL query in backend/, run `EXPLAIN ANALYZE` against the production schema:

```
grep -rn "text(.*SELECT\|text(.*INSERT\|text(.*UPDATE" backend/ --include='*.py' | head -10
```

For each, check:
- Does it have an index supporting the WHERE clause?
- Does it use `LIMIT` to bound result size?
- Is there a `JOIN` on a non-indexed column?

### 4. Memory growth review

Static review of:
- `_history` lists (e.g. `_aggregate_history` in regime, `_strategy_trades` cache, `_tick_telemetry` buffers): are they bounded?
- `_calibration_counts`: 5 bins × 2 ints — bounded.
- `_pending_entry`, `_pending_exit`: bounded by symbol set.
- `_exit_levels`: bounded by open positions.
- Any `defaultdict(list)` that's appended to but never trimmed.

### 5. Allocation hot paths

For each per-tick computation, verify:
- DataFrames are not materializing intermediate copies.
- `pd.Series.iloc[-1]` is preferred over `series.tail(1).iloc[0]`.
- Feature computation doesn't re-create the same DataFrame N times.

### 6. Async cooperative-multitasking review

Each `await` in `_live_tick_inner` is a yield point. Identify:
- Any `await` inside a tight loop (could be N×latency).
- Any `time.sleep()` (synchronous block in async context).
- Any `concurrent.futures.wait()` that could deadlock.

### 7. Container resource usage

```
docker stats intra-api-1 --no-stream
```

Verify:
- CPU% under 50% in steady state.
- Memory growth slope flat over an hour.
- Disk I/O on brain saves: bursty but bounded.

### 8. Database connection pool

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname = 'algotrading';"
```

Verify connection count is well under the pool max (typically 20-50). If too high, sessions are leaking.

## Output

`artifacts/audit/v9_reports/track_tt_performance_latency.md` with:
- Tick latency stats (p50/p95/p99)
- Top 5 cProfile hot paths (if profiled)
- SQL query plan audit results
- Memory bounded-growth review
- Async hot-path review
- Container resource snapshot
- DB connection count

Quality bar: 1-4 findings. End with one-paragraph TL;DR. **Findings here are usually optimization opportunities, not bugs**, but a hot path causing tick budget overrun = High severity.
