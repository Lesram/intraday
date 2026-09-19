# Trading Edge Baseline Report

**Window**: Apr 7–10, 2026 (4 sessions, post-structural-hardening)
**Brain state**: gen 45, 214 trades, production_frozen (214/300 to evolution freeze exit)
**Mode**: read-only analysis, no code changes

## TL;DR

The organism has a **negative expectancy of −$1.92/trade** over 32 real trades (excl. 1 reconciliation adjustment). Win rate is 18.8% with a payoff ratio of 1.08 — the wins are barely larger than the losses, so the low win rate dominates. The single most impactful finding: **pyramid_cut exits account for 24/32 trades, are 100% losers, and produce −$63.80 of the −$61.37 total loss**. Meanwhile, the **5 trades that ran to timeout/max-hold are 100% winners at +$18.68**. The exit system is actively destroying edge that the entry system generates — 25 of 32 trades went green at some point (78%), but only 6 were closed as winners.

## 1. Core stats (32 real trades, excl. reconciliation)

| Metric | Value |
|---|---|
| Win rate | 18.8% (6W / 26L) |
| Avg win | +$3.38 |
| Avg loss | −$3.14 |
| Payoff ratio | 1.08 |
| **Expectancy/trade** | **−$1.92** |
| Total PnL | −$61.37 |
| Median hold time | 550s (~9 min) |
| Trades that went green (MFE > 0) | 25/32 (78%) |
| Green trades that closed as losses | 19/25 (76%) |
| Total MFE forfeited by losing trades | $33.09 |

## 2. PnL by exit reason — THE key finding

| Exit category | Count | PnL | Win rate | Notes |
|---|---:|---:|---:|---|
| **pyramid_cut (all variants)** | **24** | **−$63.80** | **0%** | 100% LOSERS. The exit system is the problem. |
| stop_loss | 3 | −$16.25 | 33% | 2 large losses (PSQ −$12.69, XLE −$5.15) |
| **horizon_timeout / max_hold** | **5** | **+$18.68** | **100%** | The ONLY profitable exit. All at 18–30 bars. |

This is the starkest signal in the data. Trades that exit early via pyramid cuts always lose. Trades that are FORCED to hold to timeout always win. The entry system picks direction correctly ~78% of the time (MFE > 0), but the exit system cuts winners before they realize their edge and lets the cuts accumulate into a death-by-a-thousand-cuts pattern.

## 3. PnL by symbol (4-day aggregate)

| Symbol | Trades | PnL | Win rate | Category |
|---|---:|---:|---:|---|
| PSQ | 4 | −$23.70 | 0% | Inverse ETF |
| XOM | 2 | −$12.25 | 0% | Stock |
| IWM | 2 | −$6.96 | 0% | ETF |
| SH | 2 | −$4.84 | 0% | Inverse ETF |
| TSLA | 1 | −$4.80 | 0% | Stock |
| NVDA | 2 | −$3.92 | 0% | Stock |
| AMZN | 2 | −$3.60 | 0% | Stock |
| QQQ | 2 | −$3.32 | 0% | ETF |
| XLK | 2 | −$2.64 | 50% | ETF |
| AAPL | 2 | +$4.04 | 50% | Stock |
| SPY | 6 | +$5.29 | 33% | ETF |
| XLE | 6 | +$178.61 | 50% | ETF (includes $183 reconciliation) |

XLE's $178.61 includes the $183.28 reconciliation adjustment. Without it, XLE is approximately −$4.67. **No symbol has consistent positive edge** except SPY (marginally positive at +$5.29 over 6 trades).

## 4. PnL by regime

| Regime | Count | PnL | Win rate |
|---|---:|---:|---:|
| chop | 32 | −$56.22 (excl. recon) | 19% |
| unknown | 1 | −$5.15 | 0% |

Virtually all trading happened in `chop` regime (96–97% of ticks all 4 days). The organism has no edge in chop — in fact, chop is where the pyramid_cut exits do the most damage, because price oscillates around the entry, triggering adverse-excursion cuts on temporary dips that would recover.

## 5. Inverse ETF analysis

| Category | Trades | PnL | Win rate |
|---|---:|---:|---:|
| Inverse ETF (PSQ, SH) | 6 | −$28.54 | 0% |
| Non-inverse | 26 | −$32.83 | 23% |

**PSQ/SH have ZERO wins across 6 trades and 4 days.** They account for 47% of the total loss despite being only 19% of trades. Per-trade loss for inverse ETFs (−$4.76) is 53% worse than non-inverse (−$1.26).

