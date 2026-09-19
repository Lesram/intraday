# Intra Platform — Full Daily Report
## Date: 2026-03-12 (Thursday)
## HEAD SHA: 8db0fab
## Report generated: ~2026-03-12T20:00 UTC

---

# 1. EXECUTIVE SUMMARY

**Another zero-trade day.** The organism ran 715+ ticks across the full session. All 27+ candidates were rejected at the confidence gate (max eff_conf observed: 0.18 for WMT). Zero orders submitted. This is the **second consecutive zero-trade day** (following 2026-03-11).

**Market context:** Broad sell-off day. SPY -1.52%, QQQ -1.72%, IWM -2.15%. Tech led losses (TSLA -3.14%, AMD -3.46%, META -2.55%). Defensive/value names outperformed (CRM +2.65%, WMT +1.49%, XOM +1.29%, XLE +0.93%). Inverse ETFs SH +1.58%, PSQ +1.76%.

**Verdict:** The zero-trade outcome was again likely HEALTHY given the sell-off environment — long-only in a down tape means staying out was protective. However, two consecutive zero-trade days while defensives and inverse ETFs rallied exposes a structural gap: the organism cannot capitalize on its own inverse ETF universe members (SH, PSQ) or defensive rotations.

---

# 2. INFRASTRUCTURE STATUS

| Component | Status |
|-----------|--------|
| Branch | `main` |
| HEAD | `8db0fab` |
| Docker containers | 3/3 healthy (api, db, redis) |
| API | Reachable (port 8000) |
| Engine running | Yes |
| Tick count | 715 (in log buffer: 46 visible) |
| Tick interval | 10s |
| Last tick | 2026-03-12T19:56:53 UTC |
| Regime at close | `trending_up` (likely stale — market was selling off) |
| Learning mode | True |
| ML trained | False |
| Evolution frozen | Yes (158 < 300 threshold) |
| Scanner scans | 105 |
| Scanner candidates produced | 0 |

### Docker Health
- `intra-api-1`: Up 23 hours (healthy)
- `intra-redis-1`: Up 23 hours (healthy)
- `trading_platform_db_paper`: Up 23 hours (healthy)

---

# 3. ALPACA ACCOUNT

| Metric | Value |
|--------|-------|
| Equity | $111,612.21 |
| Cash | $111,612.21 |
| Buying power | $446,448.84 |
| Long market value | $0 |
| Short market value | $0 |
| Status | ACTIVE |
| PDT flag | True |
| Day trade count | 16 |

**No positions held. Fully cash.**

---

# 4. BRAIN STATE

| Metric | Value |
|--------|-------|
| Generation | 0 |
| Total runs | 65-69 (manifest says 69, API says 65) |
| Total trades | 158 (API), 142 (manifest — not yet synced) |
| Cumulative PnL | -$1,008.77 (API), -$944.74 (manifest) |
| Win rate | 43.04% |
| Winning trades | 68 |
| Losing trades | 89 |
| Avg win | +$17.70 |
| Avg loss | -$24.86 |
| Peak equity | $111,612.21 |
| ML trained | False |

### PnL Trajectory
- Start of paper trading: ~$112,620 effective starting equity
- Current: $111,612.21
- Drawdown from start: ~$1,008.77 (-0.90%)

### Win/Loss Math
- Expected value per trade: (0.43 × $17.70) - (0.57 × $24.86) = $7.61 - $14.17 = **-$6.56 per trade**
- This confirms negative expectancy — the organism is losing money on average per trade

### Trade History Data Quality Issue (ONGOING)
The following columns in `trade_history.csv` are ALL blank/zero for every trade:
- `entry_source` — always empty
- `regime_at_entry` — always empty
- `regime_at_exit` — always empty
- `mfe` — always 0.0
- `mae` — always 0.0
- `bars_held_at_exit` — always 0
- `time_in_trade_seconds` — always 0.0
- `closed_at` — always empty

**This is a critical data gap** — we cannot do proper post-hoc analysis of which regime/entry_source combinations work.

---

# 5. TODAY'S TRADING ACTIVITY

