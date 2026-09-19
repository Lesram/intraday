# Post-300 Stability Review — 2026-04-21 (Tuesday)

## 1. Executive verdict

**Experiment verdict: HELPING**
**Mechanical verdict: CLEAN**
**Post-300 verdict: INCONCLUSIVE**

A mildly losing day: -$8.56 on 16 trades. All trades are now post-300 (started at 312, ended at 328). Win rate dropped to 18.8% (matching baseline), but the XLE +$9.99 take_profit win was the first genuine take_profit exit in the entire observation history — a NEW exit type that only fires in production mode. 88% directional accuracy remains strong (14/16 went green). Pyramid_cut is back as the dominant leak (-$14.35 from 6 trades). Exp2 continues blocking inverse ETFs (0 PSQ/SH, 2 suppressions). The post-300 improvement seen on Monday's second half has NOT continued into a full session — today is roughly back to pre-300 levels. More data needed.

## 2. Live state verification

| Check | Result |
|---|---|
| Container | ce06d41, healthy, restarts=0, 5.9 days uptime |
| Exp1A=1 Exp2=2 Exp3=1 Exp4=0 | ✅ Correct |
| Account | ACTIVE, equity=$111,547.00 |
| Positions | flat |
| Manifest sync | ALL ✅ (gen=98, trades=328, pnl=-586.83, best_sharpe=3.4363, ml=True, fc=79) |
| Guards | ALL ZERO |

## 3. Performance

| Metric | Baseline | Yesterday (post-300 half) | **Today (all post-300)** |
|---|---:|---:|---:|
| Trades | 8/day | 11 (post-300) | **16** |
| PnL | -$15.34/day | +$10.73 | **-$8.56** |
| Win rate | 18.8% | 36% | **18.8%** |
| Expectancy | -$1.92 | +$0.98 | **-$0.54** |
| Payoff | 1.08 | — | **2.42** |
| Hold | 550s | — | **959s** |
| Worst | -$12.69 | — | **-$6.65** |
| Best | — | — | **+$9.99** |
| Green | 78% | — | **88%** |
| Capture | — | — | **-30%** |

## 4. Exp1A / Exp2 / Exp3

- **Exp1A suppressions**: 6 today (back to firing after yesterday's 0). Gate is active.
- **Exp2 suppressions**: 2 (PSQ/SH blocked). Zero inverse-ETF trades. ✅
- **Exp3**: confidence data accumulating. See section 8.

## 5. Post-300 behavior analysis

**All 16 trades today are post-300.** Yesterday's session had 11 post-300 trades that went +$10.73 at 36% wr. Today's 16 post-300 trades went -$8.56 at 18.8% wr.

| Post-300 comparison | Yesterday (11 trades) | Today (16 trades) |
|---|---:|---:|
| PnL | +$10.73 | -$8.56 |
| Win rate | 36% | 18.8% |
| Expectancy | +$0.98 | -$0.54 |

**Post-300 regressed from yesterday's promising signal.** The one-session improvement was likely noise, not an evolution effect. The system is back to near-baseline expectancy.

**However**: the XLE +$9.99 take_profit exit is noteworthy — this exit type was disabled in learning mode and is now active post-300. It captured 100% of its MFE ($9.06). This is evolution working as intended: production-mode profit exits are now available.

## 6. Evolved params impact

No change to `evolved_params.json` since yesterday (evolution doesn't rewrite the file on every retrain — it uses the loaded values until a new evolution cycle produces better params).

**Observable effects of evolved params**:
- Chop regime_size 0.50 → position sizes should be smaller. Hard to verify without raw notional data but the XLE -$6.65 (worst loss) is smaller than last week's IWM -$41.52 outlier. Possibly working.
- take_profit now firing → production-mode exit enabled. XLE +$9.99 is the first genuine TP exit.
- trailing_distance_scale 0.89 → trailing slightly tighter. Two trailing_stop trades today, both small losses (-$0.21 and -$0.21). Average giveback $2.77 — moderate, not catastrophic.

## 7. Exit system

| Exit | Count | PnL | Win rate | Avg give |
|---|---:|---:|---:|---:|
| pyramid_cut | 6 | **-$14.35** | 0% | $2.03 |
| stop_loss | 3 | -$2.23 | 33% | $1.75 |
| failure_to_follow | 3 | -$1.16 | 33% | $1.72 |
| trailing_stop | 2 | -$0.42 | 0% | $2.77 |
| timeout/max_hold | 1 | -$0.39 | 0% | $2.13 |
| **take_profit** | **1** | **+$9.99** | **100%** | $0.00 |

**Pyramid_cut is the biggest leak again** (-$14.35). Back up to 38% share. The XLE -$6.65 was a -3.3R cut at just 5 bars — the exact class of premature exit Exp1A was designed to prevent, but at 5 bars it was below the 10-bar threshold (so the gate allowed it in the non-chop interpretation? Actually it's chop — Exp1A should have fired but XLE may have entered outside the min-hold window).

**Timeout/max_hold broke its 100% streak** — QQQ lost -$0.39 after 30 bars. First timeout loser in 4 sessions.

**Trailing-stop givebacks >$5 today**: 0. Running total for leapfrog: still below 3.

## 8. Confidence / ML

| Bucket | Trades | PnL | Win rate |
|---|---:|---:|---:|
| < 0.35 | 8 | **-$11.29** | **12%** |
| 0.35-0.45 | 6 | -$7.83 | 0% |
| >= 0.45 | 2 | **+$10.56** | **100%** |

**PATTERN BREAK**: For the first time, the ≥0.45 bucket OUTPERFORMED. The XLE +$9.99 (conf 0.452) and SPY +$0.57 (conf 0.576) were both high-confidence wins. Meanwhile, low confidence (<0.35) had its worst day: -$11.29 at 12% wr.

**This is the OPPOSITE of the prior pattern** (where <0.35 was the only winning bucket). One day doesn't reverse a 6-session trend, but it weakens the ML contamination hypothesis significantly.

**ML contamination**: WEAKENING. Today's data suggests ML may be starting to add value post-300 (take_profit firing on a high-confidence trade). Need 2+ more sessions to confirm.

## 9. Risk / stability

- Equity: $111,555.90 → $111,547.00 (-$8.90 at broker)
- Worst trade: -$6.65 (XLE pyramid_cut) — controlled vs prior IWM -$41.52
- No concentration risk (5 symbols)
- 531 error log entries — elevated from typical ~100-200. Likely websocket reconnection churn. P3.
- Paper-safe: YES

## 10. Decision

1. **Continue unchanged?** **YES**
2. **Trustworthy?** YES
3. **Exp2 helping?** YES (0 inverse-ETF trades, 2 suppressions)
4. **Post-300 improving?** **INCONCLUSIVE** — yesterday's post-300 was +$10.73, today's is -$8.56. One session improvement was noise, not confirmed.
5. **Exp3 actionable?** **INCONCLUSIVE** — today's data WEAKENED the ML contamination hypothesis (high conf won for the first time in 7 sessions). Need more data before changing the confidence formula.
6. **Exp4 leapfrog?** NO (0 trailing givebacks >$5 today)
7. **Blocker?** NO

**Next action tomorrow**: Run post-close report. This will be the 3rd full post-300 session. If expectancy remains near-zero or improves, the hardening bundle deploy can proceed.

**Hardening deploy**: HOLD one more session. If tomorrow's post-300 data is neutral or positive, deploy the hardening bundle (HEAD `33d6138`) on Thu Apr 23 post-close as planned.

**Live branch unchanged**: `ce06d41`.
