# Daily Trading Report -- 2026-05-08

**Deployed SHA**: `bff4e20`
**Paper Validation**: PASS
**Strategy Quality**: FAIL

## Summary
| Metric | Value |
|--------|-------|
| Total trades | 12 |
| Realized PnL | $-23.79 |
| Win rate | 16.67% |
| Avg win | $2.43 |
| Avg loss | $-2.87 |
| Payoff ratio | 0.8485 |
| Unrealized PnL | N/A (not exposed by engine) |
| Exploration count | 0 |

## Exit Breakdown
| Exit Reason | Count | Total PnL | Avg PnL | Win Rate |
|-------------|-------|-----------|---------|----------|
| failure_to_follow | 4 | $-4.62 | $-1.16 | 0.00% |
| max_holding_period | 2 | $4.86 | $2.43 | 100.00% |
| pyramid_cut_full_at_-1.9R | 1 | $-0.58 | $-0.58 | 0.00% |
| pyramid_cut_full_at_-2.3R | 1 | $-10.71 | $-10.71 | 0.00% |
| stop_loss | 1 | $-1.96 | $-1.96 | 0.00% |
| trailing_stop | 3 | $-10.78 | $-3.59 | 0.00% |

## Entry Source Breakdown
| Source | Count | Total PnL | Avg PnL | Win Rate | Avg Conf |
|--------|-------|-----------|---------|----------|----------|
| alpha+breakout | 12 | $-23.79 | $-1.98 | 16.67% | 0.629 |

## Regime Distribution at Entry
| Regime | Count |
|--------|-------|
| chop | 7 |
| trending_down | 4 |
| trending_up | 1 |

## Top Winners
| Symbol | PnL | Exit | Source | Conf |
|--------|-----|------|--------|------|
| IWM | $2.54 | max_holding_period | alpha+breakout | 0.563 |
| IWM | $2.32 | max_holding_period | alpha+breakout | 0.618 |
| PSQ | $-0.38 | failure_to_follow | alpha+breakout | 0.704 |
| QQQ | $-0.46 | trailing_stop | alpha+breakout | 0.551 |
| QQQ | $-0.58 | pyramid_cut_full_at_-1.9R | alpha+breakout | 0.764 |

## Top Losers
| Symbol | PnL | Exit | Source | Conf |
|--------|-----|------|--------|------|
| CRM | $-10.71 | pyramid_cut_full_at_-2.3R | alpha+breakout | 0.596 |
| AMD | $-7.53 | trailing_stop | alpha+breakout | 0.701 |
| AMD | $-2.79 | trailing_stop | alpha+breakout | 0.556 |
| SH | $-1.96 | stop_loss | alpha+breakout | 0.601 |
| NVDA | $-1.53 | failure_to_follow | alpha+breakout | 0.625 |
