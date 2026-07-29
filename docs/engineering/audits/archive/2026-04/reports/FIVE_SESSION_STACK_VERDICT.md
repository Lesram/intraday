# Five-Session Stack Verdict

**Window**: Apr 16 - Apr 22, 2026 (Sessions 1-5 post-Exp2)
**Live stack**: `ce06d41` — Exp1A + Exp2 + Exp3 prep
**Brain**: gen=106, total_trades=348, evolution active (crossed 300 on Apr 20)
**Container**: running, 0 restarts, healthy, uptime since Apr 16

---

## 1. Session-by-session results

| Session | Date   | Trades | W-L   | WR   | PnL      | Pyramid cuts | MaxHold | Outlier |
|---------|--------|--------|-------|------|----------|-------------|---------|---------|
| 1       | Apr 16 | 16     | 5-11  | 31%  | -$47.33  | 5 (31%)     | 4       | IWM -$41.52 |
| 2       | Apr 17 | 19     | 7-12  | 37%  | +$29.76  | 5 (26%)     | 7       | — |
| 3       | Apr 20 | 19     | 5-14  | 26%  | +$2.19   | 6 (32%)     | 3       | — |
| 4       | Apr 21 | 16     | 3-13  | 19%  | -$8.56   | 6 (38%)     | 1       | — |
| 5       | Apr 22 | 20     | 6-14  | 30%  | -$20.56  | 8 (40%)     | 4       | — |
| **Total** |      | **90** | **26-64** | **29%** | **-$44.50** | **30 (33%)** | **19** | |

**Avg PnL/trade**: -$0.49
**Avg PnL/session**: -$8.90

---

## 2. Comparison with pre-window (Apr 7-15, 7 sessions)

| Metric | Pre-window (77 trades) | Observation window (90 trades) | Change |
|--------|----------------------|-------------------------------|--------|
| Win rate | 23% | 29% | +6 pp |
| Avg PnL/trade | +$0.95 | -$0.49 | -$1.44 |
| Total PnL | +$72.95 | -$44.50 | |
| Pyramid cut share | 56% | 33% | -23 pp (improved) |
| MaxHold share | 14% | 21% | +7 pp (improved) |

**Key observation**: Win rate improved, pyramid_cut share fell materially (56% -> 33%), but average PnL per trade flipped from slightly positive to slightly negative. The pre-window had a $183.28 reconciliation windfall on Apr 8 (XLE) that inflated its total. Excluding that, pre-window PnL was -$110.33 (avg -$1.43/trade). The observation window is actually an improvement in per-trade expectancy.

---

## 3. Exp1A assessment: pyramid_cut in chop

**Verdict: WORKING AS DESIGNED**

- Pyramid cut share dropped from 56% to 33% — the 10-bar min-hold gate is suppressing premature cuts
- MaxHold exits rose from 14% to 21% — more trades surviving to max hold, which are the most profitable exit type
- MaxHold trades in window: 19 trades, PnL=+$81.64, 89.5% win rate, avg +$4.30/trade
- MaxHold remains the only consistently profitable exit type

---

## 4. Exp2 assessment: PSQ/SH suppression in chop

**Verdict: WORKING PERFECTLY**

- Zero PSQ/SH trades in the 5-session window
- The chop-regime suppression is functioning correctly
- All 88 of 90 window trades were in chop regime — PSQ/SH would have been pure losers here

---

## 5. Exp3 assessment: confidence instrumentation

**Verdict: INCONCLUSIVE, keep collecting**

Confidence distribution in window:
- [0.3-0.4): 68 trades, PnL=-$29.86, WR=32%
- [0.4-0.5): 18 trades, PnL=-$18.11, WR=11%
- [0.5-0.6): 4 trades, PnL=+$3.47, WR=50%

**Concerning**: Higher confidence (0.4-0.5) has LOWER win rate (11%) than lower confidence (0.3-0.4, 32%). This is weak evidence of confidence inversion in the 0.4-0.5 band. The 0.5+ bucket has too few trades (4) to draw conclusions.

---

## 6. Exit system analysis

### Exit reason breakdown (window)

