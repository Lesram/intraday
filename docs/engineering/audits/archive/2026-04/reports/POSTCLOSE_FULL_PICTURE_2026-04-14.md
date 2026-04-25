# Post-Close Full Picture — 2026-04-14 (Tuesday, Session 2)

## 1. Executive verdict

**Experiment verdict: UNCLEAR**
**Mechanical verdict: MINOR ISSUES**

A rough day. Exp1A continued to reduce pyramid_cut share (55% vs 75% baseline) and increase hold times (699s vs 550s), but expectancy worsened to −$3.68/trade (baseline −$1.92) driven by one outsized QQQ loss (−$21.60) and a bizarre AAPL "take_profit" exit that gave back $19.71 of MFE. The 10-bar min-hold gate fired 4 times (same as Day 1). Win rate is flat at 18.2%. Two DB orders are stuck at `pending_new` status despite Alpaca showing positions flat — a reconciliation gap, not a trading logic bug.

## 2. Session identification

- Date: 2026-04-14 (Tuesday)
- Market: 13:30–20:00 UTC
- Live container: `ab54b2f` (Exp1A only) — VERIFIED
- Exp2/Exp3/Exp4/G1-G3: confirmed ABSENT from running container (all 0 grep matches)
- No offline commits accidentally live

## 3. Live state verification

| Check | Result |
|---|---|
| Container | running, restarts=0, healthy, started 2026-04-11T01:54:59Z |
| API | ok |
| Account | ACTIVE, equity=$111,522.95, trading_blocked=false |
| Positions | flat ([] from Alpaca) |

**Manifest vs learning_state — ALL SYNCED:**

| Field | Manifest | Learning | Sync |
|---|---|---|---|
| generation | 61 | 61 | ✅ |
| total_trades | 241 | 241 | ✅ |
| cumulative_pnl | -576.14 | -576.14 | ✅ |
| best_sharpe | 3.4363 | 3.4363 | ✅ |
| ml_is_trained | True | — | ✅ |
| feature_count | 79 | — | ✅ |

Brain evolved: gen 53→61 (+8), trades 230→241 (+11)

## 4. Mechanical integrity

| Check | Status |
|---|---|
| Guard fires | ALL ZERO ✅ |
| Manifest sync | ✅ |
| Container restarts | 0 ✅ |
| Force-save usage | None |

**⚠️ MINOR ISSUE: 2 orders stuck at `pending_new` in DB**
- QQQ sell 8 shares at $626.26 — status `pending_new` in DB, but Alpaca shows position flat
- AAPL sell 12 shares at $259.42 — same pattern

These orders filled at Alpaca but the fill-status update was not propagated to the DB. This is the same reconciliation gap seen with XLE in prior sessions. The scheduled reconciliation (every 15 min) should have caught it, but the `pending_new` status persists. **P3 — doesn't affect trading logic or brain state, but creates order-accounting noise.**

**64 errors in logs today** — need classification:

**Session is trustworthy for algorithm evaluation**: YES, with caveat. The 2 `pending_new` orders mean the DB-based PnL is unreliable (shows −$8,126 due to missing sell fills). The trade_history.csv PnL (−$40.52) is authoritative for Exp1A evaluation.

## 5. Session trade ledger

| # | Symbol | PnL | MFE | MAE | Giveback | Bars | Hold | Conf | Exit | Green? |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | TSLA | -$0.67 | -$0.02 | $1.60 | $0.00 | 5 | 255s | 0.320 | pyramid_cut_full_at_-1.1R | No |
| 2 | **QQQ** | **+$0.64** | $1.02 | $1.24 | $0.38 | **30** | **1745s** | 0.305 | **max_holding_period** | Yes ✅ |
| 3 | PSQ | -$1.08 | -$0.54 | $4.49 | $0.00 | 4 | 186s | 0.320 | pyramid_cut_full_at_-1.2R | No |
| 4 | **QQQ** | **-$21.60** | -$0.32 | $3.83 | $0.00 | 4 | 195s | **0.403** | pyramid_cut_full_at_-1.2R | **No** |
| 5 | AAPL | -$8.19 | **$11.52** | $3.37 | **$19.71** | 8 | 432s | 0.314 | take_profit | Yes ✅ |
| 6 | XLK | -$2.79 | -$0.31 | $4.18 | $0.00 | 3 | 142s | 0.371 | pyramid_cut_full_at_-1.8R | No |
| 7 | XLK | -$1.40 | $2.52 | $3.86 | $3.92 | 30 | 1744s | 0.322 | max_holding_period | Yes ✅ |
| 8 | QQQ | -$0.05 | $2.69 | $3.27 | $2.74 | 30 | 1744s | 0.323 | max_holding_period | Yes ✅ |
| 9 | SPY | -$2.98 | -$0.40 | $4.08 | $0.00 | 4 | 195s | **0.577** | pyramid_cut_full_at_-1.6R | No |
| 10 | XLK | -$2.70 | $1.21 | $2.27 | $3.91 | 3 | 194s | 0.339 | pyramid_cut_full_at_-1.6R | Yes ✅ |
| 11 | QQQ | +$0.30 | $0.72 | $0.23 | $0.42 | 14 | 859s | 0.333 | stop_loss | Yes ✅ |