### Orders: ZERO
- No orders submitted today
- No fills, no cancellations
- DB shows 348 lifetime orders (344 filled, 4 cancelled, 0 accepted/stale)

### Candidates Rejected (from logs)

| Symbol | Max eff_conf | Regime | Count |
|--------|-------------|--------|-------|
| WMT | 0.18 | trending_up | 3 |
| GOOGL | 0.17 | trending_up | 8 |
| IWM | 0.14 | trending_down | 1 |
| AVGO | 0.00 | trending_up/down | 4 |
| AAPL | 0.00 | trending_up | 4 |
| AMZN | 0.00 | trending_up | 2 |
| NVDA | 0.00 | trending_down | 1 |
| TSLA | 0.00 | trending_down | 1 |
| XOM | 0.00 | trending_up | 1 |

**Gate: confidence_gate responsible for 100% of rejections** (all below 0.25 floor)

### Liquidity Gate Blocks (pre-confidence)
- CAT: 10 blocks
- COST: 7 blocks
- LLY: 2 blocks

### Entries Blocked (halt/drawdown/insufficient data)
- 22 ticks had entries completely blocked before even reaching candidate evaluation

---

# 6. REGIME ANALYSIS

| Regime | Ticks (in buffer) |
|--------|------------------|
| trending_up | 65 |
| trending_down | 6 |
| unknown | 2 |

### Regime Transitions
- `trending_up → trending_down` at ~17:44 UTC (12:44 ET) with 12-tick cooldown
- Trending-down block activated after 10:00 ET

### Regime Anomaly: "trending_up" During Sell-Off
The regime detector reported `trending_up` for most of the session while SPY was falling -1.52%. This is a **significant concern** — the regime model may be lagging or using stale lookback windows. If the regime were correctly `trending_down`, the inverse ETFs SH (+1.58%) and PSQ (+1.76%) could have been valid long candidates.

---

# 7. ERROR LOG

### Critical: Alpaca Position Service Disconnects
**9 occurrences** of `Failed to get all positions: RemoteDisconnected`
- 17:44, 18:02, 18:21, 18:54, 19:10, 19:13, 19:20, 19:26, 19:56 UTC
- These are Alpaca API connection drops during `get_all_positions()` calls
- The scheduler recovered each time (streak=1, no cascading failures)

### Scheduler Timeouts
**2 tick failures** (TimeoutError) at:
- 17:50:44 UTC (tick streak=1)
- 19:34:21 UTC (tick streak=1)
- Both caused by `get_all_positions()` hanging until asyncio timeout
- Both recovered on next tick — no lasting damage

### WebSocket Disconnects
- 2 market data WebSocket drops (keepalive ping timeout)
- 1 trade updates WebSocket reconnection
- All auto-reconnected successfully

### Stale Data Warnings
- 355 total stale-data warnings across ALL 22 symbols
- Each symbol had 15-17 stale warnings
- These occur in pre-market and during connection recovery — expected behavior

---

# 8. ML TRAINING STATUS

Training job #21 was submitted and **rejected by quality gate**:

| Metric | Value | Threshold |
|--------|-------|-----------|
| Score | 0.453 | < 0.35 (fail) |
| Accuracy | 58.4% | — |
| Precision | 78.4% | — |
| Recall | 62.2% | — |
| F1 | 0.694 | — |
| Hit rate | 56.8% | — |
| Calibration error | 0.345 | Too high |
| Calibration monotonic | False | Required: True |
| Candidate cal samples | 308 | — |
| System cal samples | 0 | — |

**The model was correctly rejected.** Calibration is non-monotonic with 34.5% error — this means the model's confidence scores don't reliably rank outcomes. The quality gate is working as designed.

---

# 9. MARKET OPPORTUNITY BENCHMARK (2026-03-12)

### Full Universe Performance

