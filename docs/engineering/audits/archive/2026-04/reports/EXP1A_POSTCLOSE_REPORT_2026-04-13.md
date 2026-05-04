# Experiment 1A — Post-Close Observation Report: 2026-04-13 (Monday)

**Session**: Mon Apr 13, first Exp1A observation session
**Container**: ab54b2f (Exp1A live), healthy
**Brain**: gen=53, trades=230 (+16 today), pnl=-535.62
**Equity**: $111,551.86 → $111,526.61 (−$25.25)
**Positions at close**: flat

## Exp1A gate activity

| Metric | Value |
|---|---|
| **Pyramid_cut suppressions (Exp1A fires)** | **4** |
| Symbols suppressed | XOM (1), TSLA (1), AMZN (2) |

### Suppression detail
| Symbol | Bars held | R-multiple | Unrealized | Reason suppressed |
|---|---:|---:|---:|---|
| XOM | 9/10 | -0.3R | -$3.87 | cut_full_at_-2.5R |
| TSLA | 9/10 | 0.1R | -$3.14 | cut_full_at_-1.6R |
| AMZN | 4/10 | -0.6R | -$2.38 | cut_full_at_-1.3R |
| AMZN | 7/10 | -0.6R | -$2.17 | cut_full_at_-1.2R |

**XOM suppression outcome**: The XOM trade was at -$3.87 unrealized at bar 9 when the cut was suppressed. It exited at bar 10 via pyramid_cut at -$1.38. **The suppression saved $2.49 on this trade** (would have locked in -$3.87, instead recovered to -$1.38).

## Core metrics vs baseline

| Metric | Baseline (Apr 7-10) | Today (Apr 13) | Delta | Assessment |
|---|---:|---:|---|---|
| Trades | 32 (4 days) | 16 (1 day) | — | Higher activity |
| Pyramid_cut % | 75% | **50%** | **↓25pp** | ✅ Significant reduction |
| Timeout/max_hold % | 16% | **12%** | ~same | — |
| Stop_loss % | 9% | **12%** | ~same | — |
| Win rate | 18.8% | **18.8%** | = | No change yet |
| Expectancy/trade | -$1.92 | **-$1.36** | **↑$0.56** | ✅ Improving |
| Avg hold time | 550s | **746s** | **↑196s** | ✅ Trades held longer |
| Worst loss | -$12.69 | **-$8.36** | ↑$4.33 | ✅ Smaller worst loss |
| Net PnL | -$61.37/4d | -$21.70/1d | — | Still negative |

## Today's exit breakdown

| Exit type | Count | % | PnL | Win rate | Baseline % |
|---|---:|---:|---:|---:|---:|
| **pyramid_cut** | **8** | **50%** | -$15.89 | 0% | 75% |
| failure_to_follow | 2 | 12% | -$2.13 | 0% | — |
| trailing_stop | 2 | 12% | -$1.66 | 0% | — |
| stop_loss | 2 | 12% | -$8.20 | 50% | 9% |
| **timeout/max_hold** | **2** | **12%** | **+$6.17** | **100%** | 16% |

**Key pattern holds**: timeout/max_hold exits are STILL 100% winners (+$6.17 from 2 trades). Pyramid_cuts are STILL 0% winners. But pyramid_cut share dropped from 75% to 50%.

**New exit types today**: failure_to_follow (2 trades, both losers) and trailing_stop (2 trades, both losers) appeared as trades held longer. FTF fires after the min-hold gate expires (bars 12-24). Trailing stops fire on trades that went green then reversed.

## Symbol performance

| Symbol | Trades | PnL | Win rate |
|---|---:|---:|---:|
| NVDA | 2 | -$9.44 | 0% |
| XOM | 2 | -$4.41 | 0% |
| QQQ | 3 | -$4.06 | 33% |
| AMZN | 2 | -$2.71 | 0% |
| TSLA | 1 | -$2.58 | 0% |
| MSFT | 2 | -$2.23 | 0% |
| AAPL | 1 | -$0.95 | 0% |
| **XLK** | **3** | **+$4.68** | **67%** | 

**XLK is the standout**: 3 trades, 2 winners (+$1.53 and +$4.64 both via max_holding_period at 30 bars), 1 loser. Both winners were HELD to timeout — further evidence that holding works.

**No PSQ/SH trades today** — inverse ETFs didn't enter. Good (they're 0% win rate in chop historically).

## Notable trades

**Best trade**: XLK +$4.64, held 30 bars (1742s), exited via max_holding_period. MFE was $6.48 — captured 72% of maximum favorable excursion. This is the kind of trade Exp1A is designed to protect.

**Worst trade**: NVDA -$8.36, held only 6 bars (379s), exited via stop_loss. MFE was $0.00 — never went green. This was a genuine bad entry, not an exit timing problem. Stop_loss worked correctly.

**Most interesting**: NVDA -$1.08, held 28 bars (1622s), MFE was **$13.81** but closed at -$1.08 via trailing_stop. This trade captured 0% of a $13.81 favorable excursion. The trailing stop gave back all the gains. This is a TRAILING STOP problem, not a pyramid_cut problem.

## Regime

| Regime | Ticks | % |
|---|---:|---:|
| chop | 1367 | 85% |
| trending_up | 198 | 12% |
| high_vol | 51 | 3% |

More diverse than the Apr 7-10 baseline (which was 97% chop). 12% trending_up is the first significant non-chop activity.

## Success criteria check

| Criterion | Threshold | Today | Status |
|---|---|---|---|
| Win rate improvement | >25% | 18.8% | ⏳ PENDING (same as baseline) |
| Expectancy improvement | >-$0.50 | -$1.36 | ⏳ IMPROVING (+$0.56 vs baseline) |
| Suppression events | >10 total | 4 | ⏳ PENDING |
| Max single-trade loss | < -$25 | -$8.36 | ✅ PASS |

## Assessment

**Exp1A is showing directional improvement but hasn't broken through yet.** The 10-bar min-hold successfully reduced pyramid_cut exits from 75% to 50% and improved expectancy from -$1.92 to -$1.36 per trade. Average hold time increased from 550s to 746s. The XOM suppression demonstrably saved $2.49.

But win rate hasn't moved (still 18.8%) because the trades that survive the min-hold gate are now exiting via OTHER losing mechanisms (failure_to_follow at 12 bars, trailing_stop on reversals). The exits are shifting, not disappearing.

The NVDA trailing_stop trade ($13.81 MFE captured at $0.00) reveals a NEW problem: the trailing stop is too tight and gives back large gains. This was invisible in the baseline because trades were cut before reaching trailing_stop territory.

## Recommendation

**Continue observation unchanged.** One session is insufficient to judge. Need 2-3 more sessions (30+ trades) for statistical power. The directional signals are positive (pyramid_cut % down, expectancy up, hold time up) but win rate is flat, suggesting the exit problem extends beyond pyramid_cut into trailing_stop and FTF as well.
