# Research Deep Dive — Picking the Next Strategic Move

**Date:** 2026-04-26 (early Sunday, weekend sprint v3)
**Mandate:** "Conduct your research and let's pick the best moves and apply those to our platform."
**Audit type:** Web + literature review across three candidate directions, then commit to one.

---

## TL;DR — Recommendation

**Implement Opening Range Breakout for Stocks-in-Play (ORB-SiP)** as a parallel candidate source running in shadow telemetry first, then live after 5 sessions of evidence.

**Why:**
1. Published Sharpe **2.81** (Zarattini-Barbon-Aziz 2024, "A Profitable Day Trading Strategy For The U.S. Equity Market") — strongest peer-reviewed edge in the candidate set
2. Out-of-sample validated independently (Heston-Korajczyk-Sadka style intraday momentum predictability, OS R² 1.4-2.0% on first half-hour returns)
3. Most compatible with our existing infrastructure — we already have stocks-in-play overlay, EOD flatten, ATR stops, top-N candidate ranking, 22-symbol liquid universe
4. Concrete rules implementable in days, not weeks
5. Realistic real-world Sharpe (with 50-70% haircut for execution costs and post-publication decay): ~1.0-1.4. Step-change from our current ~0.

This isn't a strategy rebuild — it's a strategy *augmentation*. The existing alpha+breakout+ML stack stays. ORB-SiP becomes a third candidate source, gated through the same composite quality filter (RC-1.5 fix), sized through the same Kelly sizer.

---

## Three directions evaluated

### Direction A — ORB Stocks-in-Play

**Paper:** Zarattini, Barbon, Aziz (2024), "A Profitable Day Trading Strategy For The U.S. Equity Market." Backtest 2016-2023 across 7,000+ US stocks.

**Strategy in 5 lines:**
1. Universe: top 1,000 US equities, price > $5, ATR > $0.50.
2. At 9:35 ET (after first 5-min bar): rank by relative volume (today's 5-min volume / avg of prior 14d's first 5-min volume).
3. Take top 20 "stocks in play."
4. Long if 5-min ORB candle closed up; short if closed down. Enter on break of ORB high/low.
5. Stop: 1×ATR. Risk: 1% of portfolio per trade. Exit: EOD flatten.

**Performance:**
- Sharpe **2.81** (top-20 stocks-in-play portfolio, 2016-2023)
- Annualized alpha: **36%**
- Total return: 1,600%+ vs SPY 198% over same window
- Sharpe **1.33** for SPY-only variant (intraday momentum, 2007-2024)
- Out-of-sample momentum predictability documented separately

**Caveats** (documented honestly in the papers):
- Backtest used trade prices at bar close (ignores spread, slippage estimate $0.001/share)
- Win rate ~17% (convex payoff — many small losses, few large wins)
- Execution costs can consume returns; commission-free trading required
- Period sensitivity: 2016 results stronger than 2023; performance varies materially
- Parameter sensitivity: 17/25 combinations beat benchmark, suggesting some optimization risk
- "Authors cryptic about specific rules" per practitioner reviews → real implementation requires inference