| Symbol | Close Change | Category |
|--------|-------------|----------|
| CRM | +2.65% | Winner (defensive/SaaS) |
| PSQ | +1.76% | Winner (inverse QQQ) |
| SH | +1.58% | Winner (inverse SPY) |
| WMT | +1.49% | Winner (defensive retail) |
| XOM | +1.29% | Winner (energy) |
| COST | +1.12% | Winner (defensive retail) |
| XLE | +0.93% | Winner (energy) |
| MSFT | -0.75% | Moderate loser |
| CAT | -0.98% | Moderate loser |
| AMZN | -1.47% | Loser |
| SPY | -1.52% | Loser (broad market) |
| NVDA | -1.55% | Loser (tech) |
| AVGO | -1.64% | Loser (semi) |
| GOOGL | -1.67% | Loser (tech) |
| QQQ | -1.72% | Loser (tech index) |
| XLK | -1.84% | Loser (tech sector) |
| AAPL | -1.94% | Loser (tech) |
| IWM | -2.15% | Loser (small cap) |
| LLY | -2.26% | Loser (pharma) |
| META | -2.55% | Loser (tech) |
| TSLA | -3.14% | Big loser (auto/tech) |
| AMD | -3.46% | Biggest loser (semi) |

### Key Observation
**7 out of 22 symbols were winners today.** Three of those winners (CRM +2.65%, WMT +1.49%, COST +1.12%) are defensive names. Two are inverse ETFs (SH +1.58%, PSQ +1.76%). Two are energy (XOM +1.29%, XLE +0.93%).

**The organism has SH and PSQ in its universe specifically for down-tape days like today, but it CANNOT go long on inverse ETFs because:**
1. The breakout scanner doesn't detect inverse ETF rallies during sell-offs (they move gradually, not via breakout patterns)
2. The regime is reported as `trending_up` even during a sell-off, so the inverse ETF regime-flip logic may not trigger
3. Confidence scores for all candidates are near-zero

---

# 10. COMPARISON: 2026-03-11 vs 2026-03-12

| Metric | Mar 11 | Mar 12 |
|--------|--------|--------|
| Trades | 0 | 0 |
| Candidates reaching gates | 27 | 27+ |
| Max eff_conf | 0.22 | 0.18 |
| Regime changes | 4 in 5 hrs | 1 transition |
| Market (SPY) | -0.3% (flat) | -1.52% (sell-off) |
| Best missed opp | XLE +1.21% | CRM +2.65%, SH +1.58% |
| Classification | HEALTHY_SELECTIVITY | HEALTHY (but structural gap exposed) |
| New trades to brain | 0 | 0 |
| PnL change | 0 | 0 |

**Two consecutive zero-trade days = 0 new data points for the learning brain.** The organism needs trades to learn. If it doesn't trade, it can't improve. This creates a potential starvation loop.

---

# 11. CUMULATIVE PLATFORM STATISTICS

| Metric | Value |
|--------|-------|
| Days since launch | ~14 trading days |
| Total trades | 158 |
| Win rate | 43.04% (68W / 89L) |
| Cumulative PnL | -$1,008.77 |
| Avg win | +$17.70 |
| Avg loss | -$24.86 |
| Expected value/trade | -$6.56 |
| Profit factor | 0.68 (68×17.70 / 89×24.86 = 1203.6 / 2212.5) |
| Sharpe ratio | ~0.0 |
| Max drawdown | ~-$1,008 (-0.90% of equity) |
| Trades to evolution | 142 more needed (158/300) |
| ML status | Untrained (quality gate rejecting) |
| Consecutive zero-trade days | 2 |

---

# 12. FILES CHANGED/CREATED SINCE LAST PROMPT

### Modified (tracked):
- `monitoring/memory_monitoring.json` — Updated memory monitoring config

### Created (untracked, from yesterday's audit cycle):
**Intraday Audit (2026-03-11):**
- `docs/engineering/intraday_audit/2026-03-11-8db0fab-intraday/intraday_gate_audit.json`
- `docs/engineering/intraday_audit/2026-03-11-8db0fab-intraday/intraday_order_health.json`
- `docs/engineering/intraday_audit/2026-03-11-8db0fab-intraday/intraday_recommendation.json`
- `docs/engineering/intraday_audit/2026-03-11-8db0fab-intraday/intraday_rejected_opportunities.json`
- `docs/engineering/intraday_audit/2026-03-11-8db0fab-intraday/intraday_runtime_snapshot.json`
- `docs/engineering/intraday_audit/2026-03-11-8db0fab-intraday/intraday_today_trades.json`

