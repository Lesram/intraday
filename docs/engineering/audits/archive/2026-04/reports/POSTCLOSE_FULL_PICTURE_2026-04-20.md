# Post-Close Full Picture — 2026-04-20 (Monday)

## 1. Executive verdict

**Experiment verdict: HELPING**
**Mechanical verdict: CLEAN**

Near-breakeven day: -$0.59 on 18 trades. The system **crossed the 300-trade evolution freeze boundary** today — trade 300 was a QQQ failure_to_follow at 15:46 UTC. Pre-300 trades lost -$11.32 (0% win rate, 7 trades). Post-300 trades gained +$10.73 (36% win rate, 11 trades). The post-300 improvement is noteworthy but could be coincidence — need more sessions. 94% directional accuracy (17/18 went green) confirms the entry system remains strong. NVDA was the standout: 4 wins totaling +$24.25, including a +$10.64 max_holding_period trade. Timeout/max_hold continues to be the profit engine (+$16.63, 100% win rate). Zero PSQ/SH trades (Exp2 working). Zero Exp1A suppressions logged (trades avoided the pyramid_cut window organically today).

## 2. Session identification

- Date: 2026-04-20 (Monday)
- Market: 13:28–20:00 UTC
- Container: ce06d41, healthy, restarts=0, up since Apr 16 02:42 UTC (4.9 days)
- Exp1A=1 ✅, Exp2=2 ✅, Exp3=1 ✅, Exp4=0 ✅
- No offline commits accidentally live

## 3. Live state verification

| Check | Result |
|---|---|
| Container | healthy, restarts=0 |
| Account | ACTIVE, equity=$111,555.95 |
| Positions | flat |
| Manifest sync | ALL ✅ (gen=92, trades=312, pnl=-578.28, best_sharpe=3.4363) |
| ml_is_trained | True |
| feature_count | 79 |

**Brain evolved**: gen 84→92 (+8), trades 293→312 (+19 today but only 18 in trade_history = 1 reconciliation trade)

## 4. Mechanical integrity

- Guard fires: ALL ZERO ✅
- 188 error log entries (websocket timeouts — P3, same pattern)
- Manifest synced ✅
- No restarts, no force-save usage
- **Session trustworthy**: YES

## 5-6. Performance summary

| Metric | Baseline | **Today** |
|---|---:|---:|
| Trades | 8/day | **18** |
| Net PnL | -$15.34/day | **-$0.59** |
| Win rate | 18.8% | **22.2%** |
| Expectancy | -$1.92 | **-$0.03** |
| Payoff ratio | 1.08 | **3.42** |
| Avg hold | 550s | **836s** |
| Worst loss | -$12.69 | **-$4.29** |
| Best win | — | **+$10.64** |

**Near breakeven.** Payoff ratio 3.42 is excellent — when wins happen, they're 3.4× the average loss.

## 7. Directionality

