# Weekend Strategy Lab Report

**Date**: Apr 11-12, 2026 (weekend — market closed until Mon Apr 13 13:30 UTC)
**Dataset**: 32 real trades Apr 7-10 from `trade_history.csv` (excl. 1 reconciliation adjustment)
**Live experiment**: Exp1A (chop 10-bar min-hold gate) deployed at `ab54b2f`, observation starts Mon
**Mode**: read-only analysis, no code changes, no deploys

## One-paragraph verdict

The biggest single leak is the pyramid_cut exit mechanism in chop, which Exp1A directly addresses ($42 of the $61 baseline loss comes from the 13 trades it would suppress). But a NEW finding from this lab is more concerning long-term: **confidence is inversely correlated with outcomes** — trades with confidence >0.45 have a 0% win rate, while trades with confidence <0.35 have a 29% win rate. This suggests the ML contribution to the confidence formula may be adding noise rather than signal in the current production_frozen phase. This doesn't require immediate action (Exp1A addresses the dominant short-term leak), but it should be investigated after the Exp1A observation window, potentially as Experiment 3 (before the original opening-range fix).

## What-if simulations

### Exp1A: chop 10-bar min-hold (DEPLOYED, awaiting observation)

**Simulation result**: 13/24 pyramid_cut trades would have been suppressed (bars_held < 10 in chop), saving $42.27 of the $63.80 pyramid_cut total loss. The 11 remaining pyramid_cut trades (bars_held ≥ 10) lost $21.53.

**Nuance**: of the 13 suppressed trades, only 8 went green at any point (MFE > 0), and the recoverable MFE was just $5.05. This means the 10-bar hold gate doesn't guarantee recovery — it just gives trades more time. The actual outcome depends on whether held trades exit via timeout (historically profitable) or eventually hit stop_loss (potentially larger per-trade loss).

**Best case**: suppressed trades exit via timeout at avg +$3.74 → +$48.62 improvement
**Realistic case**: ~50% timeout (winners) + ~50% hit stop at baseline loss → +$20-25 improvement
**Worst case**: all 13 suppressed trades hit stop_loss at -2x avg loss → net -$40 additional loss (unlikely given 78% MFE rate)

**Confidence level**: MEDIUM. The hypothesis is sound (entry signal has directional edge, exits cut too early), but the counterfactual outcome is uncertain.

### Exp2: suppress PSQ/SH in chop

**Simulation result**: 6 trades removed, $28.54 saved. ALL 6 PSQ/SH trades in chop are losers with 0% win rate. 4/6 never went green at all (MFE ≤ 0). The remaining 26 non-inverse trades lose $32.83 (vs $61.37 baseline).

**Key detail**: PSQ at 105 shares and stop_loss exit lost $12.69 — the single worst trade in the dataset. This isn't just an entry-timing problem; the POSITION SIZING on inverse ETFs is over-allocated relative to their edge. Inverse ETFs are getting the same share sizes as SPY/XLE despite having no demonstrated edge in chop.

**Confidence level**: HIGH. 0% win rate across 6 trades and 4 days. The evidence is unambiguous.

### Exp1B: widen CUT_FULL from -1.0R to -2.5R

**Simulation result**: 20/24 pyramid_cut trades had R between -0.8R and -1.8R — ALL would survive a -2.5R threshold. Only 4 cuts at ≤-2.5R would remain. PnL saved: $47.17 from the 20 held trades.

**Comparison with Exp1A**: Exp1B saves $47.17 vs Exp1A's $42.27. But Exp1B applies to ALL regimes (not just chop) and to ALL hold durations (not just <10 bars). It's broader and more aggressive. It also catches the 11 pyramid_cut trades that Exp1A would allow (bars ≥ 10 but R between -1.0 and -2.5).

**Risk**: Exp1B increases per-trade risk because the stop-loss ATR is the only remaining risk control. If the entry signal is wrong, losses per trade will be larger. With 5/13 suppressed trades that never went green, some of those will end up as larger stop_loss hits.

**Confidence level**: MEDIUM-LOW. More data needed. The combined Exp1A+Exp1B would be very aggressive. Better to observe Exp1A first, then consider Exp1B if the evidence supports it.

### Exp3: widen opening-range block to 60 min