**Paper Validation Bundle (2026-03-11):**
- `docs/engineering/paper_validation/2026-03-11-8db0fab/daily_runtime_snapshot.json`
- `docs/engineering/paper_validation/2026-03-11-8db0fab/daily_trading_report.md`
- `docs/engineering/paper_validation/2026-03-11-8db0fab/daily_trade_log.json`
- `docs/engineering/paper_validation/2026-03-11-8db0fab/daily_exit_breakdown.json`
- `docs/engineering/paper_validation/2026-03-11-8db0fab/daily_entry_breakdown.json`
- `docs/engineering/paper_validation/2026-03-11-8db0fab/daily_model_quality.json`
- `docs/engineering/paper_validation/2026-03-11-8db0fab/daily_signal_quality.json`
- `docs/engineering/paper_validation/2026-03-11-8db0fab/daily_kpi_summary.json`
- `docs/engineering/paper_validation/2026-03-11-8db0fab/postclose_anomalies.json`
- `docs/engineering/paper_validation/2026-03-11-8db0fab/tomorrow_preopen_plan.json`

**No-Trade Forensic Audit (2026-03-11):**
- `docs/engineering/no_trade_forensic/2026-03-11-8db0fab/market_opportunity_benchmark.json`
- `docs/engineering/no_trade_forensic/2026-03-11-8db0fab/universe_miss_analysis.json`
- `docs/engineering/no_trade_forensic/2026-03-11-8db0fab/candidate_pipeline_forensics.json`
- `docs/engineering/no_trade_forensic/2026-03-11-8db0fab/gate_counterfactuals.json`
- `docs/engineering/no_trade_forensic/2026-03-11-8db0fab/no_trade_root_cause.json`
- `docs/engineering/no_trade_forensic/2026-03-11-8db0fab/top_rejected_opportunities.json`
- `docs/engineering/no_trade_forensic/2026-03-11-8db0fab/tomorrow_strategy_recommendation.json`

**Other:**
- `docs/engineering/AIA_RETROSPECTIVE_2026-03-11.md`

### Created (this report):
- `docs/engineering/daily_report/2026-03-12-8db0fab/daily_full_report.md` (this file)
- `docs/engineering/daily_report/2026-03-12-8db0fab/engine_status_snapshot.json`
- `docs/engineering/daily_report/2026-03-12-8db0fab/error_log_analysis.json`
- `docs/engineering/daily_report/2026-03-12-8db0fab/market_benchmark_20260312.json`
- `docs/engineering/daily_report/2026-03-12-8db0fab/strategic_recommendations.md`

---

# 13. KNOWN ISSUES & DEFERRED ITEMS

### From yesterday (still open):
| ID | Issue | Priority |
|----|-------|----------|
| INV-001 | XOM never produced as candidate despite +2.43% move (scanner sensitivity) | MEDIUM |
| INV-002 | Consider adding INTC, MU to universe (multi-day evidence needed) | LOW |
| DEFER-001 | Wire entry_source, regime, closed_at, mfe, mae into trade_history.csv | MEDIUM |
| DEFER-002 | Wire organism trades into realized_trades DB table | MEDIUM |
| DEFER-003 | Fix async bug in /api/v1/orders/validate | LOW |
| DEFER-004 | Normalize alpha weights sum to 1.0 | VERY LOW |

### New findings today:
| ID | Issue | Priority |
|----|-------|----------|
| INV-003 | Regime detector shows `trending_up` during SPY -1.52% sell-off | HIGH |
| INV-004 | Alpaca position service disconnects (9 occurrences, self-recovering) | MEDIUM |
| INV-005 | SH/PSQ in universe but never produced as candidates on down days | HIGH |
| INV-006 | Entries blocked for 22/46 visible ticks (halt/drawdown/insufficient) | MEDIUM |
| INV-007 | Brain manifest.json not synced with live engine state (142 vs 158 trades) | LOW |

---

# 14. STRATEGIC ASSESSMENT FOR AIA REVIEW

