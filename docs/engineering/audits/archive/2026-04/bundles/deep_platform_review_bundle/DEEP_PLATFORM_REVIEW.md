# Deep Platform Review — Architecture, Code, and Algorithm

**Date**: 2026-04-11
**Scope**: Full code review of all 10 organism subsystems (~15,000 lines across live_engine, adaptive_exits, pyramider, kelly_sizer, alpha_scanner, continuous_learner, trading_phase, regime, brain_persistence, ml_signal)
**Method**: Line-by-line code inspection + cross-module analysis + trading data correlation
**Mode**: Read-only. No code changes.

---

## EXECUTIVE SUMMARY

The platform is **mechanically sound** — the persistence stack is well-hardened, the tick loop is coherent, and the system has been trading reliably for a week without crashes or data loss. The structural work is genuinely complete.

The trading algorithm has **three real problems**, in order of impact:

1. **The exit system destroys the edge the entry system generates.** 78% of entries pick the right direction (go green), but 76% of those green trades close as losers because pyramid cuts fire within 2-5 bars on temporary adverse excursions. The system is a good stock-picker with a bad exit timer. Exp1A (10-bar min-hold) directly targets this.

2. **The confidence formula is inverted in production_frozen phase.** Higher confidence correlates with WORSE outcomes (0% win rate at ≥0.45 vs 29% at <0.35). This is because the ML component gets 50% weight but is trained on only ~200 trades — not enough data to produce signal, so it adds noise. The learning-mode formula (65% breakout + 35% tension) was actually better.

3. **Inverse ETFs enter in the wrong regime.** PSQ/SH are designed for trending_down hedging but they enter via the generic breakout path in chop where they have 0% win rate across 6 trades. Exp2 addresses this.

The architecture is **solid but over-complicated in places** — scattered constants, dead code, and two competing exit systems (adaptive_exits vs pyramider) that don't coordinate. None of these are blockers, but they increase maintenance burden and make the system harder to reason about.

---

## PART 1 — WHAT WORKS WELL

### Entry system has genuine directional signal
The alpha scanner + breakout scanner combination picks direction correctly 78% of the time (MFE > 0 for 25/32 trades). This is a real edge. The problem is downstream.

### Regime detection is reasonable
Chop detection (97% of ticks in the Apr 7-10 window) is accurate — the market WAS choppy. The regime detector isn't hallucinating. The issue is that the system trades IN chop instead of recognizing chop as a low-edge environment.

### Persistence is battle-tested
Full Patch F with 8 structural prevention classes survived 734 saves with zero guard fires across 3 sessions. The force-save endpoint provides reliable emergency recovery. The manifest sync is working correctly.

### EOD flatten works reliably
Every session ends with flat positions. No overnight exposure carried. This is critical and working.

### Governance and risk gates are functional
Drawdown checks, warmup gates, stale-data detection, position limits, burst caps — all present and firing correctly in logs.

---

## PART 2 — WHAT'S ACTUALLY BROKEN (algorithm)

### Problem #1: The exit system is the enemy (PROVEN)

**The data speaks clearly:**

| Exit type | Count | Win rate | PnL | Assessment |
|---|---:|---:|---:|---|
| pyramid_cut (all variants) | 24 | 0% | −$63.80 | 100% LOSERS — the system |
| stop_loss | 3 | 33% | −$16.25 | Working as intended |
| horizon_timeout / max_hold | 5 | 100% | +$18.68 | 100% WINNERS — the cure |

The paradox: **the ONLY profitable exit path is "hold until forced out."** Every active exit decision the system makes is wrong.

**Root cause chain:**
1. CUT_FULL at −1.0R is too tight for 1-minute bars in chop. A −1.0R move in chop is NORMAL noise, not a trend failure.
2. CUT_PARTIAL at −0.7R makes it worse — it cuts half the position on a −0.7R dip that typically recovers.
3. The pyramider checks price vs entry every tick (not every bar), so intra-bar noise triggers the cut.
4. In chop, prices oscillate ±1-2R around entry routinely. The cut fires on the FIRST dip.

**What Exp1A does:** Suppresses pyramid cuts in chop until 10 bars held. This gives the entry thesis time to work through the noise.