| Exit type | Count | PnL | WR | Avg |
|-----------|-------|-----|----|-----|
| max_holding_period | 19 | +$81.64 | 89.5% | +$4.30 |
| take_profit | 2 | +$15.82 | 100% | +$7.91 |
| eod_flatten | 1 | +$7.62 | 100% | +$7.62 |
| trailing_stop | 8 | -$4.72 | 25% | -$0.59 |
| failure_to_follow | 11 | -$4.82 | 9.1% | -$0.44 |
| stop_loss | 17 | -$31.21 | 11.8% | -$1.84 |
| pyramid_cut (all) | 30 | -$93.51 | 0% | -$3.12 |
| reconciliation | 2 | -$15.10 | 50% | -$7.55 |

### MFE giveback

- **61% of trades** went green then closed red
- Total favorable excursion given back: **$195.21**
- Trailing stop trades gave back an average of $3.92 per trade (MFE avg $3.33, realized avg -$0.59)

The trailing stop is the single largest value-destruction mechanism. 8 trailing-stop exits gave back $31.38 of MFE.

---

## 7. Evolution at trade 300

Trade 300 was crossed on Apr 20 (Session 3). The evolved params activated:
- ML alpha weight increased to 36% (from 25%)
- Trailing distance scale tightened by ~11%
- Chop regime size reduced to 50% (conservative)
- Direction thresholds became more selective

**Post-300 performance (Sessions 3-5, Apr 20-22)**: 55 trades, PnL=-$26.93, avg=-$0.49
**Pre-300 within window (Sessions 1-2, Apr 16-17)**: 35 trades, PnL=-$17.57, avg=-$0.50

No observable degradation from evolution activation. Performance is essentially flat pre/post evolution boundary within the window. The tightened trailing distance scale may be partially offset by the reduced chop sizing. Insufficient data to distinguish signal from noise.

---

## 8. Infrastructure stability

- **Container**: 0 restarts since Apr 16, continuously healthy
- **Brain**: No save failures, no wipe incidents, no manifest drift
- **Reconciliation**: 2 events (QQQ on Apr 20 and Apr 22) — minor, not structural
- **Persistence**: Structurally frozen, working as expected
- **Evolution**: Activated cleanly at trade 300, no anomalies

**Verdict: MECHANICALLY STABLE**

---

## 9. Rolling expectancy trend

| Window | PnL | Avg/trade | WR |
|--------|-----|-----------|----|
| Last 50 | -$21.37 | -$0.43 | 26% |
| Last 100 | -$41.25 | -$0.41 | 29% |
| Last 150 | -$118.81 | -$0.79 | 27% |
| All-time (348) | -$607.38 | -$1.75 | 33% |

**The trend is improving**. Expectancy has moved from -$1.75 all-time to -$0.41 over the last 100 trades. The system is converging toward breakeven from below but has not yet crossed to positive.

---

## 10. Symbol concentration

| Symbol | Trades | PnL | Notes |
|--------|--------|-----|-------|
| NVDA | 23 | +$21.52 | Best performer, 39% WR |
| XLE | 12 | +$10.26 | Second best, 25% WR |
| SPY | 10 | +$4.08 | Positive, 50% WR |
| QQQ | 33 | -$21.43 | Worst performer, 24% WR, 37% of all trades |
| IWM | 1 | -$41.52 | Single outlier trade |

QQQ concentration (33 of 90 trades, 37%) is concerning. IWM single-trade -$41.52 outlier dominated Session 1 — without it, the window PnL would be -$2.98 (essentially flat).

---

## 11. Overall stack verdict

### What is working
1. **Exp1A**: Pyramid cut suppression is effective (56% -> 33%)
2. **Exp2**: PSQ/SH chop blocking works perfectly (0 trades)
3. **MaxHold**: The most profitable exit type, proportion rising
4. **Infrastructure**: Rock solid, zero incidents
5. **Evolution**: Activated cleanly, no degradation observed
6. **Expectancy trend**: Improving (-$1.75 -> -$0.41/trade)

### What is not yet working
1. **Overall expectancy**: Still negative (-$0.49/trade in window)
2. **Trailing stop giveback**: $195.21 given back, 61% of trades go green then close red
3. **Win rate**: 29% is too low for the reward structure
4. **Confidence inversion hint**: 0.4-0.5 confidence band worse than 0.3-0.4
5. **QQQ concentration**: 37% of trades, net negative

### Bottom line

**The current stack (Exp1A + Exp2 + Exp3) has measurably improved the system but has not achieved positive expectancy.** The improvements are structural (fewer premature exits, no inverse-ETF chop losers) and the direction is correct. The system is mechanically stable and the trend is toward breakeven.

**KEEP the current stack.** No changes to live algorithm.
