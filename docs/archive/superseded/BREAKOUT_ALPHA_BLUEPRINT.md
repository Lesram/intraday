# Breakout Alpha System — Blueprint for 100%+ Returns

## 1. Deep Analysis of Current System (v2.0) Results

### What's Working
| Metric | Value | Assessment |
|--------|-------|------------|
| Direction Accuracy | 70.1% | GOOD — ML model predicts direction well |
| Win Rate | 72.9% | GOOD — 78W/29L |
| Sharpe | 2.42 | EXCELLENT — risk-adjusted |
| LONG win rate | 76.7% | STRONG |

### What's Broken — The 7 Killers

**KILLER 1: Trailing stop cuts ALL winners too early**
- 74/107 trades exit via trailing stop (69%)
- Trail activates at only 1% profit — absurdly tight
- Trail step = 50% — takes half your profit immediately
- Result: Average winning trade captures only $225 vs $275 average loss
- Win/Loss ratio = 0.90 (should be >2.0 for great systems)
- FIX: Trail only after 3× ATR profit, trail 25% of excursion, ATR-based not %-based

**KILLER 2: Position sizing is microscopic**
- Average position: $4,917 = 4.9% of $100k
- Even a 10% winner on a $5k position = only $500
- To make $100k (+100%), you need ~200 trades averaging $500 — impossible at this size
- FIX: Increase max position to 10-15%, concentrate in top 3-5 ideas

**KILLER 3: Predicted return is wildly wrong**
- Avg predicted: 0.75% vs Avg actual: 2.16% (3× underestimate!)
- Correlation between predicted and actual: -0.089 (basically zero!)
- The magnitude predictor adds NO value — only direction matters
- FIX: Use direction classifier confidence only, size based on technical setup quality

**KILLER 4: Universe is only 10 stocks**
- 107 trades in 211 days = 0.5 trades/day
- Missing hundreds of breakout opportunities across the market
- The best breakout traders scan 500+ symbols
- FIX: Scan 50-100+ liquid mid/large-cap stocks, find the compressed coils

**KILLER 5: No momentum pyramiding**
- When AMD goes +27.4%, we only hold the initial position
- When TSLA goes +14.9%, we DON'T add more
- Missing the power law of returns — geometric compounding from adding to winners
- FIX: Add to positions at breakout continuation (+1R, +2R, +3R levels)

**KILLER 6: Shorts are net losers**
- 21 short trades, total PnL: -$16
- 57% win rate but avg profit is tiny
- In a bull market, shorts just bleed via slippage+commission
- FIX: Only short in confirmed downtrend/crisis regime, threshold ADX > 30 downward

**KILLER 7: No breakout-specific pattern detection**
- The alpha scanner is generic (ML score + volume + momentum)
- No squeeze detection (BB width at historic lows → expansion)
- No consolidation pattern detection (tight range → breakout)
- No relative volume surge detection (>3× average volume on breakout day)
- FIX: Build proprietary breakout scanner with squeeze + volume + range patterns

## 2. The Path to 100%+ Returns

### Mathematical Framework

To turn $100k → $200k+ in ~200 trading days:
- Need ~$100k in net PnL
- If avg win = $1,000 and win rate = 65%, avg loss = $500
- Expected value per trade = 0.65 × $1,000 - 0.35 × $500 = $475
- Need ~210 positive-EV trades = ~1 per day
- With 50-100 symbols scanned, 1 breakout/day is realistic
- With pyramiding, avg win could be $2,000+ → need only ~70 trades

### Key Principles
1. **LET WINNERS RUN** — the single biggest change
2. **CONCENTRATE when right** — bigger positions on high conviction
3. **SCAN WIDER** — 50-100 stocks, find the compressed springs
4. **PYRAMID WINNERS** — add at continuation breakouts
5. **CUT LOSERS FAST** — 1.5× ATR max stop, no mercy
6. **TREND ONLY** — don't fight the primary trend (eliminate counter-trend shorts in uptrends)

## 3. Implementation Plan — 5 Modules

### Module A: Breakout Pattern Scanner (`backend/organism/breakout_scanner.py`)

Proprietary breakout detection system with 6 pattern detectors:

```
1. SQUEEZE DETECTOR — Bollinger Band width at 20-bar low + Keltner inside BB
   Score: width_percentile_rank (lower = more compressed = higher score)
   
2. VOLUME SURGE — Current volume > 2.5× 20-day average
   Score: vol_ratio / 5.0 (capped at 1.0)
   
3. RANGE CONTRACTION — 10-day ATR / 50-day ATR < 0.6 (coiled spring)
   Score: 1.0 - (atr_10/atr_50), higher = more compressed
   
4. RELATIVE STRENGTH — 20-day return rank vs universe top 20%
   Score: percentile rank [0,1]
   
5. PIVOT BREAKOUT — Close > max(recent 20-day high) by > 0.5× ATR
   Score: (close - pivot) / atr, capped at 1.0
   
6. INSTITUTIONAL FLOW — Large block trades (volume bars > 5× median)
   Score: count of 5×+ volume bars in last 5 days / 5
```