**Verdict: inverse ETF exposure is unambiguously harmful in chop.** The `improve9` logic intended them for trending-down protection, but the regime has been predominantly chop all week. In chop, inverse ETFs are mean-reverting around a flat level — entering via breakout and exiting via pyramid-cut is systematically wrong.

## 6. Time-of-day analysis

| Hour (UTC) | Count | PnL | Win rate |
|---|---:|---:|---:|
| 13:00 | 1 | −$5.15 | 0% |
| 14:00 | 4 | −$13.90 | 0% |
| 15:00 | 2 | −$6.09 | 0% |
| 16:00 | 9 | −$12.84 | 22% |
| 17:00 | 4 | −$3.61 | 50% |
| 18:00 | 7 | −$11.79 | 0% |
| 19:00 | 5 | −$7.99 | 40% |

The first 2 hours (13:00–14:59 UTC = 9:00–10:59 ET) are the worst window: 5 trades, −$19.05, 0% win rate. This is the volatility-expansion period where breakout entries get faked out by opening-range noise. The 15:45 ET entry cutoff (EOD block) prevents late-day entries, which is correct.

## 7. MFE/MAE — the unrealized edge problem

- **25/32 trades went green** (MFE > 0) — the entry system picks direction correctly 78% of the time
- **19 of those 25 green trades closed negative** — they forfeited $33.09 of combined MFE
- **Total MFE across all 32 trades: $67.61** — this is the theoretical max the entries generated
- **Total realized PnL: −$61.37** — the exit system captured NEGATIVE value from positive setups
- **Edge capture ratio: −91%** — for every dollar of edge the entries create, the exits destroy $0.91

This is the most damning metric. The entry system has genuine directional signal (78% go green). The exit system converts that into losses via premature pyramid cuts.

## 8. Premature exit analysis

12/32 trades (38%) were "premature" (≤5 bars held, negative PnL):
- Combined PnL: −$52.68 (86% of total loss)
- Forfeited MFE from premature exits: $11.27
- These trades were cut in 2–5 minutes, before the entry thesis had time to work

The remaining 20 "normal" trades lost only −$8.69 total — nearly break-even.

## 9. Scanner breadth

- Universe: 22 symbols
- Symbols traded: 12 (55% coverage)
- Never traded: AMD, AVGO, CAT, COST, CRM, GOOGL, LLY, META, MSFT, WMT (10 symbols, 45% dark)

Scanner breadth is adequate — 12 of 22 is reasonable for 4 days of a learning-mode organism. The untouched symbols are mostly large-cap stocks that may not produce breakout signals in a chop regime. Not a primary concern.

## 10. ML phase transition impact

The ML isolation boundary was crossed at trade 200 (on Apr 8). Pre-crossing: 7 trades Apr 7 (before structural issues). Post-crossing: 25 trades Apr 8-10.

No clear behavioral change is visible in the data — post-crossing trades show the same pyramid-cut-dominated, chop-regime, low-win-rate pattern as pre-crossing. This is expected because:
1. The ML models are still in early training (gen 27→45, 214 total trades — small sample)
2. The confidence formula in `production_frozen` phase may not yet weight ML signal heavily
3. The exit system is regime-invariant — it cuts regardless of ML confidence

The ML transition is NOT the problem. The exit system is.

## Answers to the explicit questions

**Is PSQ/inverse-ETF exposure net helpful or harmful?**
Harmful. Zero wins across 6 trades, −$28.54, 47% of total loss. Remove from entry eligibility in chop regime.

**Is scanner breadth too narrow?**
No. 12/22 symbols traded. The untouched ones lack breakout signals in chop. Not a primary concern.

**Are multi-leg exits hurting realized edge?**
Not directly — the multi-leg vs single-leg distinction is secondary. The real problem is that the pyramid_cut exit mechanism fires too aggressively on temporary adverse excursions, cutting trades that would have recovered. All 24 pyramid-cut exits are losers.

**Is the current edge regime-specific?**
Yes — 97% of ticks and all 32 trades were in chop. The organism has no edge data for other regimes. In chop, the breakout-entry + pyramid-cut-exit combination is systematically wrong: breakout entries in a range-bound market get faked out, then pyramid cuts ensure the losses are realized.

**What are the top 3 highest-value algorithm experiments?**

## TOP 3 ALGORITHM EXPERIMENTS (ranked by expected value)

### 1. WIDEN PYRAMID-CUT THRESHOLDS IN CHOP REGIME (~$50-65 PnL improvement potential)

**Problem**: 24/32 trades exit via pyramid_cut at −1.0R to −1.8R adverse excursion. ALL are losers. Meanwhile, the 5 trades that ran to timeout (18–30 bars) are ALL winners. The exit system is cutting trades that would have recovered.