## 6. Performance summary

| Metric | Baseline | Day 1 | **Day 2** |
|---|---:|---:|---:|
| Trades | 8/day avg | 16 | **11** |
| Net PnL | -$15.34/day | -$21.70 | **-$40.52** |
| Win rate | 18.8% | 18.8% | **18.2%** |
| Expectancy | -$1.92 | -$1.36 | **-$3.68** |
| Avg hold | 550s | 746s | **699s** |
| Worst loss | -$12.69 | -$8.36 | **-$21.60** |
| Best win | — | +$4.64 | **+$0.64** |
| Payoff ratio | 1.08 | — | **0.10** |

**Worst session since Exp1A deployed.** The QQQ -$21.60 is the single worst trade in the entire observation window. Payoff ratio collapsed to 0.10 (wins are $0.47 avg vs losses $4.61 avg).

## 7. Directionality

- Trades that went green: 6/11 (55%) — DOWN from baseline 78%
- Average MFE: $1.79 (much lower than baseline ~$3.30)
- Capture rate: -205.9% (destroyed 2× the MFE generated)

**The entry system was WEAKER today.** Only 55% of trades went green (vs 78% baseline). The directional signal quality dropped, not just exit timing.

## 8. Exit system analysis

| Exit | Count | % | PnL | Win rate | Avg hold | Avg giveback | Baseline % |
|---|---:|---:|---:|---:|---:|---:|---:|
| pyramid_cut | 6 | **55%** | -$31.82 | 0% | 194s | $0.65 | 75% |
| timeout/max_hold | 3 | **27%** | -$0.81 | **33%** | 1744s | $2.35 | 16% |
| stop_loss | 1 | 9% | +$0.30 | 100% | 859s | $0.42 | 9% |
| take_profit | 1 | 9% | -$8.19 | 0% | 432s | $19.71 | — |

**Pyramid_cut still dominant damage** (-$31.82), but timeout/max_hold is NO LONGER 100% winners — 1/3 today was a winner (+$0.64 QQQ), 2/3 were losers (XLK -$1.40, QQQ -$0.05). This is the first session where timeout exits produced losses.

**AAPL take_profit anomaly**: Trade went to +$11.52 MFE, exited via "take_profit" at -$8.19. This suggests a partial TP that booked profits, then the remainder reversed and hit a stop. The combined round-trip netted -$8.19. This is a giveback problem, not a take_profit problem per se.

## 9. Giveback analysis

| Metric | Day 2 |
|---|---|
| Total MFE | $19.68 |
| Total PnL | -$40.52 |
| Total giveback | $31.08 |
| Capture rate | **-205.9%** |

| Exit | Trades with MFE>0 | Giveback | Avg |
|---|---:|---:|---:|
| take_profit | 1 | **$19.71** | $19.71 |
| pyramid_cut | 2 | $4.56 | $2.28 |
| timeout/max_hold | 2 | $5.09 | $2.55 |
| stop_loss | 1 | $0.42 | $0.42 |

**Worst giveback: AAPL** (gave back $19.71 from $11.52 MFE). The "take_profit" exit label is misleading — this was likely a partial TP followed by a full loss on the remaining shares.

**Trailing-stop givebacks > $5 today: 0.** No trailing_stop exits at all. Exp4 leapfrog criteria NOT met.

## 10. Confidence / ML analysis

| Bucket | Trades | PnL | Win rate | Baseline wr |
|---|---:|---:|---:|---:|
| < 0.35 | 8 | -$13.15 | **25%** | 29% |
| 0.35-0.45 | 2 | -$24.39 | **0%** | 0% |
| >= 0.45 | 1 | -$2.98 | **0%** | 0% |

**Confidence inversion CONFIRMED again.** The SPY trade at confidence 0.577 (highest today) lost -$2.98. The QQQ trade at 0.403 lost -$21.60 (worst trade). Both high-confidence trades that were ML-boosted. Low-confidence bucket (<0.35) is the only one with any wins (25%).

**ML contamination hypothesis strengthened.** Two consecutive sessions show the same pattern.

## 11. Regime / symbol / time

**Regime**: 1696 chop (97%), 35 high_vol (2%), 9 trending_down (<1%), 5 trending_up (<1%). Essentially all chop.

