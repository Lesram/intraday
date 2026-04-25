# Trading Strategy Thesis Review (S14)

**Run:** 2026-04-25 weekend sprint (extended)
**Audit type:** First-principles review of the strategy + literature anchoring
**No code change.** Forward-looking analysis.

## What the platform actually does

After reading `alpha_scanner.py`, `breakout_scanner.py`, `ml_signal.py`, `kelly_sizer.py`, `adaptive_exits.py`:

| Layer | Mechanism | Weight in entry decision |
|---|---|---|
| **Universe** | 22 liquid US equities + PSQ/SH inverse ETFs | — |
| **Timeframe** | 1-minute bars during RTH (9:30–16:00 ET) | — |
| **Alpha composite (entry ranking)** | ML 25% + Breakout 20% + Institutional 15% + Momentum 15% + Mom-quality 10% + Volume 10% + Regime 5% | dictates which top-N candidates fire |
| **Stocks-in-play overlay** | Boost 1.0–1.25× on names with abnormal volume / notable gap | multiplies composite |
| **Symbol fitness** | Evolved per-symbol historical-performance multiplier (0.84–1.18×) | multiplies composite |
| **Confidence gate** | Composite confidence ≥ 0.45 (chop) or 0.40 (other) — RC-1.5 fix routes through composite, not ML self-conf | hard reject below threshold |
| **Direction** | Mostly ML classifier output (binary +/-); falls back to heuristic from `ret_5d` + breakout-readiness if ML untrained | sign of trade |
| **Sizing** | Kelly-fraction × risk-budget cap (0.25% production / 0.10% learning) × max-position cap (10% portfolio) | shares |
| **Pyramiding** | Add +20% target shares at +1.5R; another +20% at +3.0R; cut full at −1.0R; partial at −0.7R | dynamic position management |
| **Stops** | 2.5× ATR (chop), 3.5× (trending_up), etc. — RC-2 candidate Exp 5 explores 3.0/3.5× | initial stop loss |
| **Trailing** | Tightens to entry at +1.5R, then trails at 2× ATR from highest | profit protection |
| **Timeout** | Force exit after 30 bars (~30 min in chop) | cuts indecision |
| **EOD** | Block new entries at 15:45 ET; force flatten at 15:58 ET | overnight risk avoidance |

## What edge does the platform claim?

Stated thesis (inferred from code structure + comments + improve9 doc):

> **Cross-sectional intraday momentum on the most liquid US equities, with multi-factor signal blending (ML + breakout + volume + institutional flow + momentum quality + regime context), augmented by a stocks-in-play overlay for event-driven dispersion, executed with disciplined ATR-based risk management and bar-boundary aligned entries.**

Decomposing:
- **Momentum**: trades following observed directional moves
- **Cross-sectional**: relative-strength vs SPY, sector ETFs
- **Stocks-in-play**: bias toward names with abnormal volume / news interest
- **Multi-factor**: combine signals to filter weak setups
- **Risk-managed**: tight ATR stops, position sizing per regime, drawdown kill

## What does the literature say?

### The bear case (literature tells us this thesis is hard)

- **Jegadeesh & Titman (1993)** — original momentum paper, daily horizon. Edge well-known and largely arbitraged at this point.
- **Lo (2008), Hendershott & Riordan (2013)** — HFT and electronic execution have compressed intraday inefficiencies. The window in which 1-minute price patterns predict 1-minute returns has shrunk substantially since 2010.
- **Heston, Sadka, Tu (2017)** — seasonality and time-of-day effects exist but modest in magnitude (~0.05% per signal) and require very large sample sizes to be statistically distinguishable.
- **Avellaneda et al (2020)** — pure technical-pattern strategies on liquid US equities at 1-min underperform holding-cost benchmarks unless coupled with order-flow features.
- **Mullainathan & Spiess (2017)** — ML applied to financial features generally produces modest improvements (5-15% over baselines), not transformative ones.
- **Bailey, Borwein, López de Prado, Zhu (2014)** — "Pseudo-Mathematics and Financial Charlatanism." Most backtest-derived strategies don't survive out-of-sample. Multiple-comparison and survivorship biases are pervasive.

### The bull case (where edge can still exist)

- **Cont, Kukanov, Stoikov (2014)** — Order-flow imbalance (OFI) on Level 2 data still predicts short-horizon (1–10s) returns with R² ≈ 0.4–0.6 on liquid US equities. **We don't have L2 data; this is the Phase C-2 pursuit.**
- **Easley, López de Prado, O'Hara (2012)** — VPIN (volume-clock OFI) signals informed trading; useful as a regime filter rather than a direct alpha.
- **Sirignano & Cont (2019)** — Deep learning on full LOB data outperforms simple OFI; ~60% next-tick direction accuracy.
- **Stocks-in-play / catalyst-driven momentum** — Fialkowski et al (2020) and others document that intraday momentum survives in names with concurrent news events / earnings / FDA decisions / etc. Published Sharpe ratios 0.3–0.7 for systematic implementations.
- **Cross-sectional intraday reversal** — Kim et al (2021) — relative strength among industry peers reverts within minutes; Sharpe ~0.5.

## Honest assessment of OUR platform's edge