**What Exp1A doesn't do:** It doesn't fix the underlying problem that CUT_FULL at −1.0R is fundamentally wrong for 1-minute chop. After 10 bars, if the trade is at −1.0R, it STILL gets cut. The min-hold just prevents the premature cut. A deeper fix would widen the R-threshold or eliminate pyramid cuts entirely in chop.

### Problem #2: ML confidence is anti-predictive (LIKELY)

**The evidence:**

| Confidence bucket | Trades | Win rate | PnL |
|---|---:|---:|---:|
| < 0.35 | 21 | 29% | −$25.59 |
| 0.35 – 0.45 | 7 | 0% | −$21.68 |
| ≥ 0.45 | 4 | 0% | −$14.10 |

The production_frozen confidence formula gives ML 50% weight:
```
confidence = 0.50 × ml_conf + 0.30 × breakout + 0.20 × tension
```

But the ML models are trained on only ~200 trades — a tiny sample. The models are fitting noise, producing overconfident signals that are wrong. When a trade has high ML confidence, it's because the ML is strongly wrong, not strongly right.

**The learning-mode formula was actually better:**
```
confidence = 0.65 × breakout + 0.35 × tension
```

This formula produced the low-confidence trades (<0.35) that have the 29% win rate — the only bucket with any wins at all.

**Why this happened:** At trade 200, the system crossed the ML isolation boundary and switched from learning to production_frozen. The confidence formula weight shift from 0% ML → 50% ML happened in one step. There was no gradual ramp-up, no A/B test, no validation that ML was actually adding edge before giving it 50% weight.

**Exp3 prep instruments this.** But the real fix is likely to revert to learning-mode weights in chop, or at least reduce ML weight to 10-20% until the model has 500+ trades of calibration data.

### Problem #3: Inverse ETFs trade in the wrong regime (PROVEN)

PSQ and SH enter via breakout signals in chop. But inverse ETFs in chop are mean-reverting — breakout entries are systematically faked. 0% win rate across 6 trades, 4/6 never went green at all.

Exp2 directly fixes this with a simple regime gate.

---

## PART 3 — ARCHITECTURAL CONCERNS (not blockers, but real)

### 3.1 Two competing exit systems that don't coordinate

The platform has TWO exit systems:
1. **`adaptive_exits.py`** — ATR-based stops, trailing stops, profit locks, FTF, horizon timeouts
2. **`pyramider.py`** — R-multiple based cuts (CUT_PARTIAL at −0.7R, CUT_FULL at −1.0R)

They run on different code paths, at different points in the tick loop, with different state:
- Exits run at Step 5 (lines 1552-1700 in live_engine)
- Pyramid checks run at Step 6 (lines 1882-1960)

The adaptive exit engine uses `ExitLevels` with bars_held, trailing_active, regime-at-entry.
The pyramider uses `PyramidPosition` with R-multiples, highest_price, layer count.

**They don't share state.** When the pyramider tightens a stop (line 1982), it updates `exit_levels.trailing_stop` manually. But if the adaptive exit engine has already computed a different trailing stop on the same tick, the two values conflict. The last writer wins, silently.

**This is why the exit behavior is hard to predict**: for any given trade, BOTH exit systems are evaluating independently, and the first one to fire wins. The trade_history exit_reason tells you WHICH system fired, but not why the OTHER system didn't fire first.

### 3.2 Confidence formula has an unreachable ceiling in learning mode

The learning-mode formula:
```
confidence = 0.65 × breakout_score + 0.35 × tension
```

With typical breakout_score ≈ 0.3-0.5 and tension ≈ 0.2-0.4, the max achievable confidence is approximately 0.43. But the main-book gate in defensive regimes is 0.40-0.45. This means **in defensive regimes, learning-mode trades can't pass the main-book gate at all**. The gate was lowered to 0.25 (the "exploration" gate) as a patch, but the root issue — the formula is mathematically limited — was never fixed.

### 3.3 Prediction horizon mismatch

The ML model is trained with `prediction_horizon = 1` (predict the next bar). But positions are held for 5-30 bars. The ML is answering "will the price go up in the next minute?" while the trading system needs "will the price go up in the next 15-30 minutes?" These are different questions.

### 3.4 Dead code: exploration routing

Lines 2205-2235 in live_engine route candidates to an "exploration" path that was explicitly removed (confirmed at lines 2568-2572). The routing logic silently drops candidates that would have been routed to exploration. This dead code should be deleted.

