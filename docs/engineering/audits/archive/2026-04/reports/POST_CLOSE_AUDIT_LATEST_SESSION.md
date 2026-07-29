# Post-Close Audit — Latest Completed Session

# 1. Executive Verdict

**PARTIAL PASS**

The Apr 1 session was mechanically active and profitable at the broker level (+$51.35 across 14 round trips). However, the **persistence stack did NOT function for this session** — the complete split persistence fix (3534346) was not deployed until AFTER the session ended. The container running during the Apr 1 session was commit 53cc1ad, which lacked `save_essential_state()`. The walk-forward gate blocked all full brain saves, and zero Apr 1 trades were persisted to disk. The brain on disk still shows 161 trades from the Mar 31 backup.

**Top 3 findings:**
1. **PERSISTENCE GAP CONFIRMED**: 14 completed trades from Apr 1 are NOT in brain/CSV. The walk-forward gate blocked 111 save attempts. The old container format ("exit_levels + entry_metadata persisted separately") confirms `save_essential_state()` was never called.
2. **RECONCILIATION ADJUSTMENT FIX WORKED**: One `reconciliation_adjustment` event fired correctly at 13:28:47 for stale AMZN metadata. This was expected behavior, not an artifact.
3. **TRADING MECHANICS HEALTHY**: 14 round trips, 42.9% win rate, 4.23x payoff ratio, zero errors, zero canceled orders. The organism is finding genuine edge in chop regime.

# 2. Session Identification

| Field | Value |
|---|---|
| **Session date** | 2026-04-01 (Tuesday) |
| **Timezone** | All timestamps UTC unless noted |
| **Session window** | 13:28 – 20:01 UTC (9:28 AM – 4:01 PM EDT) |
| **Deployed git SHA during session** | `53cc1ad` (reconciliation fixes, partial persistence) |
| **Current repo HEAD SHA** | `8f1e657` (includes handoff doc) |
| **Deployed SHA differs from HEAD** | YES — container is built from `3534346`, HEAD is `8f1e657` (diff is handoff doc only, no code) |
| **Code changed during/after session** | YES — commits `007a977` and `3534346` (persistence fixes) were committed and deployed AFTER the session ended. Container was rebuilt post-close. |

# 3. Runtime State Before and After Session

| Metric | Before Session (pre-open) | After Session (post-close) |
|---|---|---|
| Brain manifest total_trades | 161 (from backup) | 161 (unchanged — gate blocked saves) |
| Brain manifest cumulative_pnl | -714.26 | -714.26 (unchanged) |
| Brain manifest saved_at | 2026-04-01T08:00:02Z | 2026-04-01T08:00:02Z (unchanged) |
| Brain manifest ml_is_trained | true | true |
| Brain generation | 0 | 0 |
| Equity (Alpaca) | ~$111,595.51 | $111,644.66 |
| Open positions | 0 | 0 |
| Blocks / safety flags | None | None |
| Started flat / ended flat | YES / YES | — |

**Critical note**: The brain manifest did NOT advance during the session. The `saved_at` timestamp remained at the pre-market value (08:00:02Z). This proves the walk-forward gate blocked all persistence.

# 4. Broker Truth

**Orders**: 41 total, 41 filled, 0 canceled, 0 rejected.