Composite breakout score = weighted average:
- Squeeze: 25%
- Volume surge: 25%
- Range contraction: 15%
- Relative strength: 15%
- Pivot breakout: 15%
- Institutional flow: 5%

Take top 5-8 breakout candidates per scan.

### Module B: Momentum Pyramider (`backend/organism/pyramider.py`)

Add-to-winner system with strict rules:

```
PYRAMID RULES:
1. Initial entry = 60% of target position
2. At +1.5R (1.5× ATR above entry): Add 30% more
3. At +3R (3× ATR): Add final 10%
4. Move ALL stops to breakeven after 2nd add
5. Each add reduces remaining risk — only pyramid when risk ↓
6. Max 3 layers per position
7. Trail entire pyramid from highest-add entry

ANTI-PYRAMID (losers):
- If position hits -0.7R: cut 50% immediately
- If -1R: cut remaining 100%
- NEVER average down
```

### Module C: Fixed Exit Engine v2 (overhaul `adaptive_exits.py`)

Complete overhaul of exits:

```
STOP LOSS (unchanged concept, tighter execution):
- Long: entry - 1.5× ATR (was 2× — tighter = smaller losses)
- Short: entry + 1.5× ATR

TRAILING STOP (MAJOR CHANGES):
- OLD: trail after 1% profit at 50% — THIS KILLED RETURNS
- NEW: trail ONLY after 3× ATR profit using ATR-based distance
- Trail distance = 2.5× ATR from highest close (not from entry)
- In trending regime: trail at 3.5× ATR (wider — let trends run)
- In chop: trail at 1.5× ATR (tighter — grab what you can)
- NEVER trail tighter than the initial stop distance

TAKE PROFIT:
- OLD: 3× risk — barely ever reached (only 3/107 trades)
- NEW: 6× risk in trending, 4× in normal, 2.5× in chop
- Partial take profit: sell 30% at 3R, let 70% run with trail

TIME STOP:
- OLD: 30 bars max — exits winners too early
- NEW: No time limit in trending regime
- In chop: 20 bars max
- In normal: 40 bars max
```

### Module D: Aggressive Position Sizer v2 (overhaul `kelly_sizer.py`)

```
POSITION SIZING CHANGES:
- max_position_pct: 5% → 12% (per-position)
- max_portfolio_pct: 95% → 90% (slightly less to avoid margin issues)
- min_position_usd: $500 → $2,000 (don't waste on tiny positions)

BREAKOUT BONUS SIZING:
- If breakout_score > 0.7: multiply Kelly by 1.5×
- If breakout_score > 0.85: multiply Kelly by 2.0×
- If regime = trending AND breakout_score > 0.7: multiply by 2.5×
- Cap at max_position_pct regardless

CONVICTION SCALING (aggressive curve):
- OLD: 0.5 + confidence * 0.5 → range [0.5, 1.0]
- NEW: 0.3 + confidence * 1.2 → range [0.3, 1.5] — allows OVER-sizing on high conviction
```

### Module E: Expanded Universe Scanner (`scripts/run_hft_organism.py`)

Expand from 10 → 50+ symbols:

```python
BREAKOUT_UNIVERSE = [
    # Mega-cap tech (high liquidity, strong trends)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
    # Semiconductor (high beta breakouts)
    "AVGO", "MRVL", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "ON",
    # Software/SaaS (momentum darlings)
    "CRM", "NOW", "PANW", "CRWD", "SNOW", "DDOG", "NET", "ZS",
    # Biotech/Pharma (binary breakouts)
    "LLY", "ABBV", "MRNA", "AMGN", "GILD", "VRTX",
    # Consumer/Retail (earnings breakouts)
    "COST", "WMT", "TGT", "LULU", "NKE", "SBUX",
    # Energy (commodity breakouts)
    "XOM", "CVX", "SLB", "OXY",
    # Financials (rate-sensitive breakouts)
    "JPM", "GS", "MS", "V", "MA",
    # ETF proxies (for regime/bench)
    "SPY", "QQQ", "IWM", "XLK", "SMH",
]
```

## 4. Execution Order

1. Build Breakout Scanner (Module A) — the crown jewel
2. Fix Exit Engine v2 (Module C) — stop killing winners
3. Build Pyramider (Module B) — amplify winners
4. Update Position Sizer v2 (Module D) — bigger bets
5. Update Master Script v3 with 50+ symbols and all new modules
6. Run backtest → compare to v2.0 results
7. Run test suite → verify no regressions

## 5. Acceptance Criteria

| Metric | v2.0 Baseline | Minimum Target | Stretch Goal |
|--------|:------------:|:--------------:|:------------:|
| Total Return | +11.17% | +50% | +100% |
| Sharpe | 2.42 | >1.5 | >3.0 |
| Win Rate | 72.9% | >60% | >70% |
| Win/Loss Ratio | 0.90 | >1.5 | >2.5 |
| Avg Win | $249 | >$500 | >$1,000 |
| Max Drawdown | 2.55% | <15% | <10% |
| Direction Accuracy | 70.1% | >65% | >72% |