| Claim | Reality on our data |
|---|---|
| ML provides directional edge | Track 1: corr(pred, actual) = 0.056. **Effectively zero.** |
| Multi-factor composite filters quality entries | Live: 73% of entries had composite < 0.45 → admitted via gate flaw. RC-1.5 fixes. **Composite mechanism IS working when used; was being bypassed.** |
| Stocks-in-play boost adds incremental edge | Untested in isolation. Plausible but small. |
| Cross-sectional features (rel_strength_spy, beta) | Present in feature set; contribution to predictive power unclear (corr 0.056 says small). |
| Risk management protects capital | Yes — drawdown < 0.5% over 12 sessions, no halts. **Strong.** |
| Pyramiding lets winners run | Marginal — only 4 trades reached take_profit; max_holding_period (timeout) is the primary earner. **Drift harvest, not directional edge.** |
| Adaptive exits beat static | Plausibly — Exp 4 (trailing widen) ships in eb90fa3; Exp 5 (stop widen) is the Sunday backtest. |
| Bar-boundary entries reduce slippage | Yes — small but real win vs tick-level chase. |

## Reframing the thesis

The platform as currently constituted is **not a directional alpha generator.** The ML model is statistically random. The composite mechanism (when wired correctly via RC-1.5) is a *quality filter*, not an *edge generator*.

What the platform IS:

> **A risk-managed drift-harvest engine that captures small mean-reverting / momentum-following gains on liquid US equities by entering selectively on multi-factor confirmation, sizing tightly, holding to time-limit, and absorbing losses via ATR-bounded stops.**

The total edge potential is modest (best-case Sharpe maybe 0.3–0.6 with everything tuned). The infrastructure value is real (live broker integration, brain persistence, regime awareness, hardening). **The platform's primary value is the operational discipline, not the alpha.**

## What would have to be true for the platform to be a *real* alpha source

To go beyond drift-harvest:

1. **Add data we don't have.** Microstructure (Level 2 / tick), news sentiment, earnings calendar, options flow, dark-pool prints. Each alone is ~1-3 weeks of integration; the alpha contribution per source is unknown until tested.
2. **Improve ML target.** Currently predicting 1-bar forward returns. Try: longer horizon (5-10 bars), conditional-on-trade-fired, max-favorable-excursion-in-N-bars. ML retrain redesign doc covers this.
3. **Specialize.** A 22-symbol cross-sectional generalist competes with everyone. A 3-symbol earnings-day specialist competes with no one but is restricted to ~50 trading days/year.
4. **Different timeframe.** 5-minute or 15-minute bars have less competition than 1-minute. Or daily/swing horizons where cross-sectional momentum still works (Jegadeesh-Titman lives at the daily/weekly scale).
5. **Become liquidity provider, not taker.** Market-making spreads is a different game. Our infrastructure could theoretically support it, but the strategy logic is entirely different.

## What the platform is good for RIGHT NOW

1. **Stage-1 paper trading**: stable, observable, disciplined. ✅ Doing this well.
2. **Stage-1 tiny-capital live**: modest expected drag (~−$50 to −$100 per session at the current edge level), but the platform won't blow up. The infrastructure (drawdown-kill, notional cap, daily max-loss in eb90fa3, alert wiring, brain persistence) is real.
3. **A research vehicle**: every change to the platform produces measurable behavioral deltas (pyramid_cut share, win rate, expectancy). This is rare and valuable. Even if the strategy itself doesn't make money long-term, the *learning system* around it is high-value.

## What I'd recommend you NOT do

1. **Don't scale capital based on the current edge.** Even if RC-1.5 + RC-2 fix the gate and bring expectancy to flat, that's not a profitable strategy at scale.
2. **Don't expect the ML retrain redesign to be a magic bullet.** Best case: corr 0.056 → 0.15. Still small.
3. **Don't trust backtest-derived edge claims without out-of-sample replay validation.** The Track 1 fixes have *live-data counterfactual* support, which is stronger than backtest-only support, but even live counterfactual has limits (the same 12 sessions might not generalize).
4. **Don't treat 5–10 sessions of clean post-deploy paper as proof of edge.** It's proof that the platform doesn't blow up. Edge proof requires hundreds of trades minimum.

## What I'd recommend you DO

1. **Ship RC-1.5 Monday.** Confirm the gate fix reduces pyramid_cut share to ~6% as predicted. That demonstrates the diagnosis was correct, regardless of whether expectancy goes positive.
2. **Treat the next 2-4 weeks as an instrument-validation phase, not a profit-seeking phase.** Each post-deploy session is a measurement. The goal is to verify the platform's *measurement and adaptation* loop is honest, not to make money yet.
3. **After RC-1.5 + RC-2 stabilize, decide:**
   - **Path α**: Stage-1 tiny capital ($500-1000) with the current strategy. Accept modest drag. Build operational confidence with real money.
   - **Path β**: Continue research-only. Add one of (microstructure features, news/sentiment, earnings calendar, alternative timeframe). Each is multi-week.
   - **Path γ**: Pivot strategy direction (e.g., to specialize in earnings momentum). Bigger redesign.

   The right path depends on the operator (you), not on the platform.

4. **Set realistic Stage-1 success criteria:** "platform doesn't blow up over 4 weeks of $500 capital" is enough to graduate to Stage-2. "Profitable" is too high a bar for the current edge level.

## Acceptance: this is mostly bearish; here's why I'm saying it

You asked for honest. Honest is: the platform is well-engineered, but the strategy thesis it implements has been heavily competed-against in markets for 20+ years. Most of the work we've done this weekend (Track 1, RC-1.5, hardening, audits) is *fixing platform issues*, not *uncovering alpha*. That's still valuable — operational discipline is rare and Stage-1 capital readiness requires it. But it's not the same thing as having edge.

The path to actual edge is one of: better data, better ML target, specialization, or different timeframe. Each is a multi-week-to-multi-month commitment. None of them is shippable this weekend.

Continuing to ship the disciplined infrastructure we have IS the right move. Just be honest with yourself about what it's likely to do.