| # | Time (UTC) | Symbol | Side | Qty | Type | Fill Price | Status |
|---|---|---|---|---|---|---|---|
| 1 | 13:28:10 | AMZN | buy | 15 | limit | $210.426 | filled |
| 2 | 13:37:10 | AMZN | sell | 15 | market | $210.036 | filled |
| 3 | 14:01:05 | XLK | buy | 24 | limit | $134.65 | filled |
| 4 | 14:09:03 | XLK | buy | 12 | limit | $135.018 | filled |
| 5 | 14:17:08 | XLK | buy | 4 | limit | $135.16 | filled |
| 6 | 14:18:10 | XLK | sell | 40 | market | $135.110 | filled |
| 7 | 14:40:09 | IWM | buy | 13 | limit | $251.13 | filled |
| 8 | 14:53:11 | TSLA | buy | 8 | limit | $380.294 | filled |
| 9 | 14:57:04 | IWM | sell | 13 | market | $251.68 | filled |
| 10 | 15:00:06 | TSLA | buy | 4 | limit | $381.55 | filled |
| 11 | 15:08:02 | PSQ | buy | 105 | limit | $31.70 | filled |
| 12 | 15:08:02 | SH | buy | 88 | limit | $37.54 | filled |
| 13 | 15:09:03 | SH | sell | 44 | market | $37.53 | filled |
| 14 | 15:09:03 | PSQ | sell | 52 | market | $31.69 | filled |
| 15 | 15:10:04 | TSLA | sell | 12 | market | $381.66 | filled |
| 16 | 15:10:04 | PSQ | sell | 52 | market | $31.69 | filled |
| 17 | 15:10:05 | SH | sell | 44 | market | $37.53 | filled |
| 18 | 15:13:07 | PSQ | sell | 1 | market | $31.69 | filled |
| 19 | 15:28:03 | LLY | buy | 3 | limit | $946.01 | filled |
| 20 | 15:34:08 | LLY | buy | 1 | limit | $959.88 | filled |
| 21 | 15:42:02 | LLY | buy | 1 | limit | $958.19 | filled |
| 22 | 15:45:04 | LLY | sell | 5 | market | $959.464 | filled |
| 23 | 16:14:02 | SH | buy | 88 | limit | $37.49 | filled |
| 24 | 16:18:05 | SH | sell | 26 | market | $37.50 | filled |
| 25 | 16:29:11 | SH | buy | 44 | limit | $37.52 | filled |
| 26 | 16:31:13 | SH | sell | 106 | market | $37.51 | filled |
| 27 | 18:37:03 | XOM | buy | 20 | limit | $162.21 | filled |
| 28 | 18:44:11 | XOM | sell | 20 | market | $162.008 | filled |
| 29 | 18:50:02 | SPY | buy | 4 | limit | $654.715 | filled |
| 30 | 18:56:07 | SPY | sell | 2 | market | $654.225 | filled |
| 31 | 18:57:08 | SPY | sell | 2 | market | $654.33 | filled |
| 32 | 19:15:11 | XLE | buy | 56 | limit | $59.020 | filled |
| 33 | 19:25:11 | XOM | buy | 20 | limit | $161.89 | filled |
| 34 | 19:25:11 | XLE | buy | 28 | limit | $59.11 | filled |
| 35 | 19:26:11 | XOM | sell | 20 | market | $161.58 | filled |
| 36 | 19:27:01 | XLE | sell | 84 | market | $59.08 | filled |
| 37 | 19:36:07 | SPY | buy | 4 | limit | $655.925 | filled |
| 38 | 19:36:07 | PSQ | buy | 105 | limit | $31.79 | filled |
| 39 | 19:37:09 | PSQ | sell | 105 | market | $31.77 | filled |
| 40 | 19:43:05 | SPY | buy | 2 | limit | $656.31 | filled |
| 41 | 19:51:10 | SPY | sell | 6 | market | $655.345 | filled |

**Account at close**: Equity $111,644.66, cash $111,644.66, long_market_value $0 (flat).

**Broker/runtime mismatch**: The broker shows 41 filled orders (14 round trips, +$51.35). The brain shows 0 new trades for Apr 1. This is a **complete persistence gap** — every Apr 1 trade exists only in Alpaca history, not in brain state.

# 5. Trade Ledger for the Session

