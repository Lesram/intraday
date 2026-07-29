# Baseline Audit Context

Generated: 2026-03-09
SHA: `7a8fa1a`
Branch: `main`

This document describes each major module and its role in the trading pipeline, written for auditors who need to understand the system without reading every file.

---

## Platform State

| Property | Value |
|----------|-------|
| SHA | `7a8fa1a` |
| Branch | `main` |
| Mode | Paper trading, development environment |
| Timeframe | 1Min (from container env `ORGANISM_LIVE_TIMEFRAME`) |
| Learning mode | Active (142 trades < 200 threshold) |
| Universe | 30 symbols (`.env` override), code default 22 |
| Alpha top_n | 5 |
| Max positions | 15 (`.env` override), code default 8 |
| Brain | Gen 0, 35 runs, 142 trades, PnL -$944.74 |
| ML | Not trained; learning-mode weights: 0.65 breakout + 0.35 tension + 0.0 ML |
| Evolution | Frozen (142 < 300 trade threshold) |
| Exploration | Fully removed (no execution path exists) |
| Docker | 3 containers (api, postgres, redis) via `docker-compose.paper.yml` |
| Drawdown kill | 20% (`.env` override of 5% default) |

---

## Trading Pipeline

```
Market Data -> Features -> Regime -> Signals -> Entry Gates -> Sizing -> Execution -> Exits -> Evolution
     1           2          3          4           5            6          7           8          9
```

The organism processes 1-minute bars during market hours (9:30-16:00 ET). Each tick runs stages 1-8 synchronously. Stage 9 runs asynchronously after trade completion.

---

## Stage 1: Data Ingestion

### `streaming_data_provider.py` (336 lines)
WebSocket connection to Alpaca storing incoming 1-minute OHLCV bars in per-symbol ring buffers. Reconnects with exponential backoff on disconnect.

### `alpaca_client.py` (925 lines)
REST wrapper for Alpaca historical data and account endpoints. Used for initial bar loading on startup and equity/positions reconciliation.

### `alpaca_market_data_stream.py` (713 lines)
Lower-level WebSocket protocol handler. Handles authentication, subscription management, and message parsing for bars, quotes, and trades.

---

## Stage 2: Feature Computation

### `ml_features.py` (457 lines)
Computes 70+ features per symbol per bar: RSI, MACD, Bollinger width, ATR, ADX, volume ratios, momentum scores, cross-symbol relative strength. No lookahead bias.

### `composite_indicators.py` (534 lines)
Seven higher-order indicators fusing multiple base indicators: squeeze momentum, volume-price divergence, trend alignment, institutional accumulation, mean reversion extremity, breakout readiness, momentum quality.

### `multi_timeframe.py` (172 lines)
Resamples 1-minute bars to weekly/monthly, computes RSI and trend features at longer horizons.

---

## Stage 3: Regime Detection

### `regime.py` (666 lines)
Classifies market state into six regimes: `trending_up`, `trending_down`, `chop`, `high_vol`, `low_vol`, `stress`. Multi-model approach (volatility + trend + volume). Each regime maps to different parameter sets for sizing, exits, and confidence thresholds. Contains `DriftDetector` for distribution shift detection.

---

## Stage 4: Signal Generation

### `ml_signal.py` (619 lines)
XGBoost ensemble predicting next-bar direction and magnitude. Outputs `MLSignal` with direction, confidence, predicted_return. **In learning mode: ML weight = 0%** — signal computed but not used.

### `alpha_scanner.py` (396 lines)
Scores every universe symbol by combining ML prediction, breakout strength, volume profile, and regime alignment into a composite score. Returns top-N (N=5) candidates. Contains inverse ETF definitions (DOG, PSQ, RWM, SH) with flipped regime alignment. In learning mode: ML weight redistributed to breakout (0.40) + momentum (0.20).

### `breakout_scanner.py` (477 lines)
Six breakout patterns: Bollinger squeeze release, volume surge, range contraction, relative strength new high, pivot level break, order flow imbalance. Combined into a single composite_score (0-1).

### `market_scanner.py` (475 lines)
Queries Alpaca most-actives and top-movers for discovery. Market awareness only — not used for entry decisions.

---

## Stage 5: Entry Gating

### `live_engine.py` (4,080 lines)
The core module. Implements the full tick loop and 13 sequential entry gates:

1. **Open position check** — no duplicate positions
2. **Exit cooldown** — wait after closing before re-entry
3. **Pending entry** — no duplicate pending orders
4. **Entry metadata** — no stale entry attempts
5. **Direction gate** — LONG_ONLY in learning mode
6. **Sector gate** — max 2 per GICS sector
7. **Fitness gate** — >= 0.45 with 10+ trades (production only; **OFF in learning**)
8. **Liquidity gate** — minimum dollar volume
9. **Circuit breaker** — symbol banned after repeated losses
10. **Missingness gate** — sufficient feature data
11. **Confidence gate** — 0.40 baseline, 0.45 in defensive regimes (chop/high_vol/trending_down)
12. **Bar boundary gate** — entries only on 1-minute bar boundaries
13. **Burst cap** — max entries per tick (learning: 12/hr)

Pure breakout path (non-alpha candidates, composite_score >= 0.55) shares liquidity gate + confidence threshold with alpha path.