### 3.5 Scattered constants with no single source of truth

Critical thresholds are defined in 6+ different files:
- `ML_ISOLATION_TRADES = 200` (trading_phase.py)
- `_RISK_BUDGET_PER_TRADE = 0.0025` (kelly_sizer.py)
- `CUT_FULL = -1.0` (pyramider.py)
- `REGIME_STOP_ATR["chop"] = 2.5` (adaptive_exits.py)
- `_MIN_MAIN_CONF = 0.40` (live_engine.py, dynamically computed)
- `MIN_COMPOSITE = 0.15` (alpha_scanner.py)

Changing one often requires changing others, but there's no enforced coupling.

---

## PART 4 — WHAT SHOULD CHANGE NEXT (prioritized)

### Priority 1: Let Exp1A run (Monday observation)
No changes. The 10-bar min-hold gate targets the dominant leak. We need 30-40 trades of data to evaluate.

### Priority 2: Deploy Exp2 after observation (inverse ETF gate)
Simple, high-confidence, orthogonal to Exp1A. $25-30 expected improvement per 4-session window.

### Priority 3: Deploy Exp3 instrumentation + analyze confidence data
The confidence inversion is the deepest algorithmic issue. The side-by-side instrumentation will prove whether reverting to learning-mode weights in chop improves outcomes.

### Priority 4: If data supports it, revert to learning-mode confidence in chop
This would be Exp3B — change the confidence formula to use 65% breakout + 35% tension when regime is chop, regardless of trading phase. This addresses the ML contamination concern directly.

### Priority 5: Consider widening CUT_FULL from −1.0R to −2.5R in chop
Only if Exp1A shows that the 10-bar hold is insufficient (i.e., trades still get cut at −1.0R after 10 bars and lose). This is more aggressive and has higher per-trade risk.

---

## PART 5 — WHAT SHOULD NOT CHANGE

- **Persistence stack** — frozen, working, battle-tested
- **Entry system** — has genuine directional signal (78% MFE rate). Don't break what works.
- **Regime detection** — correctly identifies chop. The problem is what the system DOES in chop, not how it detects chop.
- **EOD flatten** — working perfectly
- **Position limits / governance** — working correctly

---

## PART 6 — THE PATH TO REAL MONEY

### What's missing

1. **Positive expectancy** — current is −$1.92/trade. Need >+$0.50 sustained over ≥3 weeks.
2. **Confidence formula fix** — ML weight needs to be earned, not given. Either reduce ML to 10% or gate it behind calibration quality.
3. **Daily max-loss auto-halt** — current system has no session-level risk limit. A bad day could lose 5-10% of equity before the stop-loss level on any individual trade fires.
4. **Monitoring/alerting** — no Slack/email alerts. Diagnostics warn "no alert channels configured."
5. **Log rotation** — 37MB log file and growing.

### Realistic timeline

| Week | Goal |
|---|---|
| Week 1 (Apr 13-18) | Exp1A observation + Exp2 deploy + Exp3 instrumentation |
| Week 2 (Apr 20-25) | Exp3B (confidence fix if data supports) + cumulative edge assessment |
| Week 3 (Apr 27-May 2) | If positive expectancy emerging: add daily max-loss halt + monitoring |
| Week 4+ | If expectancy sustained: begin Stage 1 ($5K live, max $500/week risk) |

---

## APPENDIX — The 10 most important numbers in this system

1. **0.65 / 0.35** — learning-mode confidence weights (breakout / tension)
2. **0.50 / 0.30 / 0.20** — production-mode confidence weights (ml / breakout / tension)
3. **−1.0R** — CUT_FULL pyramid cut threshold (too tight for 1-min chop)
4. **10 bars** — Exp1A min-hold gate (addresses the timing, not the threshold)
5. **18 bars** — horizon_timeout in learning mode (the ONLY profitable exit)
6. **2.5 ATR** — chop regime stop-loss distance
7. **30 bars** — chop regime max holding period
8. **200 trades** — ML isolation boundary (switches confidence formula)
9. **300 trades** — evolution freeze boundary (activates parameter tuning)
10. **0.25** — minimum confidence gate (lowered from 0.40 for learning mode)
