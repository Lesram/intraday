# Baseline Audit Context

Generated: 2026-03-08
SHA: `d2b22a36`

This document describes each major module and its role in the trading pipeline, written for auditors who need to understand the system without reading every file.

---

## Trading Pipeline Overview

```
Market Data → Features → Regime → Signals → Entry Gates → Sizing → Execution → Exits → Evolution
     1           2         3         4           5           6         7          8         9
```

The organism processes 1-minute bars during market hours. Each tick runs through stages 1-8 synchronously. Stage 9 (evolution) runs asynchronously after trade completion.

---

## Stage 1: Data Ingestion

### `streaming_data_provider.py` (336 lines)
Maintains WebSocket connection to Alpaca, storing incoming 1-minute OHLCV bars in per-symbol ring buffers. The engine reads from these buffers on each tick. If the WebSocket drops, it reconnects with exponential backoff.

### `backend/data/alpaca_client.py` (925 lines)
REST wrapper for Alpaca's historical data and account endpoints. Used for initial bar loading on startup and for fetching account equity/positions for reconciliation.

### `backend/integrations/alpaca_market_data_stream.py` (713 lines)
Lower-level WebSocket protocol handler for Alpaca's market data feed. Handles authentication, subscription management, and message parsing for bars, quotes, and trades.

---

## Stage 2: Feature Computation

### `ml_features.py` (457 lines)
Computes 70+ features per symbol per bar: RSI, MACD, Bollinger width, ATR, ADX, volume ratios, momentum scores, and cross-symbol relative strength. All features are computed without lookahead bias — only uses data available at computation time.

### `composite_indicators.py` (534 lines)
Seven higher-order indicators that fuse multiple base indicators into single normalized scores: squeeze momentum, volume-price divergence, trend alignment, institutional accumulation, mean reversion extremity, breakout readiness, and momentum quality.

### `multi_timeframe.py` (172 lines)
Resamples 1-minute bars to weekly and monthly timeframes, then computes RSI and trend features at those scales. These longer-horizon signals feed into the ensemble.

---

## Stage 3: Regime Detection

### `regime.py` (666 lines)
Classifies the current market state into one of six regimes: `trending_up`, `trending_down`, `chop`, `high_vol`, `low_vol`, `stress`. Uses a multi-model approach (volatility-based + trend-based + volume-based detectors). Each regime maps to different parameter sets for sizing, exits, and confidence thresholds. Also contains a `DriftDetector` that flags when the regime classifier's input distribution shifts.

---

## Stage 4: Signal Generation

### `ml_signal.py` (619 lines)
XGBoost ensemble predicting next-bar return direction (+1/-1) and magnitude. Outputs an `MLSignal` with `direction`, `confidence`, and `predicted_return`. In learning mode (< 200 trades), ML weight is set to 0% — the signal is computed but not used for decisions.

### `alpha_scanner.py` (396 lines)
Scores every symbol in the universe by combining ML prediction, breakout strength, volume profile, and regime alignment into a single `composite_score`. Returns the top-N candidates (N=5) sorted by score. Includes a stocks-in-play overlay that boosts symbols with high relative volume and gap.

### `breakout_scanner.py` (477 lines)
Detects six breakout patterns: Bollinger squeeze release, volume surge, range contraction, relative strength new high, pivot level break, and order flow imbalance. Each pattern produces a 0-1 score; they're combined into a single `composite_score`.

### `market_scanner.py` (475 lines)
Queries Alpaca's most-actives and top-movers endpoints to discover high-tension symbols outside the static universe. Used for market awareness but not currently for entry decisions.

---

## Stage 5: Entry Gating

### `live_engine.py` (4,080 lines) — the core
The largest and most critical module. Implements the full tick loop: data refresh → regime update → signal generation → entry gating → sizing → order submission → exit management → telemetry. Contains 13 sequential entry gates that every candidate must pass:

1. **Open position check** — no duplicate positions
2. **Exit cooldown** — wait after closing before re-entry
3. **Pending entry** — no duplicate pending orders
4. **Entry metadata** — no stale entry attempts
5. **Direction gate** — LONG_ONLY in learning mode
6. **Sector gate** — max 2 positions per GICS sector
7. **Fitness gate** — symbol fitness >= 0.45 (production only, 10+ trades)
8. **Liquidity gate** — minimum dollar volume
9. **Circuit breaker** — symbol not banned after repeated losses
10. **Missingness gate** — sufficient feature data available
11. **Confidence gate** — 0.40 baseline / 0.45 in chop/high_vol/trending_down
12. **Bar boundary gate** — entries only on 1-minute bar boundaries
13. **Burst cap** — maximum entries per tick

Also handles the pure breakout path (non-alpha candidates with composite_score >= 0.55) with shared safety gates.

### `sector_map.py` (96 lines)
Static mapping of the 22-symbol universe to GICS sectors. Enforces max 2 positions per sector for diversification.

### `governance.py` (250 lines)
Central control: drawdown kill switch (default 5%, .env override 20%), trading halt/resume, freeze controls. When drawdown exceeds the limit, all new entries are blocked but exits remain active.

---

## Stage 6: Position Sizing

