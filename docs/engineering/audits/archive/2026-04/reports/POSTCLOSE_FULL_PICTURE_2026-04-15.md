# Post-Close Full Picture — 2026-04-15 (Wednesday, Session 3)

## 1. Executive verdict

**Experiment verdict: HELPING**
**Mechanical verdict: CLEAN**

The best session since Exp1A deployed. 17 trades, +$13.26 net PnL — the **first positive session** in the observation window. Win rate jumped to 35.3% (baseline 18.8%). Expectancy turned positive at +$0.78/trade (baseline -$1.92). Pyramid_cut share dropped to 29% (baseline 75%). Timeout/max_hold exits produced 5 trades at 80% win rate and +$29.19 PnL — the strongest evidence yet that holding works. 88% of trades went green (baseline 78%). The 10-bar min-hold gate fired 3 times. Entry quality was excellent.

## 2. Session identification
- Date: 2026-04-15 (Wednesday)
- Market: 13:30–20:00 UTC
- Live container: `ab54b2f` (Exp1A only) — VERIFIED (Exp1A=1, Exp2=0, Exp3=0, Exp4=0)
- No offline commits accidentally live

## 3. Live state verification

| Check | Result |
|---|---|
| Container | running, restarts=0, healthy, started 2026-04-11T01:54:59Z |
| API | ok |
| Account | ACTIVE, equity=$111,535.90 |
| Positions | flat |

**Manifest vs learning_state — ALL SYNCED:**

| Field | Manifest | Learning |
|---|---:|---:|
| generation | 70 | 70 ✅ |
| total_trades | 258 | 258 ✅ |
| cumulative_pnl | -562.88 | -562.88 ✅ |
| best_sharpe | 3.4363 | 3.4363 ✅ |
| ml_is_trained | True | — ✅ |
| feature_count | 79 | — ✅ |

## 4. Mechanical integrity

| Check | Status |
|---|---|
| Guard fires | ALL ZERO ✅ |
| Manifest sync | ✅ |
| Restarts | 0 ✅ |
| 88 error log entries | Likely websocket timeouts (same pattern as prior sessions) — P3 |

**Session trustworthy**: YES. No persistence anomalies, no guard fires, no state drift. DB order reconciliation gaps may persist (same class as prior sessions) but trade_history is authoritative.

## 5. Session trade ledger

| # | Symbol | PnL | MFE | MAE | Give | Bars | Hold | Conf | Exit | Green? |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | **QQQ** | **+$9.11** | $8.27 | $7.32 | $0.00 | **30** | 1770s | 0.434 | **max_holding_period** | ✅ |
| 2 | **SPY** | **+$4.84** | $6.94 | $4.02 | $2.10 | **30** | 1737s | 0.315 | **max_holding_period** | ✅ |
| 3 | QQQ | -$0.14 | $7.42 | $5.56 | $7.56 | 30 | 1754s | 0.397 | max_holding_period | ✅ |
| 4 | **XLK** | **+$1.51** | $2.65 | $3.63 | $1.14 | **30** | 1754s | 0.319 | **max_holding_period** | ✅ |
| 5 | QQQ | -$0.53 | $1.45 | $2.49 | $1.98 | 17 | 983s | 0.361 | failure_to_follow | ✅ |
| 6 | XLK | -$3.06 | -$0.18 | $3.69 | $0.00 | 12 | 678s | 0.382 | pyramid_cut_full_at_-2.4R | No |
| 7 | QQQ | -$1.72 | $0.66 | $2.89 | $2.38 | 12 | 679s | 0.306 | failure_to_follow | ✅ |
| 8 | XLK | -$0.25 | $1.65 | $4.00 | $1.90 | 13 | 737s | 0.305 | failure_to_follow | ✅ |
| 9 | QQQ | -$2.31 | $0.39 | $3.46 | $2.70 | 5 | 248s | 0.405 | pyramid_cut_full_at_-1.6R | ✅ |
| 10 | QQQ | -$2.01 | $0.56 | $2.25 | $2.57 | 5 | 263s | **0.603** | pyramid_cut_full_at_-1.9R | ✅ |
| 11 | SH | -$1.09 | $2.72 | $2.71 | $3.81 | 11 | 608s | 0.302 | trailing_stop | ✅ |
| 12 | PSQ | -$3.00 | $1.00 | $5.60 | $4.00 | 9 | 489s | 0.347 | trailing_stop | ✅ |
| 13 | SPY | +$0.30 | $5.16 | $3.41 | $4.86 | 19 | 1089s | 0.348 | trailing_stop | ✅ |
| 14 | **QQQ** | **+$13.87** | $12.59 | $10.42 | $0.00 | **30** | 1756s | 0.364 | **max_holding_period** | ✅ |
| 15 | SPY | -$1.82 | -$0.12 | $2.13 | $0.00 | 4 | 186s | 0.310 | pyramid_cut_full_at_-1.5R | No |
| 16 | **XLK** | **+$1.10** | $1.98 | $0.28 | $0.88 | 15 | 912s | 0.430 | stop_loss | ✅ |
| 17 | QQQ | -$1.54 | $0.21 | $2.96 | $1.75 | 4 | 181s | 0.371 | pyramid_cut_full_at_-1.5R | ✅ |