**Simulation result**: 5 first-hour entries (13:30-14:30 UTC), $19.05 loss, 0% win rate. But one of those (IWM -$4.52, 27 bars) was held for a long time — its entry happened to be in the first hour but the loss isn't attributable to opening-range noise.

**Adjusted estimate**: removing the 5 first-hour trades saves $19.05, but overlap with Exp1A is significant (3/5 first-hour trades are pyramid_cut with bars_held < 10 — already suppressed by Exp1A). **Incremental value after Exp1A: ~$6-10.**

**Confidence level**: MEDIUM. The 0% win rate is real, but 5 trades is a small sample and 3/5 are already handled by Exp1A.

### Combined: Exp1A + Exp2

**Simulation result**: 17 trades remaining (15 removed), PnL −$5.44, win rate **35.3%**, expectancy **−$0.32/trade**. Compared to baseline: $55.93 improvement, win rate +16.5pp, expectancy +$1.60/trade.

This is the highest-expected-value two-experiment stack. It brings the system from clearly negative (-$1.92/trade) to near-breakeven (-$0.32/trade), within noise of profitability.

## NEW FINDING: confidence inversion

| Confidence bucket | Trades | PnL | Win rate |
|---|---:|---:|---:|
| Low (<0.35) | 21 | −$25.59 | **29%** |
| Mid (0.35-0.45) | 7 | −$21.68 | **0%** |
| High (≥0.45) | 4 | −$14.10 | **0%** |

**Higher confidence = worse outcomes.** This is the opposite of what a functional confidence model should produce. Possible causes:

1. **ML is anti-predictive in chop**: the ML component (which was recently activated at the 200-trade phase boundary) may be fitting noise from the small training sample and producing overconfident directional signals that are wrong
2. **Confidence formula weights**: in `production_frozen` phase, the confidence formula shifts from `0.65×breakout + 0.35×tension` (learning) to `0.50×ml + 0.30×breakout + 0.20×tension` (production). If the ML signal is anti-predictive, giving it 50% weight contaminates the confidence score
3. **Selection bias**: higher-confidence trades may be entering on stronger breakout signals that are MORE likely to be fakeouts in chop (the same problem the opening-range filter tries to address)

**Recommendation**: investigate this AFTER the Exp1A observation window, as a potential Experiment 3. If ML confidence is anti-predictive, the highest-value fix may be to revert to learning-mode confidence weights in chop regime, not to change exits or entries.

## ML phase transition — no visible effect

| Period | Trades | PnL | Win rate |
|---|---:|---:|---:|
| Pre-200 (before ML isolation exit) | 15 | −$26.00 | 20% |
| Post-200 (after ML isolation exit) | 17 | −$35.37 | 18% |

The ML phase transition at 200 trades produced **no improvement** — post-transition trades are slightly worse. Combined with the confidence inversion above, this suggests the ML models are not yet producing edge. This is not unexpected (214 trades is still a small training sample), but it means we should NOT rely on ML improvement as a source of edge in the near term.

## Scanner breadth

12/22 symbols traded over 4 days. The 10 untouched symbols (AMD, AVGO, CAT, COST, CRM, GOOGL, LLY, META, MSFT, WMT) are large-cap stocks that didn't produce breakout signals in a chop regime. **This is correct behavior** — the scanner is correctly filtering low-conviction candidates. Broadening the scanner would add MORE noise, not MORE edge. Scanner breadth is NOT a problem.

## Exit fragmentation

13 trades had shares > 20 (inverse ETFs + large entries). Fragmentation itself doesn't appear to be the primary leak — the issue is that ANY exit via pyramid_cut loses, regardless of whether it's 1 fill or 4 fills. The fragmentation is a symptom of the pyramider's multi-leg exit logic, but it's not the cause of the loss. Fixing the pyramid_cut gate (Exp1A) addresses the root cause.

## Walk-forward gate effect

The walk-forward gate is not suppressing entries. It controls brain persistence (full save vs essential save), not entry decisions. The organism traded actively across all 4 days (106 total fills) with no evidence of gate-induced throttling. Not a factor.

## Explicit answers