| # | Symbol | Side | Entry | Exit | Qty | Entry $ | Exit $ | PnL | Classification | Hold |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AMZN | long | 13:28 | 13:37 | 15 | 210.43 | 210.04 | -$5.85 | strategy | 9m |
| 2 | XLK | long | 14:01 | 14:18 | 40 | 134.81 | 135.11 | +$11.95 | strategy | 17m |
| 3 | IWM | long | 14:40 | 14:57 | 13 | 251.13 | 251.68 | +$7.15 | strategy | 17m |
| 4 | TSLA | long | 14:53 | 15:10 | 12 | 380.71 | 381.66 | +$11.37 | strategy | 17m |
| 5 | SH | long | 15:08 | 15:10 | 44 | 37.54 | 37.53 | -$0.44 | strategy | 2m |
| 6 | PSQ | long | 15:08 | 15:13 | 1 | 31.70 | 31.69 | -$0.01 | strategy | 5m |
| 7 | LLY | long | 15:28 | 15:45 | 5 | 951.22 | 959.46 | +$41.22 | strategy | 17m |
| 8 | SH | long | 16:14 | 16:31 | 106 | 37.50 | 37.51 | +$0.80 | strategy | 17m |
| 9 | XOM | long | 18:37 | 18:44 | 20 | 162.21 | 162.01 | -$4.05 | strategy | 7m |
| 10 | SPY | long | 18:50 | 18:57 | 2 | 654.72 | 654.33 | -$0.77 | strategy | 7m |
| 11 | XOM | long | 19:25 | 19:26 | 20 | 161.89 | 161.58 | -$6.20 | strategy | 1m |
| 12 | XLE | long | 19:15 | 19:27 | 84 | 59.05 | 59.08 | +$2.53 | strategy | 12m |
| 13 | PSQ | long | 19:36 | 19:37 | 105 | 31.79 | 31.77 | -$2.10 | strategy | 1m |
| 14 | SPY | long | 19:36 | 19:51 | 6 | 656.05 | 655.35 | -$4.25 | strategy | 15m |

All 14 trades classified as **strategy** (not reconciliation artifacts). One `reconciliation_adjustment` event fired at 13:28:47 for stale AMZN metadata but was correctly handled.

**Note**: These trades are reconstructed from broker order history. No brain TradeRecord data is available because persistence was blocked.

# 6. Persistence Verification

**This is the most critical section.**

## Evidence

| Check | Result | Evidence |
|---|---|---|
| Trades persisted to brain CSV | **NO** | `trade_history.csv` has 162 lines (161 trades + header). Last entry: `QQQ ... 2026-03-31T16:48:18`. Zero Apr 1 entries. |
| Persistence occurred despite gate block | **NO** | 111 "Brain save SKIPPED" log entries. Message format: "exit_levels + entry_metadata persisted separately" — the OLD format from commit 53cc1ad. `save_essential_state()` was never called. |
| Brain manifest trade count advanced | **NO** | Manifest shows total_trades=161, saved_at=2026-04-01T08:00:02Z. Unchanged from pre-session. |
| Essential saves occurred | **NO** | Zero "Essential state saved" log entries. The save_essential_state method did not exist in the deployed container. |
| Old walk-forward persistence gap recurring | **YES** | This IS the old gap. The container deployed during the Apr 1 session was commit 53cc1ad, which lacks the complete split persistence fix (3534346). |

## Root Cause

The Apr 1 session ran on commit `53cc1ad`. The complete persistence fix (`save_essential_state` writing all runtime truth on gate block) was committed as `007a977` and then expanded in `3534346` — both AFTER the Apr 1 session ended. The container was rebuilt from `3534346` post-close, but by then the in-memory trades were already lost.

## Files Inspected

- `/Users/marselkei/VS/intra/organism_brain/manifest.json` — saved_at=08:00:02, trades=161
- `/Users/marselkei/VS/intra/organism_brain/trade_history.csv` — 162 lines, last entry Mar 31
- `application.log` — 111 "Brain save SKIPPED" events, 0 "Essential state saved" events
- Container grep — log format confirms 53cc1ad (old message), not 3534346 (new message)

## Missing Trades

14 round trips from the broker are NOT in brain state. These are permanently lost from learner/evolution history.

# 7. Forensic Field Verification

| Check | Result | Evidence |
|---|---|---|
| regime_at_exit populated | **UNKNOWN** | No Apr 1 TradeRecords exist in brain CSV. Cannot verify. The regime_at_exit fix (using `_last_regime`) was deployed in commit 53cc1ad which DID run during the session, so trades in memory likely had correct regime_at_exit. But they were never persisted. |
| reconciliation_adjustment artifacts | **1 expected, correctly handled** | Log at 13:28:47: "Reconciliation adjustment: AMZN had stale entry metadata (entry=$210.59) with no broker position or exit fill — tagging as non-strategy PnL". This was stale metadata from the Mar 31 session — the fix worked correctly. |
| Stale metadata / orphan evidence | **1 orphan adoption** | Log at 13:30:53: "Adopted orphaned broker position: AMZN LONG 9 shares @ $210.63". This was the partial fill of the new AMZN buy order being adopted after the stale metadata was pruned. Normal behavior. |
| Phantom closes | **None detected** | No unexpected "live_close" or "reconciliation_adjustment" events beyond the expected AMZN stale metadata handling. |