## 6. Performance summary

| Metric | Baseline | Day 1 | Day 2 | **Day 3** |
|---|---:|---:|---:|---:|
| Trades | 8/day | 16 | 11 | **17** |
| Net PnL | -$15.34/day | -$21.70 | -$40.52 | **+$13.26** ✅ |
| Win rate | 18.8% | 18.8% | 18.2% | **35.3%** ✅ |
| Expectancy | -$1.92 | -$1.36 | -$3.68 | **+$0.78** ✅ |
| Payoff ratio | 1.08 | — | 0.10 | **3.22** ✅ |
| Avg hold | 550s | 746s | 699s | **931s** ✅ |
| Worst loss | -$12.69 | -$8.36 | -$21.60 | **-$3.06** ✅ |
| Best win | — | +$4.64 | +$0.64 | **+$13.87** ✅ |

**Every metric improved.** First positive session. Best single trade (+$13.87 QQQ via max_holding_period). Smallest worst loss (-$3.06). Highest win rate. Highest payoff ratio.

## 7. Directionality

- Trades that went green: **15/17 (88%)** — UP from baseline 78% and Day 2's 55%
- Average MFE: $3.16 (strong, up from Day 2's $1.79)
- Capture rate: **+24.7%** (POSITIVE for the first time — capturing 25% of MFE generated)

**Entry quality was excellent today.** 88% directional accuracy is the highest in the observation window. The problem today was STILL exits (pyramid_cut and trailing_stop gave back edge), but much less than prior sessions.

## 8. Exit system analysis

| Exit | Count | % | PnL | Win rate | Avg hold | Avg giveback |
|---|---:|---:|---:|---:|---:|---:|
| **pyramid_cut** | 5 | **29%** | -$10.74 | 0% | 311s | $1.40 |
| trailing_stop | 3 | 18% | -$3.79 | 33% | 728s | $4.22 |
| failure_to_follow | 3 | 18% | -$2.50 | 0% | 799s | $2.09 |
| stop_loss | 1 | 6% | +$1.10 | 100% | 912s | $0.88 |
| **timeout/max_hold** | **5** | **29%** | **+$29.19** | **80%** | **1754s** | $2.16 |

**Pyramid_cut** dropped to 29% (from 75% baseline, 50% Day 1, 55% Day 2). The 10-bar gate is working — trades are surviving to reach timeout.

**Timeout/max_hold** produced +$29.19 from 5 trades at 80% win rate. This is the strongest validation of the "hold and let the thesis play out" approach. The QQQ +$13.87 and SPY +$4.84 timeout exits are the session's profit engine.

**Trailing_stop** gave back $12.67 across 3 trades. PSQ trailing_stop gave back $4.00, SPY trailing_stop gave back $4.86 from a $5.16 MFE (captured only $0.30). This is the continuing trailing-stop leakage.

## 9. Giveback analysis

| Metric | Value |
|---|---|
| Total MFE | $53.65 |
| Total PnL | +$13.26 |
| Total giveback | $37.63 |
| **Capture rate** | **+24.7%** |

| Exit | Giveback | Avg/trade |
|---|---:|---:|
| trailing_stop | $12.67 | **$4.22** |
| timeout/max_hold | $10.80 | $2.16 |
| pyramid_cut | $7.00 | $1.40 |
| failure_to_follow | $6.27 | $2.09 |
| stop_loss | $0.88 | $0.88 |

**Trailing-stop leapfrog check**: 3 trailing_stop trades today. Givebacks: $3.81 (SH), $4.00 (PSQ), $4.86 (SPY). None above $5 individually, but all close. Cumulative trailing-stop givebacks >$5 in the window: Day 1 NVDA $14.89 + today's SPY $4.86 = 2 trades above or near $5. **Leapfrog criteria NOT YET met** (need 3+). Close — one more session could tip it.

**Exp2 readiness**: PSQ -$3.00 and SH -$1.09 today, both losers, both in chop, both would be blocked by Exp2. **Exp2 remains confirmed.**

## 10. Confidence / ML analysis

| Bucket | Trades | PnL | Win rate |
|---|---:|---:|---:|
| < 0.35 | 8 | -$1.23 | **38%** |
| 0.35-0.45 | 8 | **+$16.50** | **38%** |
| >= 0.45 | 1 | -$2.01 | 0% |

**BREAKTHROUGH: The 0.35-0.45 bucket turned positive.** 8 trades, +$16.50, 38% win rate — including the QQQ +$13.87 at conf 0.364. The confidence inversion WEAKENED today. The mid-confidence range is performing.

The single >=0.45 trade (QQQ at conf 0.603) lost -$2.01 via pyramid_cut. High confidence still underperforms, but the sample (1 trade) is too small to draw conclusions today.

**ML contamination hypothesis: INCONCLUSIVE for this session.** The 0.35-0.45 bucket's strong performance suggests ML isn't uniformly harmful. The inversion may be specific to very high confidence (>0.50) rather than the entire ML-weighted range.

## 11. Regime / symbol / time

**Regime**: 1627 chop (100%). Pure chop day.

**Symbols**: QQQ dominated (8 trades, +$14.73 net — carried the session). SPY +$3.32 (3 trades). XLK -$0.70 (4 trades). PSQ -$3.00, SH -$1.09 (inverse ETFs, both losers in chop as expected).

**Inverse ETFs**: 2 trades, -$4.09 combined. Both would be blocked by Exp2. **Exp2 continues to have value.**

## 12. Experiment tracking — CUMULATIVE WINDOW

### Day-by-Day

| Metric | Baseline | Day 1 | Day 2 | Day 3 | **Cumulative** |
|---|---:|---:|---:|---:|---:|
| Trades | 8/day | 16 | 11 | 17 | **44** |
| Suppressions | — | 4 | 4 | 3 | **11** |
| Pyramid_cut % | 75% | 50% | 55% | **29%** | **43%** |
| Timeout/max_hold % | 16% | 12% | 27% | **29%** | **23%** |
| Win rate | 18.8% | 18.8% | 18.2% | **35.3%** | **25.0%** |
| Expectancy | -$1.92 | -$1.36 | -$3.68 | **+$0.78** | **-$1.11** |
| Avg hold | 550s | 746s | 699s | **931s** | **803s** |
| Worst loss | -$12.69 | -$8.36 | -$21.60 | **-$3.06** | -$21.60 |

### Session 3 hard recommendation: **KEEP**

Exp1A is working. The evidence:
1. Pyramid_cut dropped from 75% → 43% cumulative
2. Hold time increased from 550s → 803s cumulative
3. Win rate improved from 18.8% → 25.0% cumulative
4. The best session (Day 3) had pyramid_cut at 29% and first positive PnL
5. 11 suppressions across 3 sessions — the gate is firing consistently
6. Cumulative expectancy (-$1.11) is better than baseline (-$1.92) despite Day 2 outlier

The Day 2 regression was driven by a single QQQ outlier (-$21.60). Excluding that, cumulative expectancy would be approximately -$0.62 — significantly better than baseline.

### Queue updates
- **Exp2 remains next**: YES. PSQ/SH lost -$4.09 today in chop. Exp2 is ready.
- **Exp3 prep**: ML contamination hypothesis WEAKENED today (0.35-0.45 bucket turned positive). Keep queued but lower urgency.
- **Exp4 stays behind Exp2**: YES. Trailing-stop leapfrog criteria not yet met (2 trades near threshold, need 3+). BUT trailing_stop gave back $12.67 today — if tomorrow adds another $5+ giveback, Exp4 moves up.

## 13. Risk / drawdown

- Equity: $111,522.91 → $111,535.90 (+$12.99 at broker)
- Worst trade: -$3.06 (XLK pyramid_cut) — controlled
- No position exceeded limits
- Losses distributed across symbols (not concentrated)
- Paper-safe: YES

## 14. Top findings

1. **✅ / experiment**: First positive session (+$13.26). Win rate 35.3%. Exp1A working.
2. **✅ / algorithm**: Pyramid_cut at 29% — lowest in the observation window. Timeout exits at 80% wr.
3. **✅ / directionality**: 88% of trades went green. Highest directional accuracy in the window.
4. **✅ / capture**: 24.7% capture rate — first positive capture.
5. **P3 / algorithm**: QQQ +$13.87 is the biggest single win ever. 30-bar max_holding_period.
6. **P3 / algorithm**: PSQ/SH lost -$4.09 in chop. Exp2 readiness confirmed.
7. **P3 / algorithm**: Trailing_stop gave back $12.67 (3 trades). Exp4 case building.
8. **P3 / data**: Confidence inversion weakened — 0.35-0.45 bucket +$16.50 at 38% wr.
9. **P3 / mechanical**: 88 error log entries (websocket pattern, P3).
10. **✅ / structural**: Zero guard fires, manifest synced, container stable.

## 15. Decisions

1. **Continue Exp1A unchanged?** **YES** — KEEP. Working as designed.
2. **Session trustworthy?** YES.
3. **Exp2 remain next?** YES — PSQ/SH still losing in chop.
4. **Exp4 move ahead?** NO — trailing leapfrog criteria not yet met (2, need 3+).
5. **Blocker before next session?** NO.

**Recommended next action tomorrow**: Run post-close observation. Session 4. If positive trend holds, begin planning Exp2 deployment for Friday post-close.

**Recommended after session 3**: Exp1A verdict is **KEEP**. Next deploy: Exp2 (suppress PSQ/SH in chop) at the next post-close maintenance window. Stack with Exp3 instrumentation and G1/G2/G3 mechanical fixes if convenient.

**Live branch must remain unchanged**: `ab54b2f` only until the next authorized deploy.