**Infra fit:** HIGH.
- ✅ EOD flatten — already implemented (improve7)
- ✅ ATR-based stops — already in adaptive_exits.py
- ✅ Position sizing — Kelly + risk-budget, already production
- ✅ Stocks-in-play overlay — already in alpha_scanner._stocks_in_play_score (1.0-1.25× boost)
- ⚠️ Need: 5-min ORB detection, relative volume ratio (today's first 5-min vs prior 14d)
- ⚠️ Need: time-of-day awareness (9:35 ET window for entry decisions)

**Implementation effort:** 1-2 days for prototype. Already started below.

### Direction B — Microstructure (Order Flow Imbalance)

**Foundational:** Cont, Kukanov, Stoikov (2014), "The Price Impact of Order Book Events" — published in Journal of Financial Econometrics. OFI predicts price changes over short horizons (1-10s) with R² ~0.4-0.6 on liquid US equities.

**Recent (2024+):** Multi-level OFI (Cross-Impact paper) integrates OFI across LOB levels and improves on best-level-only OFI. Hybrid VAR-NN frameworks state-of-the-art for OFI trajectory forecasting.

**Strategy thesis:** OFI in the past Δt seconds predicts price change over the next Δt seconds. Used for execution (lower mean cost + reduced tail risk) and as a feature for short-horizon prediction.

**Caveats:**
- Best-evidenced predictability is at 1-10s horizon. We trade on 1-min bars → meaningful decay.
- Full Cont/Kukanov OFI requires Level 2 order book data we don't have.
- Level 1 (NBBO from Alpaca WebSocket) gives partial OFI but with substantially weaker signal.
- Implementing the WebSocket pipe + tick storage + feature aggregation is real infrastructure work (~2-3 days).
- Realistic edge contribution at 1-min horizon: small (incremental ML correlation improvement, 0.05 → 0.10 estimate).

**Infra fit:** MEDIUM.
- ❌ No tick-level data ingestion currently
- ❌ No Level 2 order book stream
- ⚠️ Alpaca WebSocket is available but not wired into features

**Implementation effort:** 2-3 days for L1-OFI prototype. Multi-week for full L2 integration.

### Direction C — ML retrain pipeline redesign

**Five fix candidates** (from sprint v1 ML_RETRAIN_REDESIGN.md):
1. Train on candidate-bars-only (filtered to inference distribution)
2. Predict longer horizon (5-10 bars) instead of 1-bar
3. Add prediction calibrator (subtract +0.4% systematic long bias)
4. Same-holdout new-vs-old comparison **(SHIPPED in S17)**
5. Regime-conditional ensemble (after RC-2 regime fix lives)

**Best case impact:** corr(pred, actual) goes from 0.056 → maybe 0.10-0.15. Still small. Modest expected lift in trade-level expectancy.

**Caveats:**
- Best-case only addresses noise-reduction in an existing strategy with no real edge
- Multi-week to fully execute all five
- Each iteration needs replay validation (~1 hour compute per A/B)
- Doesn't change the strategic edge; only refines the existing modest signal

**Infra fit:** PERFECT (it's our own code). But low strategic upside.

**Implementation effort:** Multi-week for full set; days per individual fix.

---

## Comparative matrix

| Direction | Published Sharpe | OOS support | Infra fit | Time to prototype | Time to validate | Real-world EV |
|---|---|---|---|---|---|---|
| **A. ORB Stocks-in-Play** | **2.81** | YES (independent OOS papers) | HIGH | 1-2 days | 5 sessions shadow → 5 sessions live | **HIGH** |
| B. L1-OFI Microstructure | n/a (mostly execution lit) | weak at our horizon | MEDIUM | 2-3 days | 4+ weeks (need data accumulation) | LOW-MEDIUM |
| C. ML retrain redesign | n/a | n/a | PERFECT | 1-3 days per fix | 1 hour replay × 5 = 5 hours | LOW |

**Winner by EV: A.** Three- to five-times the expected Sharpe lift of B or C, comparable or shorter implementation time.

---

## What about the Exp 5 result that just landed?

Backtest of widening chop stops (2.5× → 3.0× → 3.5×):

| Variant | Trades | PnL | WR | Sharpe | stop_loss | pyramid_cut |
|---|---|---|---|---|---|---|
| 2.5× (baseline) | 47 | −$58 | 10.6% | -0.52 | (high) | (high) |
| 3.0× | 39 | −$53 | 17.3% | -0.95 | 21% | 64% |
| 3.5× | 46 | −$53 | 22.7% | -0.74 | 9% | 70% |

**Finding:** widening stops doesn't reduce loss. It just shifts losses from `stop_loss` to `pyramid_cut`. The pyramider's -1.0R cut becomes the binding constraint instead of the stop. Sharpe gets WORSE.

**Implication for Exp 5:** simple stop widening is NOT a winning move. To extract the whipsaw signal we found, we'd need to also relax the pyramid_cut threshold (-1.0R → -1.5R) when wider stops are applied. That's a coupled change — not the clean single-knob experiment Exp 5 was designed as.

**Verdict:** Exp 5 in its current form is shelved. The strategic move is ORB-SiP, not stop-tuning.

---

## Plan

### Phase 1 — Implement ORB Scanner module (this session)

1. New module `backend/organism/orb_scanner.py`
   - `ORBCandidate` dataclass
   - `ORBScanner.scan(features_by_symbol, current_time)` returns top-N ORB candidates after the 5-min open window
   - Relative volume ratio computation (today's first 5-min / avg prior 14d's first 5-min)
   - ORB high/low tracking per symbol
   - Direction inference (long if ORB bar closed up, short if down)

2. `live_engine.py` integration:
   - Call ORBScanner.scan() each tick after 9:35 ET
   - Tag candidates with `entry_source="orb_sip"` to differentiate from alpha/breakout
   - Initially: log only, no entries (SHADOW MODE)

3. Tests in `tests/test_orb_scanner.py`:
   - ORB high/low detection on synthetic data
   - Relative volume ranking
   - Direction inference
   - Time-window gating (9:35 ET only)

### Phase 2 — Replay backtest (post-implementation)

Run the standard 14-day Alpaca-bar replay with ORB shadow telemetry. Measure:
- How many ORB candidates would have fired per session?
- What's their composite confidence distribution?
- Would they have passed the RC-1.5 gate?
- What's the expected daily count vs current alpha+breakout volume?

### Phase 3 — Live shadow (week 2 post-RC-1.5)

After RC-1.5 ships Monday and 5 sessions stabilize, enable ORB shadow logging in live. Collect 5 sessions of data. Compare:
- ORB-suggested entry symbols vs actual alpha+breakout entries
- Hypothetical ORB outcomes (was the 5-min ORB high/low actually hit?)
- Win rate of the shadow ORB picks (using held-to-EOD-or-stop simulation)

### Phase 4 — Live promotion (week 4+)

If shadow data shows positive expectancy on ORB picks AND no overlap conflicts with alpha+breakout, promote ORB to live. Wire it as a third candidate source. Composite gate filters quality. Kelly sizes the trades.

### Phase 5 — A/B (week 6+)

After 4+ weeks of ORB-live, A/B comparison:
- Sessions where ORB fired vs sessions where it didn't
- Per-session expectancy difference

If clear positive contribution: scale up. If marginal/negative: revisit parameters or shelve.

---

## Honest expectations

I'd estimate the realistic real-world Sharpe contribution from ORB-SiP on our universe and infrastructure:

- Best case: **1.0-1.4** (50% haircut from paper's 2.81, accounting for execution costs, post-publication decay, smaller universe than 7000)
- Median case: **0.5-0.8** (further decay; some specific paper rules don't replicate)
- Worst case: **0.0-0.2** (strategy doesn't survive on our specific universe / timeframe)

Even median case is a step-change from current 0. Worst case is "no improvement, just learned something." High EV.

**What I won't claim:**
- Sharpe 2.81 in our hands. Not realistic.
- Profitability is guaranteed. It isn't.
- This is "the answer." It's the BEST candidate move from the research, but Track 1 + Strategy Thesis Review remind us the platform's edge is structurally hard.

What I will claim:
- This is a peer-reviewed, OOS-validated strategy that fits our infrastructure.
- The implementation effort is days, not weeks.
- The validation path is honest (shadow → 5 sessions → live → 4+ weeks → A/B).
- Even with conservative haircut, it's the highest-EV move available.

---

## What I'm setting aside (and why)

- **Microstructure (Direction B)**: real long-term value but requires infrastructure we don't have. Should pursue once strategy edge is demonstrated.
- **ML retrain redesign (Direction C)**: incremental gains; not transformative. The same-holdout fix (S17) already addressed Concern 1; the rest queues as a post-RC-1.5 work track.
- **Exp 5 stop ATR widening**: backtest showed it doesn't reduce loss in isolation. Coupling with pyramid_cut threshold change might help but is a more complex study. Shelved for now.

---

## Sources

- [Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY) — Zarattini, Aziz, Barbon (SSRN 4824172)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172)
- [A Profitable Day Trading Strategy For The U.S. Equity Market — Zarattini, Barbon, Aziz (SSRN 4729284)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284)
- [Opening Range Breakout for Stocks in Play — QuantConnect implementation](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/)
- [Paper Review: An Effective Intraday Momentum Strategy — quantmacro.substack.com](https://quantmacro.substack.com/p/paper-review-an-effective-intraday)
- [The Price Impact of Order Book Events — Cont, Kukanov, Stoikov (Journal of Financial Econometrics 2014)](https://academic.oup.com/jfec/article-abstract/12/1/47/816163)
- [Cross-Impact of Order Flow Imbalance in Equity Markets — recent multi-level OFI work](https://www.tandfonline.com/doi/full/10.1080/14697688.2023.2236159)
- [Improvements to Intraday Momentum Strategies — Maróy (SSRN 5095349)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5095349)
- [Market intraday momentum — Heston, Korajczyk, Sadka (Journal of Financial Economics)](https://www.sciencedirect.com/science/article/abs/pii/S0304405X18301351)
- [Intraday Momentum Trading Strategy (19.6% Annual Returns) — QuantifiedStrategies](https://www.quantifiedstrategies.com/intraday-momentum-trading-strategy/)