- Green: **17/18 (94%)** — outstanding
- MFE: $57.32
- Capture rate: -1.0% (essentially zero — captured nothing net, but didn't lose much either)

**Entry system remains excellent.** 94% directional accuracy. The problem is still exit timing, not direction.

## 8. Exit system

| Exit | Count | % | PnL | Win rate | Avg give |
|---|---:|---:|---:|---:|---:|
| pyramid_cut | 6 | 33% | -$10.99 | 0% | $3.50 |
| stop_loss | 4 | 22% | -$8.76 | 0% | $1.68 |
| trailing_stop | 2 | 11% | -$4.29 | 0% | $6.70 |
| failure_to_follow | 2 | 11% | -$0.80 | 0% | $1.87 |
| timeout/max_hold | 3 | 17% | **+$16.63** | **100%** | $2.98 |
| eod_flatten | 1 | 6% | +$7.62 | 100% | $0.00 |

**Timeout/max_hold still 100% winners (+$16.63).** Pyramid_cut at 33% — higher than recent sessions but no Exp1A suppressions fired (trades didn't enter the <10 bar chop window). Trailing_stop: 2 trades, -$4.29 total, avg giveback $6.70/trade — continuing the pattern.

## 9. Giveback

| Metric | Value |
|---|---|
| Total MFE | $57.32 |
| Total PnL | -$0.59 |
| Total giveback | $53.80 |
| Capture rate | **-1.0%** |

Top 3 givebacks:
1. QQQ trailing_stop: gave back $8.90 (MFE $5.03, closed -$3.87)
2. XLE pyramid_cut: gave back $5.27 (MFE $2.03, closed -$3.24)
3. NVDA pyramid_cut: gave back $5.03 (MFE $2.59, closed -$2.44)

**Trailing-stop leapfrog**: 1 giveback >$5 today (QQQ $8.90). Running total across observation window: still building but not yet at 3+ threshold.

## 10. Confidence / ML

| Bucket | Trades | PnL | Win rate |
|---|---:|---:|---:|
| < 0.35 | 7 | **+$9.32** | **29%** |
| 0.35-0.45 | 9 | -$4.35 | 22% |
| >= 0.45 | 2 | -$5.56 | 0% |

**Confidence inversion persists.** Low confidence (<0.35) outperforms massively (+$9.32 at 29% wr). High confidence (≥0.45) produces 0% win rate (2 trades: QQQ -$3.87 and NVDA -$1.69 — both at conf >0.48). The pattern is now consistent across 6+ sessions.

## 11. Regime / symbol

**Regime**: 1318 chop (100%). Pure chop day.
**NVDA**: 6 trades, +$12.08 — carried the session. Best single trade: +$10.64.
**QQQ**: 5 trades, -$9.65 — worst symbol today.
**Inverse ETF**: 0 trades ✅ (Exp2 working)

## 12. Trade 300 / Post-freeze analysis

**Trade 300 crossed today.** The 7th trade (QQQ failure_to_follow, closed ~15:46 UTC) was approximately trade #300.

| Metric | Pre-300 (7 trades) | Post-300 (11 trades) |
|---|---:|---:|
| PnL | **-$11.32** | **+$10.73** |
| Win rate | **0%** | **36%** |
| Expectancy | -$1.62 | +$0.98 |

**Post-300 performance dramatically better.** All 4 wins came post-300. All 7 pre-300 trades were losers.

**Caution**: This could be coincidence (small sample, intraday regime drift). The evolution params activated mid-session, and the regime was chop throughout. The most likely explanation is intraday noise rather than evolution activation — but the signal is interesting enough to track.

**Key evolved params now active**: chop regime_size 0.50 (half-size positions in chop), ML alpha weight 36% (up from 25%), trailing_distance_scale 0.89.

**No suspicious behavior observed. No guard fires. Evolution unfreeze appears normal.**

## 13. Experiment tracking — cumulative

| Metric | Baseline | Exp1A only (3d) | Exp1A+Exp2 (4d) | **Today** | **Cumulative (7d)** |
|---|---:|---:|---:|---:|---:|
| Trades | 8/day | 14.7/day | 17.5/day | 18 | **~15/day** |
| Pyramid_cut % | 75% | 43% | 29% | 33% | **~35%** |
| Timeout/max_hold % | 16% | 23% | 31% | 17% | **~25%** |
| Win rate | 18.8% | 25.0% | 34.3% | 22.2% | **~28%** |
| Expectancy | -$1.92 | -$1.11 | -$0.50 | -$0.03 | **~-$0.80** |
| Avg hold | 550s | 803s | 1066s | 836s | **~900s** |

### Decisions
- **Continue unchanged?** YES
- **Exp2 helping?** YES (0 inverse-ETF trades in chop)
- **Confidence inversion?** YES (persists — low conf outperforms, high conf 0% wr)
- **Exp4 leapfrog?** NO (trailing givebacks building but <3 at threshold)

## 14. Risk / drawdown

- Equity: $111,558.13 → $111,555.95 (-$2.18 at broker)
- Worst trade: -$4.29 (AAPL stop_loss) — controlled
- No concentration risk (5 symbols traded)
- Paper-safe: YES

## 15. Top findings

1. **✅ TRADE 300 CROSSED** — evolution freeze exited. Post-300 trades were +$10.73 (36% wr) vs pre-300 -$11.32 (0% wr). Interesting signal, needs more data.
2. **✅ Near breakeven** — -$0.59 is the second-closest-to-zero session ever.
3. **✅ 94% directional accuracy** — 17/18 went green. Entry quality outstanding.
4. **✅ Timeout/max_hold 100% winners again** (+$16.63 from 3 trades).
5. **✅ Exp2 working** — zero inverse-ETF trades in chop.
6. **⚠️ Confidence inversion persists** — ≥0.45 conf = 0% wr (6th consecutive session).
7. **⚠️ Capture rate -1%** — the system generates $57 of MFE but captures nothing net. Exit timing still the problem.
8. **P3** — 188 error log entries (websocket, recurring P3).
9. **✅ Zero Exp1A suppressions** — trades didn't trigger the min-hold gate today (traded at >10 bar windows naturally).
10. **✅ Zero guard fires, manifest synced, container stable 4.9 days**.

## 16. Decisions

1. **Continue unchanged?** YES
2. **Trustworthy?** YES
3. **Exp2 helping?** YES
4. **Exp3 actionable?** INCONCLUSIVE — confidence inversion persists but needs stronger evidence before a formula change
5. **Exp4 leapfrog?** NO
6. **Blocker?** NO

**Next action tomorrow**: Post-close observation. Watch for continued post-300 evolution effects. Track whether position sizing in chop has halved (evolved regime_size 0.50).

**After observation window**: Deploy hardening bundle (HEAD `33d6138`). Includes G1/G2/G3 + Exp4 + H1/H2 + CAP/HALT + H5 + alerts.

**Live branch must remain unchanged**: `ce06d41`.