### `kelly_sizer.py` (601 lines)
Two sizing modes:
- **Learning mode** (< 200 trades): Fixed ATR-dollar risk. `size = equity * 0.001 / stop_distance`. Kelly is OFF.
- **Production mode** (200+ trades): Kelly fraction with confidence scaling, regime adjustment, and risk-budget floor (0.25% equity per trade).

Includes dynamic leverage capping and maximum position size limits.

---

## Stage 7: Order Execution

### `backend/integrations/alpaca_broker.py` (881 lines)
Submits orders to Alpaca's paper trading API. Handles market, limit, and stop orders. Includes retry logic for transient failures and order status polling.

### `backend/services/order_service.py` (1,714 lines)
Full order lifecycle management: creation, validation, submission, fill processing, cancellation. Integrates with guardrails for pre-trade validation.

### `backend/integrations/alpaca_stream.py` (733 lines)
WebSocket stream for trade updates: fills, partial fills, cancellations, rejections. Updates internal position state in real-time.

---

## Stage 8: Exit Management

### `adaptive_exits.py` (706 lines)
Regime-conditioned exit engine:
- **ATR trailing stops** with regime-specific multipliers (trending_up=3.5x, chop=2.5x, etc.)
- **Partial take-profit** at configurable R-multiples (disabled in learning mode)
- **Horizon timeout** — hard exit at 18 bars in learning mode
- **EOD flatten** — block entries at 15:45, force close at 15:58

### `pyramider.py` (267 lines)
Adds to winning positions at 1.5R and 3.0R continuation levels. Checks that the trend still supports the position before adding.

---

## Stage 9: Learning & Evolution

### `self_evolution.py` (1,253 lines)
The meta-learning engine. After each trade closes, it updates:
- Symbol fitness scores (trade-count-based decay)
- Regime-specific parameter weights
- Feature importance rankings
- Confidence calibration curves

**Evolution is frozen for the first 300 trades.** Only ML retraining runs during this period.

### `continuous_learner.py` (401 lines)
Orchestrates the learning loop: record trade → compute attribution → update fitness → evaluate model → retrain if needed → gate promotion.

### `background_trainer.py` (412 lines)
Runs ML retraining in a separate process so the hot tick path is never blocked. Communicates results back via shared state.

### `transfer_learning.py` (581 lines)
Preserves knowledge across brain resets using distillation: extracts regime-conditioned trade statistics and feature importance from the old brain, then warm-starts the new brain.

### `walk_forward.py` (459 lines)
Validates candidate model/parameter updates using chronological out-of-sample testing before allowing promotion to production.

---

## Persistence & Telemetry

### `brain_persistence.py` (1,251 lines)
Saves the organism's learned state (evolved parameters, ML models, trade history) to disk with atomic writes, versioning, and automatic backups. Loads on startup for cross-session continuity.

### `decision_telemetry.py` (464 lines)
Captures every indicator value, gate decision, and threshold comparison for each tick. Powers the decision transparency dashboard.

### `attribution.py` (421 lines)
Reconstructs per-symbol P&L from order fills. Used by the evolution engine to score symbol fitness and by the dashboard for performance reporting.

---

## Supporting Infrastructure

### `backend/infra/schemas.py` (1,444 lines)
Core SQLAlchemy ORM models for all entities: users, orders, positions, trades, strategies, signals, audit logs, watchlists, chart drawings.

### `backend/infra/security.py` (859 lines)
JWT authentication, password hashing, user session management.

### `backend/infra/guardrails.py` (545 lines)
Pre-execution validation: order size limits, position concentration checks, market hours enforcement. Separate from the organism's internal gates.

### `backend/risk/risk_manager.py` (1,832 lines)
Institutional-grade risk manager with Kelly-based sizing, VaR/CVaR limits, correlation controls, and portfolio-level exposure caps. Operates independently of the organism's internal risk management.

---

## Non-Organism Trading Services

### `backend/services/backtest_service.py` (2,775 lines)
Full backtesting engine simulating trading days with realistic fills, slippage, and commission modeling.

### `backend/strategies/` (9 files, ~4,900 lines)
Strategy definitions and execution engine. Includes basic single-indicator strategies, advanced multi-signal strategies, and the living policy adaptation framework.

### `backend/analytics/` (3 files, ~1,800 lines)
Order flow analysis (microstructure alpha signals) and real-time portfolio risk analytics.

---

## Key Audit Considerations

1. **`live_engine.py` is the single point of control** — all trading decisions flow through it. Any bug here affects every trade.

2. **Learning vs production mode** is the critical behavioral split. Learning mode (< 200 trades) uses simplified sizing, no Kelly, no partial TP, and ML weight 0%.

3. **Evolution freeze (300 trades)** prevents parameter adaptation from corrupting the learning signal during early operation.

4. **Three layers of risk control**: organism gates (live_engine), governance (drawdown kill), and institutional risk manager (backend/risk). They operate independently.

5. **The confidence formula changes between modes**: learning uses 0.65*breakout + 0.35*tension; production uses 0.50*ml + 0.30*breakout + 0.20*tension.

6. **Inverse ETFs** (SH, PSQ, DOG, RWM) have flipped regime alignment — trending_down is bullish for inverse ETFs.

7. **The replay simulator** feeds historical bars through the exact same `live_tick()` pipeline, making it the primary regression test for trading logic.
