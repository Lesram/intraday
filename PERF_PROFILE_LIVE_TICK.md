# Performance/Latency Profile — `live_tick()`

**Run:** 2026-04-25 weekend sprint, S8
**Branch:** `rc-1.5-curated`
**Method:** cProfile on synthetic-data replay (100 ticks, 6 symbols, 500-bar history) + cross-reference with real-Alpaca replay (2230 ticks, 22 symbols)
**Per-tick (real Alpaca, 22 symbols):** ~1000ms
**Per-tick (synthetic, 6 symbols, instrumented w/ profiler):** ~1624ms (profiler overhead inflates this)

**TL;DR — feature engineering dominates compute.** `ml_features.compute_ml_features()` accounts for ~98% of CPU time per tick. The strategy already uses ThreadPoolExecutor to parallelize feature compute across symbols. With 10s tick interval and ~1s real per-tick time, **we have ~10× headroom** — fine for now. **The optimization opportunity is real but not urgent.**

---

## Headline numbers

| Configuration | Per-tick wall time | Feature share | ML inference share |
|---|---|---|---|
| Real Alpaca, 22 symbols, full brain | ~1000 ms | ~80% | ~10% |
| Synthetic, 6 symbols, profiler-instrumented | ~1624 ms | ~98% | ~negligible (untrained brain) |

10s tick interval, 1s real per-tick = 10× headroom. Comfortable.

## Where time goes (cProfile, top categories)

| Category | Cumulative time | % of total | Notes |
|---|---|---|---|
| `ml_features.compute_ml_features()` | 159.26 s | 98% | 600 calls (100 ticks × 6 symbols), 265 ms/call |
| ThreadPoolExecutor mgmt overhead | ~30 s | ~10% | Thread join/shutdown |
| pandas `rolling._apply` | 92 s | (within feature compute) | Heavy reuse of rolling windows |
| numpy `corrcoef`, `cov` | 45 s | (within feature compute) | Cross-asset features |
| numpy `_mean`, `_var` | 12 s | (within feature compute) | Statistical aggregates |

(Cumulative time exceeds wall time because async/threaded — same wall second can be on multiple stacks.)

## What's slow inside `compute_ml_features`

Top culprits by self time:
- `pandas.DataFrame.__finalize__` and `__init__` — DataFrame creation overhead from heavy slicing
- `pandas.rolling._apply` — rolling window calculations
- `numpy.cov`, `numpy.corrcoef` — for cross-asset / autocorrelation features
- `pd.Series.shift`, `pct_change` — feature primitives

These are general pandas overhead, not specific algorithmic problems.

## Why this matters (and doesn't)

### Why it doesn't matter for Monday

- 1s per tick on 22 symbols means 1/10 of the tick budget.
- Even on a slow Alpaca data day, we're safely inside the 10s window.
- Bar-skip risk is low.
- No code change needed for RC-1.5 / RC-2 / Stage-1 capital readiness.

### Why it could matter later

1. **If we expand the universe to 50+ symbols**, per-tick time scales roughly linearly with feature compute being the bottleneck. At 50 symbols on current code, expected ~2.3s per tick. Still inside 10s, but headroom shrinks.

2. **If we add tick-frequency strategies** (e.g., 1s polling for fast exits), feature compute becomes the constraint.

3. **If the platform graduates to multiple containers** (paper + live + research), each container computes features independently. Sharing a feature-compute service would be ~3× resource win.

## Optimization candidates (RC-3+)

Ranked by effort / impact:

### 1. Incremental feature update (HIGH impact, MEDIUM effort)

`compute_ml_features` recomputes all 79 features over 200 bars every tick. Most features are pure functions of past bars — adding one new bar should only require incrementally updating the latest value.

Approach: cache last-computed feature DataFrame per symbol. On the next tick, only compute features for the new bar (or last K bars to handle backfills). The rolling window math can be done with `df.rolling(...).iloc[-1]` only.

Expected gain: 10-50× speedup on feature compute step → per-tick time drops from 1s to ~50-200ms.

### 2. Reduce feature count (MEDIUM impact, LOW effort)

79 features is a lot for tree-based models. Track 1 found ML correlation = 0.056 — most features may not contribute. A feature-importance pruning to top-30 features could cut feature compute by ~60%.

Approach: in the next retrain, log feature importances. Drop features below 0.5% importance contribution. Re-run.

Expected gain: 2-3× feature compute speedup.

### 3. Cython / numba JIT for hot inner loops (HIGH impact, HIGH effort)

The pandas rolling-apply pattern with custom Python functions is the slowest path. Rewriting as numba `@jit` functions could give 5-10× on those specific stages.

Approach: identify the 3-4 slowest custom rolling functions, port to numba. Keep the rest as-is.

Expected gain: 3-5× on hot rolling-window paths.

### 4. Polars instead of pandas (HIGH impact, HIGH effort, RISKY)

Polars is ~2-5× faster than pandas for the same workload. But it's a massive migration touching every feature engineering line.

Recommendation: not worth it unless we hit a hard performance wall.

## Latency budget for real money

For Stage-1 tiny capital, the only latency-sensitive path is **exit decisions on adverse moves**. If price gaps to -3R between ticks, the engine needs to react fast.

Current behavior: 10s tick interval. If a position goes from -0.5R to -3R within 10s (rare, but possible on news), the engine notices on the next tick. Exit submitted, fills at next bar's open.

**Real-money mitigation (NOT a performance issue, an architecture issue):**
- Pre-position broker stop orders at -1.0R when entering. Alpaca supports this. Then the broker handles fast moves regardless of our tick latency.
- This is the **Exp 6 candidate** flagged in the pyramid_cut deep-dive.

## Verification

Profile output written to `artifacts/live_tick_profile.txt` (gitignored; ephemeral).

Reproducible:
```
./venv/bin/python scripts/profile_live_tick.py
```

(Note: synthetic data + untrained brain. For real-config measurement, run a longer Alpaca-bar replay and time it.)

## Recommendation

**No action for RC-1.5 / RC-2.** Current performance is fine for the 10s tick interval and 22-symbol universe. The optimization candidates above are real but should wait until either:
- Universe expands beyond 30-40 symbols, OR
- Tick interval needs to shrink below 5s (e.g., for tick-aware exits), OR
- Platform graduates to multiple parallel containers

Document this profile run, return to it when one of those triggers.
