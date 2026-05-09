# Intra Strategy Rebuild Master Roadmap

Date: 2026-05-09
Branch: `codex/v13-phase2-expectancy`
Status: active execution roadmap

## North Star

Intra should become a strategy-governed intraday research and trading platform, not a single blended signal blender. Every candidate must be born from a specific strategy, measured against benchmarks and null models, and promoted only when it proves after-cost edge.

No strategy gets more capital because it sounds plausible. It earns capital by surviving evidence.

## Non-Negotiable Guardrails

1. Do not promote the current ORB scanner live.
2. Keep `ORGANISM_ORB_LIVE_ENABLED=false`, `ORGANISM_EOD_LIVE_ENABLED=false`, and `ORGANISM_MEAN_REVERSION_LIVE_ENABLED=false` unless a specific strategy passes promotion gates.
3. Keep ML excluded from live direction, ranking, and sizing until it proves monotonic out-of-sample value as a meta-filter.
4. Do not increase max notional or position count until a specific `strategy_id` earns it.
5. Unknown `strategy_id` must never be allowed to submit a live order.
6. No pyramiding for Tier 0, Tier 1, or Tier 2 strategies.
7. Inverse ETFs are intraday hedge/short proxies only and must flatten by close unless separately proven.

## Core Architectural Change

Current flow:

```text
blended score -> shared gates -> shared sizing -> order -> after-the-fact label
```

Target flow:

```text
signal hypothesis -> strategy_id -> strategy-specific gates -> strategy-specific sizing
-> benchmark/null comparison -> promotion/demotion -> capital allocation
```

The current alpha/breakout composite becomes `strategy_id=alpha_baseline`. It can continue in guarded mode, but it is no longer the master strategy.

## Strategy Families

### Priority 1 - ETF/Index Intraday Momentum With Gamma/Volatility Overlay

This is the top near-term research lane. It has cleaner peer-reviewed support, lower execution friction, fewer symbols, and better fit with Intra's 1-minute infrastructure.

Initial universe:

- `SPY`
- `QQQ`
- `IWM`
- `XLK`
- `XLE`

Predeclared variants:

- Variant A: enter near `15:20-15:40 ET`; direction from first-half-hour return and same-direction rest-of-day confirmation.
- Variant B: enter near `15:20-15:40 ET`; direction from rest-of-day return; require realized-volatility and volume z-score filters.
- Variant C: same as B, but bearish SPY/QQQ routes to SH/PSQ in paper/shadow only.

Rules:

- Shadow-only initially.
- Exit by `15:58 ET`.
- No overnight hold.
- No pyramiding.
- No ML sizing.
- No trading on missing benchmark bars.

Promotion gate:

- At least 30 observed sessions.
- At least 100 shadow candidates, or an explicitly documented statistical sufficiency exception.
- Positive net alpha over same-ETF late-day passive hold.
- Positive alpha over delayed `1/5/10` bar entries.
- Positive alpha over random same-time entries.
- No single session contributes more than 25% of PnL.
- Profit factor at least 1.20 after spread/slippage.

### Priority 2 - Stocks-In-Play ORB v2

ORB remains a credible research family, but the current implementation failed local offline evidence. ORB v2 must not reuse the current Phase 3 ORB evidence for promotion.

Stocks-in-play score:

- 25% gap percent score.
- 25% first 5-minute or 15-minute RVOL score.
- 15% dollar-volume score.
- 10% premarket-range score.
- 10% opening-range expansion score.
- 5% sector-shock score.
- 5% spread/liquidity score.
- 5% earnings/news proxy when reliable.

Rules:

- Shadow-only initially.
- Require price, liquidity, spread, RVOL, ATR, VWAP, volume confirmation, and non-hostile sector/index state.
- Short/inverse side stays paper/shadow until controlled short logic is proven.

Promotion gate:

- Collect clean forward shadow events for 5-10+ sessions minimum.
- Replay only after positive after-cost alpha versus same-symbol hold, delayed-entry nulls, random same-time nulls, and simple ORB baseline.

### Priority 3 - Residualized Mean Reversion / Sector-Neutral Stat Arb

This is the hedge-fund-style medium-term lane. It must not be generic dip-buying.

Model:

```text
stock_return_1m ~ beta_spy * SPY + beta_qqq * QQQ + beta_sector * sector_ETF
residual = stock_return - fitted_return
residual_z = zscore(residual over rolling window)
```

Rules:

- Active only in chop, low-volatility, or liquidity-reversion regimes.
- No live trading until residual MR beats raw MR.
- No live trading unless beta, sector, and hedge accounting work.
- If long-only, buy residual laggards only when market/sector are not bearish.
- If hedged, simulate long residual laggard plus ETF/sector hedge in paper.