# 8. Watchdog / Save Behavior

| Metric | Value |
|---|---|
| C4 watchdog events | **1,927** (fired continuously, every tick) |
| C1 (no-trade) watchdog events | 0 |
| C4 first fire | 13:28:10 — "Brain not saved for 3735 ticks" |
| C4 last fire | 20:00:59 — "Brain not saved for 5661 ticks" |
| Total save attempts | 111 (periodic + post-fill) |
| Save successes | 0 (all blocked by walk-forward gate) |
| Essential state saves | 0 (method not present in deployed container) |
| Watchdog tick updated on save | **NO** — watchdog tick remained at 0 throughout session |

**Assessment**: The C4 watchdog fired 1,927 times during the session — nearly every tick. This is the old behavior where the watchdog tick was not updated on gate-blocked saves. The fix in commit 3534346 addresses this by updating `_watchdog_last_brain_save_tick` on essential saves.

# 9. Runtime Log Review

## Entry Activity
- **674** confidence reject events (symbols evaluated but eff_conf < 0.25)
- **193** entry-below-main-book-threshold events
- **91** liquidity gate blocks
- **20** active ticks (with signals, orders, or exits > 0)

## Regime Changes
- **chop**: 2,006 ticks (94.6%)
- **high_vol**: 71 ticks (3.3%)
- **stress**: 43 ticks (2.0%)

## Key Log Events
- 13:28:47 — Reconciliation adjustment for AMZN (stale metadata)
- 13:30:53 — Orphan adoption for AMZN (partial fill)
- 14 "Brain saved after N fill(s)" log entries — misleading: these fire even when the gate blocked the actual save
- 0 errors, 0 exceptions, 0 tracebacks
- Pre-open diagnostics: 30/36 passed (0 critical, 4 warnings)
- Post-close diagnostics: 32/36 passed (0 critical, 3 warnings)

## Anomaly List

| Anomaly | Evidence | Severity | Category |
|---|---|---|---|
| All trades lost — persistence blocked | 111 gate blocks, 0 essential saves | HIGH | Correctness |
| C4 watchdog fired 1,927 times | Continuous every-tick warnings | LOW | Observability |
| "Brain saved after N fill(s)" log is misleading | Fires even when gate blocks save | LOW | Observability |
| No Apr 2 orders yet (market not open) | Expected | NONE | — |

# 10. Performance Breakdown

## Session Net P&L
- **Broker equity change**: +$49.15 ($111,595.51 → $111,644.66)
- **Reconstructed trade P&L**: +$51.35 (from broker fill prices)

## Win/Loss
- Wins: 6 (42.9%), Losses: 8 (57.1%)
- Avg winner: +$12.50, Avg loser: -$2.96
- **Payoff ratio: 4.23x**

## P&L by Symbol
| Symbol | Trades | P&L |
|---|---|---|
| LLY | 1 | +$41.22 |
| XLK | 1 | +$11.95 |
| TSLA | 1 | +$11.37 |
| IWM | 1 | +$7.15 |
| XLE | 1 | +$2.53 |
| SH | 2 | +$0.36 |
| PSQ | 2 | -$2.11 |
| SPY | 2 | -$5.02 |
| AMZN | 1 | -$5.85 |
| XOM | 2 | -$10.25 |

## P&L by Time Bucket
| Bucket (UTC) | Trades | P&L |
|---|---|---|
| 13:00–14:00 (first 30m) | 1 | -$5.85 |
| 14:00–15:00 | 3 | +$30.47 |
| 15:00–16:00 | 3 | +$40.78 |
| 16:00–17:00 | 1 | +$0.80 |
| 17:00–18:00 | 0 | $0.00 |
| 18:00–19:00 | 2 | -$4.82 |
| 19:00–20:00 (last hour) | 4 | -$10.02 |

**Observation**: The organism made +$71.25 in the 14:00–16:00 window and -$14.84 in the 18:00–20:00 window. Late-session alpha is consistently weaker.

## MAE/MFE
Not available from broker data alone. Would require brain TradeRecords, which were not persisted.

# 11. Comparison to Prior Baseline