**Current state**: Learning mode. Fitness gate OFF. ML weight 0%. Entry throttle 12/hr.

### `sector_map.py` (96 lines)
Static GICS sector mapping. Enforces max 2 positions per sector.

### `governance.py` (250 lines)
Kill switches: drawdown kill (20%), trading halt/resume, freeze controls. Drawdown blocks entries but exits remain active.

---

## Stage 6: Position Sizing

### `kelly_sizer.py` (601 lines)
Two modes:
- **Learning** (< 200 trades): Fixed ATR-dollar risk. `size = equity * 0.001 / stop_distance`. Kelly OFF. Dollar-risk cap 0.10% equity + notional cap 5%.
- **Production** (200+ trades): Kelly fraction with confidence scaling [0.3-1.5], regime adjustment, breakout bonus [1.0-2.0], risk-budget floor 0.25% equity.

**Current state**: Learning mode. Kelly OFF. Risk budget 0.1% equity.

---

## Stage 7: Order Execution

### `alpaca_broker.py` (881 lines)
Submits orders to Alpaca paper trading API. Market, limit, stop orders. Retry logic and order status polling.

### `order_service.py` (1,714 lines)
Full order lifecycle: creation, validation, submission, fill processing, cancellation. Integrates with guardrails.

### `alpaca_stream.py` (733 lines)
WebSocket for trade updates: fills, partial fills, cancellations, rejections. Real-time position state updates.

---

## Stage 8: Exit Management

### `adaptive_exits.py` (706 lines)
Regime-conditioned exits:
- **ATR trailing stops** — multipliers: trending_up=3.5, trending_down=2.5, chop=2.5, high_vol=4.0, low_vol=3.0, stress=2.5, unknown=3.0
- **Partial take-profit** — at 3R (sell 30%, ride 70%). **Disabled in learning mode** to avoid clipping small winners
- **Horizon timeout** — hard exit at 18 bars (learning mode)
- **EOD flatten** — block entries at 15:45, force close at 15:58

### `pyramider.py` (267 lines)
Adds to winning positions at 1.5R and 3.0R continuation levels. Trend validation before adding.

---

## Stage 9: Learning & Evolution

### `self_evolution.py` (1,253 lines)
Meta-learning engine. After each trade: updates symbol fitness (trade-count decay), regime-specific parameter weights, feature importance, confidence calibration. **Frozen for first 300 trades.** Current: 142 trades, frozen.

### `continuous_learner.py` (401 lines)
Orchestrates: record trade -> compute attribution -> update fitness -> evaluate model -> retrain if needed -> gate promotion.

### `background_trainer.py` (412 lines)
ML retraining in separate process. Non-blocking to hot tick path.

### `transfer_learning.py` (581 lines)
Cross-reset knowledge distillation. Warm-start gated by 300-trade freeze.

### `walk_forward.py` (459 lines)
Chronological out-of-sample validation before parameter promotion.

---

## Persistence & Telemetry

### `brain_persistence.py` (1,251 lines)
Saves organism state (evolved params, ML models, trade history) with atomic writes, versioning, automatic backups. Loads on startup for cross-session continuity.

### `decision_telemetry.py` (464 lines)
Captures every indicator value, gate decision, and threshold comparison per tick.

### `attribution.py` (421 lines)
Per-symbol P&L reconstruction from order fills. Feeds evolution and dashboard.

---

## Supporting Infrastructure

### `guardrails.py` (545 lines)
Pre-execution validation: order size limits, position concentration, market hours. Separate from organism internal gates.

### `risk_manager.py` (1,832 lines)
Institutional-grade: Kelly sizing, VaR/CVaR limits, correlation controls, portfolio exposure caps. Independent of organism risk management.

### `base_settings.py` (1,745 lines)
Pydantic settings consuming all environment variables. Single source for config resolution.

---

## Key Audit Considerations

1. **`live_engine.py` is the single point of control** — all trading decisions flow through it. Any bug here affects every trade.

2. **Learning vs production mode** is the critical behavioral split. Learning mode (< 200 trades): simplified sizing, no Kelly, no partial TP, ML weight 0%.

3. **Evolution freeze (300 trades)** prevents parameter adaptation from corrupting learning signal. Currently active (142 trades).

4. **Three layers of risk control**: organism gates (live_engine), governance (drawdown kill 20%), institutional risk manager (backend/risk). Operate independently.

5. **Confidence formula changes between modes**: learning = 0.65*breakout + 0.35*tension; production = 0.50*ml + 0.30*breakout + 0.20*tension.

6. **Inverse ETFs** (DOG, PSQ, RWM, SH) have flipped regime alignment — trending_down is bullish for inverse ETFs.

7. **Replay simulator** feeds historical bars through the same `live_tick()` pipeline — primary regression test for trading logic.

8. **Exploration fully removed** — no execution path exists (improve9/H1).

9. **Universe: 30 symbols from `.env`** (overrides 22-symbol code default). Scanner may add/remove dynamically.

10. **Max positions = 15** (`.env`), higher than code default of 8. Alpha top_n = 5.

11. **Brain is early-stage**: gen 0, 35 runs, 142 trades, PnL -$944.74. ML not trained. All learning-mode safeguards active.