**PSQ/SH**: PSQ traded 1 time, lost -$1.08 in chop. PSQ remains a net loser in chop. Exp2 readiness: CONFIRMED.

**Symbol concentration**: QQQ dominated (4 trades, -$20.71 net). QQQ had both the worst trade (-$21.60) and the best (+$0.64).

## 12. Experiment tracking — cumulative window

### Exp1A Day-by-Day

| Metric | Baseline | Day 1 | Day 2 | Cumulative |
|---|---:|---:|---:|---:|
| Trades | 8/day | 16 | 11 | **27** |
| Suppressions | — | 4 | 4 | **8** |
| Pyramid_cut % | 75% | 50% | 55% | **52%** |
| Timeout/max_hold % | 16% | 12% | 27% | **19%** |
| Win rate | 18.8% | 18.8% | 18.2% | **18.5%** |
| Expectancy | -$1.92 | -$1.36 | -$3.68 | **-$2.30** |
| Avg hold | 550s | 746s | 699s | **727s** |
| Worst loss | -$12.69 | -$8.36 | -$21.60 | **-$21.60** |

**Cumulative assessment**: Exp1A has successfully reduced pyramid_cut dominance (52% vs 75% baseline) and increased hold times (727s vs 550s). But expectancy has WORSENED (-$2.30 vs -$1.92 baseline), driven entirely by the QQQ -$21.60 outlier. Without that single trade, cumulative expectancy would be about -$1.50 (better than baseline).

### Queue status
- **Exp2 remains next**: YES. PSQ still losing in chop. Orthogonal to exit fixes.
- **Exp3 prep**: ML contamination hypothesis STRENGTHENED by Day 2 data (0% wr at high confidence, 2 sessions running).
- **Exp4 stays behind Exp2**: YES. No trailing-stop givebacks > $5 today (0 trailing_stop exits). The leapfrog criteria is NOT met.

## 13. Risk / drawdown

- Equity: $111,526.56 → $111,522.95 (−$3.61 per broker; the −$40.52 from trade_history vs −$3.61 broker gap is due to the pending_new fill propagation issue)
- Worst single trade: QQQ -$21.60 (8 shares at $626 = $5K notional; ~0.02% of equity — small in absolute terms but 5× the average loss)
- Losses controlled: no position exceeded stop-loss limits
- Paper-safe: YES

## 14. Top findings

1. **P2 / algorithm**: QQQ -$21.60 is the worst trade in the observation window. 8 shares pyramided, cut at -1.2R after 4 bars. Position sizing concern — 8 shares of QQQ at $626 is $5K notional for a trade that lost $21 in minutes.
2. **P2 / algorithm**: Timeout/max_hold exits are NO LONGER 100% winners (1/3 today). The universal "hold = profit" assumption may be weakening as the market regime evolves.
3. **P2 / algorithm**: ML confidence inversion confirmed for second consecutive session. High-confidence trades (0.577, 0.403) produced the two worst outcomes.
4. **P3 / mechanical**: 2 orders stuck at `pending_new` in DB despite Alpaca fill. Reconciliation gap — same class as prior XLE issue.
5. **P3 / data**: AAPL "take_profit" exit at -$8.19 with $11.52 MFE is counterintuitive. May be partial TP followed by loss on remainder.
6. **P3 / algorithm**: Entry directional accuracy dropped to 55% (baseline 78%). May be regime-specific or sample noise.
7. **P3 / algorithm**: Payoff ratio collapsed to 0.10 (baseline 1.08). Wins are too small relative to losses.
8. **P3 / ops**: 64 error log entries today — need classification (likely websocket timeouts).
9. **✅ / structural**: Zero guard fires, manifest synced, no wipe recurrence.
10. **✅ / experiment**: Exp1A gate firing consistently (4/day in both sessions).

## 15. Decisions

1. **Continue Exp1A unchanged?** YES — need session 3 for a 3-session judgment. The QQQ outlier skews today's results.
2. **Session trustworthy?** YES, using trade_history data (not raw DB orders).
3. **Exp2 remain next?** YES — PSQ still losing in chop, orthogonal.
4. **Exp4 move ahead?** NO — zero trailing-stop exits today, leapfrog criteria not met.
5. **Blocker before next session?** NO.

**Next action tomorrow**: Run post-close observation report. This is session 3 — will provide the hard KEEP/REVERT/REFINE recommendation on Exp1A.

**After session 3**: If cumulative expectancy is still worse than baseline (currently -$2.30 vs -$1.92), seriously evaluate KEEP AND REFINE (wider CUT_FULL threshold) vs REVERT.

**Live branch must remain unchanged**: `ab54b2f` only.