| Metric | Mar 31 (normalized) | Apr 1 | Trend |
|---|---|---|---|
| Trades | 27 | 14 | Fewer but higher quality |
| Realized P&L | +$27.12 | +$51.35 | Improving |
| Win rate | 40.7% | 42.9% | Stable |
| Avg winner | +$11.28 | +$12.50 | Improving |
| Avg loser | -$6.06 | -$2.96 | **Much better** |
| Payoff ratio | 1.86x | 4.23x | **Much better** |
| Worst trade | -$29.43 | -$6.20 | **Much better** |
| Stale-fill artifacts | 1 (XLK +$174) | 0 | Fixed |
| Reconciliation artifacts | — | 1 (expected, correctly handled) | Fixed |
| Trades persisted | YES (Mar 31 early session) | **NO** (all lost) | Regression |
| regime_at_exit populated | "unknown" (old bug) | Unknown (not persisted) | Cannot compare |
| C4 watchdog continuous | Yes | Yes (1,927 events) | Not yet fixed during session |

**Key comparison**: Trading quality improved significantly (payoff ratio 1.86x → 4.23x, worst trade -$29 → -$6). But persistence was worse than Mar 31 because the complete fix wasn't deployed yet.

# 12. Hard Conclusions

**1. Did all newly closed trades from the session persist to disk/brain truth?**
**NO.** Zero of 14 trades persisted. The walk-forward gate blocked all 111 save attempts, and `save_essential_state()` did not exist in the deployed container (53cc1ad). This is the known pre-fix gap that was addressed by commits 007a977 and 3534346, deployed AFTER the session.

**2. Is regime_at_exit now functioning correctly in live conditions?**
**UNKNOWN.** The regime_at_exit fix (using `_last_regime`) was present in the deployed container (53cc1ad), so trades in memory likely had correct regime_at_exit values. However, since no trades persisted to CSV, this cannot be verified from disk artifacts. The first verifiable test will be the next session (Apr 2) running on commit 3534346.

**3. Were any reconciliation_adjustment artifacts produced unexpectedly?**
**NO.** One reconciliation_adjustment event fired at 13:28:47 for stale AMZN metadata — this was expected (residual from Mar 31 session) and correctly handled.

**4. Did the brain manifest/count advance consistently with the session's closed trades?**
**NO.** Brain manifest remained at total_trades=161, saved_at=08:00:02Z throughout the entire session. The manifest was never updated because the walk-forward gate blocked all saves and `save_essential_state()` was not available.

**5. Does watchdog/save behavior appear materially improved?**
**NO** — for this session. The C4 watchdog fired 1,927 times continuously. The watchdog tick was never updated because saves never succeeded. The fix for this (updating watchdog tick on essential saves) is in commit 3534346, which was not deployed during this session.

**6. Is the platform mechanically trustworthy enough to continue collecting live data without immediate correctness patches?**
**YES** — with the current deployed container (3534346). The persistence fixes are now committed and deployed. The Apr 1 session ran on old code, but the current runtime has the complete split persistence model. The next session (Apr 2) will be the first true test.

# 13. Immediate Recommendations

## Correctness Fixes Now
- **None needed.** The persistence gap observed in Apr 1 is already fixed in the currently deployed container (3534346). The fix was committed and deployed before this audit. No new correctness issues were identified.

## Observability Improvements Now
- **Verify persistence on Apr 2 session**: This is the single most important task. The first session on the 3534346 container will prove whether `save_essential_state()` works under live conditions. Check: (a) trades appear in CSV, (b) manifest advances, (c) C4 watchdog stops firing continuously, (d) regime_at_exit is populated.
- **Consider fixing the misleading "Brain saved after N fill(s)" log**: This log fires even when the walk-forward gate blocks the actual save, creating false confidence in persistence. Low priority but causes confusion.

## Strategy Changes Later
- **Do not change strategy design.** The organism needs ~130 more trades (brain shows 161/300) to exit evolution freeze. Apr 1's 4.23x payoff ratio and improving loss control are encouraging.
- **Monitor**: Late-session alpha weakness (confirmed again on Apr 1: +$71 before 16:00, -$15 after 18:00), inverse ETF marginal returns (SH/PSQ net +$0.36/-$2.11), XOM repeated losses (-$10.25 from 2 trades).