### Priority 4 - EOD Single-Name Reversal

Experimental shadow lane only.

Rules:

- `15:25-15:50 ET` only.
- Individual stocks only.
- Rank by intraday loser/winner pressure.
- Buy extreme losers only if reversal confirmation appears.
- Short side is paper-only.
- EOD flatten.

### Priority 5 - Order-Flow Imbalance / Microstructure ML

High-upside future lane, but it must not be faked from 1-minute OHLCV.

For now, add schema only:

- `bid_price_1`
- `ask_price_1`
- `bid_size_1`
- `ask_size_1`
- `spread_bps`
- `order_flow_imbalance`
- `trade_imbalance`
- `aggressive_buy_ratio`
- `aggressive_sell_ratio`
- `quote_update_rate`
- `depth_imbalance`

No strategy activation until reliable quote, Level 2, or order-book data exists.

## Promotion State Machine

| Tier | Name | Meaning |
| --- | --- | --- |
| 0 | Shadow only | Candidate logging, no orders. |
| 1 | Replay eligible | Historical/cached replay after costs and null comparisons. |
| 2 | Micro paper | Tiny capped notional, no pyramiding. |
| 3 | Normal paper | Strategy-specific risk budget. |
| 4 | Real-capital eligible | Only after live-paper evidence, benchmark alpha, drawdown control, and operational audit. |

Minimum promotion requirements for every `strategy_id`:

- Net profit factor at least 1.20 after costs.
- Positive average R.
- Positive alpha over same-symbol or same-ETF passive hold.
- Positive alpha over random same-time null.
- Positive alpha over delayed `1/5/10` bar nulls.
- No single symbol contributes more than 25-30% of total PnL.
- No single day/session contributes more than 20-25% of total PnL.
- Slippage and spread assumptions included.
- Number of tried variants logged.

## Benchmark And Null Stack

Every trade and every shadow candidate should be compared against:

1. Same-symbol passive hold over the exact trade window.
2. SPY, QQQ, and IWM same-window return.
3. Relevant sector ETF same-window return.
4. Random same-symbol/same-time/same-hold-duration entry.
5. Delayed entry: +1 bar, +5 bars, +10 bars.
6. Simple baseline version of the same strategy.
7. Side-flip/null direction where applicable.
8. Cost-adjusted version with realistic spread/slippage.

## Execution Phases

### Phase 9A - Evidence Foundation

Objective: no live behavior change. Build the contract and reporting layer needed to stop fooling ourselves.

Deliverables:

- `CandidateSignal` schema.
- `StrategyEngine` protocol.
- `StrategyGovernor`.
- `strategy_id` acceptance checks.
- Benchmark report helpers.
- Null-model helpers.
- Daily strategy league table.
- Tests for schema, governor, benchmarks, nulls, and league verdicts.

Acceptance:

- `strategy_id` exists before ranking/sizing in new strategy-engine contracts.
- Unknown strategy IDs block live authorization.
- Legacy history can still load.
- Runtime live behavior unchanged.

### Phase 9B - Shadow Strategy Engines

Objective: add new engines as shadow-only research surfaces.

Build order:

1. `etf_intraday_momentum`
2. `gamma_vol_proxy`
3. `stocks_in_play`
4. `orb_sip_v2`
5. `residual_mean_reversion`
6. `eod_reversal_shadow`
7. `microstructure_schema`

All new engines default to:

- `*_LIVE_ENABLED=false`
- `*_SHADOW_ONLY=true`

### Phase 9C - Replay And Micro-Paper Promotion

Objective: promote only specific strategy IDs that beat benchmarks and nulls.

Priority:

1. ETF/index intraday momentum first candidate for micro-paper.
2. ORB v2 only after redesigned forward shadow/replay.
3. Residual MR only after hedge accounting works.
4. EOD reversal remains shadow until statistically credible.
5. OFI disabled until data upgrade.

### Phase 9D - Portfolio Construction

Objective: combine validated engines with risk budgets, beta control, correlation controls, and exposure scaling.

No portfolio scaling until more than one strategy family proves after-cost alpha.

## What Not To Build

1. More tuning of the blended composite as the master strategy.
2. Live promotion of current ORB from the negative Phase 3 sample.
3. Re-enabling ML confidence as direction/ranking/sizing.
4. Generic mean reversion without residual/sector adjustment.
5. Inverse ETFs as overnight alpha.
6. Pyramiding unproven strategies.
7. Increasing max notional before strategy-level alpha is proven.

## Current Execution Position

We begin with Phase 9A. That is the right first move because the platform cannot make clean strategy decisions until attribution, benchmarks, nulls, and promotion verdicts are first-class.