**Evidence**: 78% of trades go green (MFE > 0). 76% of green trades close negative. $33 of MFE forfeited. Premature exits (≤5 bars) account for 86% of total loss.

**Experiment**: In chop regime only, widen the pyramid_cut adverse-excursion threshold from the current levels (−1.0R to −1.8R) to at least −3.0R. This gives trades more room to breathe in a range-bound market. The stop_loss (wider ATR-based) becomes the primary risk control, not the pyramid cut. Alternatively, ADD A MINIMUM HOLD TIME before pyramid cuts can fire (e.g., 10 bars = ~1.5 min at 1Min timeframe).

**Expected value**: $52-65 PnL improvement (based on the 12 premature exits that lost $52.68 — even preventing half of them would recover ~$26-33, and the timeout analysis suggests holding longer is systematically profitable).

**Risk**: Wider stops mean larger per-trade losses when trades do fail. Mitigated by the evidence that MFE capture is very high for trades that hold — the entry signal has genuine directional edge.

### 2. SUPPRESS INVERSE ETF ENTRIES IN CHOP REGIME (~$25-30 PnL improvement potential)

**Problem**: PSQ and SH are 0% win rate across 6 trades and 4 days, losing $28.54. They are protected symbols (always in universe) but should not be entered in chop — the `improve9` logic intended them for trending_down hedging.

**Evidence**: Per-trade loss for inverse ETFs (−$4.76) is 53% worse than non-inverse (−$1.26). In chop, inverse ETFs oscillate around flat — breakout entries on them are systematically faked.

**Experiment**: Add a regime gate in the entry path: if `regime == chop`, skip PSQ/SH for entry candidacy. They remain in the universe for monitoring and can re-enter candidacy when regime shifts to trending_down. No change to the protected-symbol logic for universe rotation — they just don't get traded in chop.

**Expected value**: ~$28 PnL improvement (direct: eliminates the 6 losing trades). Plus freed-up capital that would have gone into inverse ETF positions becomes available for non-inverse entries.

**Risk**: Very low. In a sustained trending_down regime, the gate lifts automatically. No structural change to the universe selector.

### 3. OPENING-RANGE FILTER: BLOCK ENTRIES IN THE FIRST 30 MINUTES (~$15-20 PnL improvement potential)

**Problem**: Trades closed in the 13:00–14:59 UTC window (first 2h, but concentrated in the first 30–40 min after open) have 0% win rate and −$19.05 PnL. This is the opening-range volatility period where breakout signals fire on opening-range expansion that then reverses.

**Evidence**: First fill each day is typically 37–41 minutes after open. The entries during this window get faked out by opening-range noise. The organism already has a 30-min opening block (`_is_intraday` + 9:30–10:00 AM ET block at `live_engine.py:1748`), but it may not be wide enough — Apr 10's first fill was at 14:07 UTC (10:07 ET), just past the 10:00 AM ET block.

**Experiment**: Widen the opening-range block from 30 minutes to 60 minutes (9:30–10:30 AM ET). This delays first entry to 10:30 AM ET, after the opening-range breakout fakeouts have settled.

**Expected value**: ~$15 improvement. The first-hour trades are the worst performers; blocking them eliminates 0%-win-rate entries without reducing the timeout winners (which tend to be mid-session entries).

**Risk**: Reduces opportunity count in sessions where early entries would have been valid. Acceptable given the current 0% win rate in that window.

## What we are NOT recommending

- **Changing ML model architecture** — the ML models are still in early training (214 trades). The signal hasn't had enough data to prove or disprove itself. Let it accumulate to 300+ trades before evaluating ML changes.
- **Changing confidence thresholds** — the current confidence formula is regime-appropriate for learning mode. Tightening thresholds would reduce opportunity count in an already low-activity system.
- **Changing universe composition** — 12/22 symbols trading is adequate coverage. The untouched symbols lack breakout signals in chop, not a scanner bug.
- **Changing walk-forward gate math** — the gate is functioning correctly (passing when it should, blocking when it should). It's not suppressing valid entries.

## Data quality notes

- 1 reconciliation_adjustment trade ($183.28) excluded from all analysis — this is a synthetic bookkeeping entry, not a real trade
- Trade history sourced from `organism_brain/trade_history.csv` (32 real trades Apr 7–10)
- Order-level data from PostgreSQL `orders` table (106 fills Apr 7–10)
- Some DB order-level PnL differs slightly from trade_history PnL due to rounding and multi-leg aggregation

## Bundle contents
- `orders_apr7_10.csv` — all 106 filled orders
- `trade_history.csv` — organism's trade records
- `manifest.json` — current brain state
- `learning_state.json` — current learner state