## Problem Statement
The organism has been paper trading for ~14 days. It has:
- **Negative expectancy** (-$6.56/trade, profit factor 0.68)
- **Starvation risk** (2 consecutive zero-trade days, no new data for learning)
- **Structural gaps** (can't trade inverse ETFs, can't detect defensive rotations)
- **Data quality holes** (entry_source, regime, mfe, mae all blank in trade log)

## Two Tracks for Improvement

### TRACK 1: PERFECT THE SYSTEM/MECHANISM (Infrastructure & Data)

These are engineering fixes that don't change strategy logic but improve the platform's ability to operate and learn:

1. **FIX trade_history.csv data columns** (DEFER-001) — Without entry_source, regime_at_entry, mfe, mae, we cannot analyze what's working. This is the #1 blocker for informed strategy decisions.

2. **FIX regime detector lag** (INV-003) — The regime showed `trending_up` while SPY was -1.52%. This prevents the inverse ETF logic from activating. The lookback window or detection method needs investigation.

3. **Wire realized_trades to DB** (DEFER-002) — The `realized_trades` table has 0 rows despite 158 trades. All analysis requires manual CSV parsing.

4. **Fix Alpaca connection resilience** (INV-004) — 9 disconnects in one session. Add connection pooling or retry logic to `positions_service.py:115`.

5. **Brain manifest sync** — Manifest shows 142 trades but engine has 158. The brain persistence may not be saving after every trade.

6. **Scanner sensitivity audit** (INV-001, INV-005) — Why are XOM, SH, PSQ never produced as candidates? The breakout scanner criteria need review for non-momentum patterns.

### TRACK 2: IMPROVE THE TRADING ALGORITHM (Strategy & Profitability)

These require strategy logic changes and should be carefully evaluated:

1. **Negative Expectancy Root Cause** — The avg loss ($24.86) is 40% larger than avg win ($17.70). Either:
   - Stops are too wide (letting losers run too far)
   - Take-profits are too tight (cutting winners too early)
   - Entry quality is poor (wrong direction 57% of the time)

2. **Inverse ETF Activation** — SH and PSQ are in the universe but never trade. On the two most recent down days, they would have been profitable. The regime-flip logic and scanner need to support these.

3. **Confidence Score Calibration** — Max eff_conf today was 0.18 (WMT). The formula `0.65 × breakout + 0.35 × tension` consistently produces near-zero scores. Consider:
   - Are the breakout thresholds appropriate for the current market regime?
   - Is the confidence floor (0.25) too high for learning mode?
   - Should there be a minimum trade frequency to prevent starvation?

4. **Defensive Rotation Detection** — Today CRM +2.65%, WMT +1.49%, COST +1.12% while tech sold off. The scanner only looks for breakouts, missing sector rotation opportunities.

5. **Exit Strategy Rebalancing** — With avg_win=17.70 and avg_loss=24.86:
   - Review stop-loss ATR multipliers (currently 2.5-4.0×)
   - Review partial take-profit triggers
   - Review failure-to-follow exit timing
   - Consider trailing stop improvement

6. **Learning Rate vs. Selectivity Tradeoff** — The organism needs 142 more trades to reach the 300-trade evolution threshold. At 0 trades/day, it will never get there. Options:
   - Lower confidence floor in learning mode (e.g., 0.15 instead of 0.25) with reduced position sizes
   - Add time-based "exploration" that takes small positions to gather data
   - Accept that some losing trades are the cost of learning

7. **ML Model Path** — Training job #21 was rejected (calibration non-monotonic, 34.5% error). With only 158 trades, the training set may be too small. The model needs more diverse market conditions in the training data.

---

# 15. RECOMMENDATION FOR TOMORROW (2026-03-13)

**GO_UNCHANGED** for infrastructure. But **SCHEDULE ENGINEERING WORK** for Track 1 items.

Priority order:
1. Fix trade_history.csv columns (DEFER-001) — enables all future analysis
2. Investigate regime detector behavior (INV-003) — blocks inverse ETF usage
3. Investigate scanner sensitivity for SH/PSQ/XOM (INV-005, INV-001)
4. After data quality is fixed, run 5+ trading days, then make informed strategy decisions

**Do NOT lower confidence gates or change strategy until the data quality issues are fixed.** Making strategy changes without proper trade analytics is flying blind.
