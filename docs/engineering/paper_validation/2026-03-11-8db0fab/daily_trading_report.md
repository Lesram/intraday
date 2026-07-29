# Daily Paper Trading Report — 2026-03-11

**SHA:** `8db0fab` | **Mode:** Learning | **Gen:** 0 | **Equity:** $111,612.23

---

## Session Summary

| Metric | Value |
|--------|-------|
| Market status | Regular hours (09:30–16:00 ET) |
| Ticks (logged/estimated) | 95 / ~362 |
| Regime changes | 4 (trending_up → trending_down → high_vol → low_vol) |
| Trades today | **0** |
| Realized PnL today | $0.00 |
| Open positions at close | 0 |
| Stale orders at close | 0 (WMT ghost cancelled at 20:45 UTC) |

## Why Zero Trades

Today was a regime-unstable, low-conviction market day:

1. **Confidence floor not reached** — Best candidate was TSLA at eff_conf=0.22 vs 0.25 gate
2. **Regime instability** — 4 regime changes in 5 hours (trending_up → trending_down → high_vol → low_vol)
3. **Scanner dry** — Market scanner returned zero movers, zero most-actives all day
4. **Breakout/tension signals near zero** — Most candidates scored eff_conf=0.00

This is the organism working as designed: refusing to enter positions without edge.

## Gate Pipeline (362 ticks)

```
Universe (22 symbols/tick)
  → Alpha/Breakout candidates: ~27 logged reaching confidence eval
    → Confidence gate (0.25 floor): 0 passed
      → All downstream gates: 0 candidates
        → Orders: 0
```

## Top Rejected Candidates

| Symbol | eff_conf | Regime | Verdict |
|--------|----------|--------|---------|
| TSLA | 0.22 | trending_down | Expected |
| XLE | 0.21 | trending_down | Expected |
| NVDA | 0.17 | trending_down | Expected |
| TSLA | 0.15 | high_vol | Expected |
| XLE | 0.14 | high_vol | Expected |
| GOOGL | 0.13 | high_vol | Expected |
| SNOW | 0.00 | trending_up | Expected |

**Selectivity verdict:** HEALTHY_SELECTIVITY

## Anomalies

| Severity | Count | Details |
|----------|-------|---------|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| LOW | 3 | Missing brain CSV fields, empty realized_trades table, async API bug |
| INFO | 3 | Alpha weight sum, 721s tick gap, post-close backoff |

## Lifetime Context

| Metric | Value |
|--------|-------|
| Total trades | 142 |
| Cumulative PnL | -$944.74 |
| Win rate | 40.1% |
| Sharpe | -3.043 (current run) |
| Progress to evolution | 142/300 trades |
| Equity drawdown | -0.84% |

## Tomorrow Recommendation

**GO_UNCHANGED** — No config changes, no rebuilds, no code patches. Verify containers healthy at open.