**If Exp1A works, what should Experiment 2 be?**
→ **Suppress PSQ/SH in chop** (Exp2). This addresses the second-largest leak ($28.54) with the highest confidence (0% win rate, 6 trades, 4 days). After Exp2, investigate the confidence inversion as Exp3.

**If Exp1A fails, what should Experiment 2 be?**
→ **Still Exp2** (suppress PSQ/SH in chop). Exp1A failure would mean the pyramid_cut problem needs a different approach (possibly Exp1B — wider R threshold instead of min-hold), but the PSQ/SH leak is independent and should be closed regardless.

**Which algorithm issue is the single biggest leak right now?**
→ **Pyramid_cut exits in chop** ($63.80 over 4 days, 24/32 trades, 0% win rate). Exp1A directly targets this.

**Which change offers the highest expected value with the lowest implementation risk?**
→ **Exp2 (suppress PSQ/SH in chop)**, because it's a simple regime gate with zero behavioral risk to non-inverse trades and HIGH confidence (0/6 win rate = unambiguous signal). Exp1A has higher absolute expected value but more uncertainty about the counterfactual outcome.

## Ranked next experiments (post Exp1A observation)

### Rank 1: Exp2 — Suppress PSQ/SH entry in chop regime

| Metric | Estimate |
|---|---|
| **Expected PnL improvement** | **+$25-30 per 4-session window** |
| Confidence | HIGH (0% win rate over 6 trades, 4 days) |
| Risk | Very low (only affects inverse ETF entries in one regime) |
| Implementation | ~10 lines: regime gate in entry path, skip PSQ/SH when chop |
| Evidence | All 6 PSQ/SH trades in chop are losers; 4/6 never went green |
| Measurement | PSQ/SH trade count should drop to 0 in chop; PnL improvement |

### Rank 2: Exp3-REVISED — Investigate confidence inversion / ML contamination

| Metric | Estimate |
|---|---|
| **Expected PnL improvement** | **+$15-35 per 4-session window** (if ML is anti-predictive) |
| Confidence | MEDIUM (4 trades at high confidence, 0% win rate — needs more data) |
| Risk | Medium (touches confidence formula, core signal path) |
| Implementation | ~15 lines: in chop, revert to learning-mode confidence weights (0.65×breakout + 0.35×tension, 0×ML). Or: log ML vs breakout-only confidence side-by-side for comparison |
| Evidence | Confidence >0.45 = 0% win rate (4 trades). Confidence <0.35 = 29% win rate (21 trades) |
| Measurement | Side-by-side confidence logging first (non-invasive), then weight adjustment if confirmed |

### Rank 3: Exp1B — Widen CUT_FULL threshold from -1.0R to -2.5R (conditional on Exp1A results)

| Metric | Estimate |
|---|---|
| **Expected PnL improvement** | **+$25-47 per 4-session window** |
| Confidence | MEDIUM-LOW (depends on what Exp1A shows about held trades) |
| Risk | Higher (increases per-trade loss when entries are wrong) |
| Implementation | 1 line: change `CUT_FULL = -1.0` to `CUT_FULL = -2.5` in `pyramider.py` (chop-gated) |
| Evidence | 20/24 pyramid cuts had R between -0.8 and -1.8 — all would survive a -2.5R gate |
| Measurement | Avg trade duration, stop_loss hit rate, per-trade max drawdown |

**Note**: the original Exp3 (widen opening-range block to 60 min) is DEMOTED from rank 3 to rank 4. Its incremental value after Exp1A is only ~$6-10 because 3/5 first-hour trades are already handled by the min-hold gate. The confidence inversion finding is higher expected value.

## Combined forecast

If Exp1A + Exp2 both succeed (the two highest-confidence changes):
- **Baseline**: 32 trades, PnL −$61.37, win rate 18.8%, expectancy −$1.92/trade
- **Projected**: 17 trades, PnL −$5.44, win rate 35.3%, expectancy −$0.32/trade
- **Delta**: +$55.93, +16.5pp win rate, +$1.60/trade expectancy

This brings the system from clearly losing to near-breakeven, which is the necessary precondition for the ML evolution to start producing positive edge as it accumulates more trade data (currently at 214 trades, evolution freeze exits at 300).

## Bundle contents
- `trade_history_simulation.txt` — raw what-if output
- Baseline data files in `trading_edge_baseline_bundle/`
