# Microstructure Features — Research Note

**Status:** RESEARCH — RC-3+ candidate, requires new data feed
**Author:** Saturday 2026-04-25 weekend sprint, S10

## Why microstructure

Track 1 found ML correlation with returns = 0.056 — essentially zero. Most of our 79 features are price-based (ret, ATR, RSI, MACD, etc.) — the same features as every retail strategy. Intraday momentum on liquid US equities is the most-arbitraged corner of finance.

**Microstructure features** capture order-flow dynamics that are:
- Less visible to typical retail strategies
- More predictive on short horizons (seconds to minutes)
- Documented in academic literature with positive (small) edge

The honest expectation: microstructure won't 10× our edge. It might give us a measurable +0.05 to +0.15 corr improvement in ML predictions, which compounds across the gate filter.

## What the literature says

### Cont, Kukanov, Stoikov (2014) — "The price impact of order book events"

Order Flow Imbalance (OFI):
```
OFI(t) = sum over events at time t of:
    (+volume_at_bid if event was bid increase or ask decrease)
    (-volume_at_bid if event was bid decrease or ask increase)
```

Empirical finding: OFI predicts price changes over short horizons (1-10 seconds) with R² ~0.4-0.6 on liquid US equities. Much higher than features derived from trade prints alone.

**Implication for us**: if we had Level 2 order book data, OFI computed over 1-min windows could be a strong feature. We currently use Level 1 (NBBO) only via Alpaca.

### Easley, López de Prado, O'Hara — "Flow toxicity and liquidity"

Volume-Synchronized Probability of Informed Trading (VPIN):
- Measures order-flow imbalance in volume time, not clock time
- Spikes in VPIN precede flash crashes
- Useful as a regime filter (avoid trading when VPIN > threshold)

### Avellaneda, Stoikov — "High-frequency trading in a limit order book"

Optimal market-making formulas. Less directly applicable since we're not market-making, but the modeling framework for inventory + adverse selection is influential for thinking about exit timing.

### Recent (2020+) — ML on order book features

Sirignano & Cont (2019) — Universal features in deep learning models on LOB data. Out-of-sample prediction of next-tick price direction with ~60% accuracy on equities. Suggestive that features beyond OFI (full LOB shape, time-on-book, etc.) carry information.

## What fits our infrastructure

### What we have

- Alpaca paper data: 1-minute OHLCV bars
- No Level 2 order book stream
- No tick-by-tick trade prints

### What we'd need

For OFI / VPIN / LOB features:
- Tick-level trade and quote data (Alpaca Pro tier or another vendor like Polygon, IEX Cloud, Databento)
- Storage for tick streams (~1-10 GB/day per liquid symbol)
- New ingestion pipeline (currently the system is bar-aware, not tick-aware)

This is meaningful infrastructure work, not a feature engineering tweak.

## Realistic candidate features for our data

Even without tick data, we can derive partial proxies from 1-min bars:

1. **Bar-wick imbalance**: `(close - low) / (high - low)` — already roughly captured by `close_to_high`. Higher value = buying pressure during the bar.

2. **Trade-vs-volume disparity**: SPY-relative volume on bars where SPY was flat. Indicator of news / interest.

3. **Time-of-day-conditional features**: open-15min vs midday vs close-15min behavior differs. Already partially captured but could be more explicit.

4. **Cross-asset divergences**: (already in our features as `rel_strength_spy`) but could include sector ETF and VIX divergences.

5. **Bid-ask spread proxy**: `(high - low) / close` is a poor proxy. Real spread requires Level 1 data which Alpaca provides via the WebSocket — we just don't pipe it into features.

The realistic incremental ML correlation improvement from these features alone is small (perhaps 0.02-0.05 added to current 0.056). Not transformative.

## Recommendation

**Phase C-2 is meaningful research but NOT a near-term win.**

- The features we'd benefit from most (OFI, VPIN) require infrastructure we don't have.
- Adding the infrastructure is a real project: data feed contract change, ingestion code, storage, backtests on tick data. Multi-week.
- Without tick data, what we can derive from 1-min bars is incremental, probably +0.05 corr at best.

**Better near-term moves** (already in this weekend's work):
1. Composite-gate fix (RC-1.5) — addresses the immediate ML-driven leakage
2. Regime classifier fix (RC-2) — gets the right calibration into the right regime
3. ML weight drop (RC-2) — de-emphasizes the noisy signal until we improve it
4. Phase C-1 (RC-3) — separates concerns so we can swap in better models later

**When to actually pursue microstructure:**
- After Phase C-1 ships (the architecture lets us add new models cleanly)
- When we've shown the platform is profitable with current data (otherwise we'd just be over-engineering for a strategy that doesn't work)
- When we have budget for a tick-data feed (~$200-500/month for retail-friendly providers)

Estimated calendar time to prototype: 4-8 weeks once infrastructure is in place.

## Open question for the operator

Do you want me to draft a small Alpaca-WS-based proof-of-concept for **Level 1 order flow imbalance** (which we *can* compute from real-time WebSocket NBBO updates)? That would be ~2 days of work, partial-OFI feature, no new vendor needed. Output: feasibility score with empirical correlation against forward returns.

If yes, that becomes an Exp 7 candidate. If no, queue everything here as Phase C-2 longer-term.
