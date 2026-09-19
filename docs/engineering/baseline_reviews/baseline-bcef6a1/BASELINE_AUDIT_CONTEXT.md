# Baseline Audit Context

Generated: 2026-03-14 (Weekend Audit Baseline)
SHA: `bcef6a1`
Branch: `main`

This document describes each major module and its role in the trading pipeline, written for auditors who need to understand the system without reading every file.

---

## Platform State

| Property | Value |
|----------|-------|
| SHA | `bcef6a1` (parent: `8db0fab`) |
| Branch | `main` |
| Mode | Paper trading, development environment |
| Timeframe | 1Min (from container env `ORGANISM_LIVE_TIMEFRAME`) |
| Learning mode | Active (158 trades < 200 threshold) |
| Universe | 22 symbols (container env aligned to code default) |
| Alpha top_n | 5 |
| Max positions | 8 (container env aligned to code default) |
| Brain | Gen 0, 66 runs, 158 trades, PnL -$1,008.77 |
| ML | Not trained; 23 training attempts all rejected; learning-mode weights: 0.65 breakout + 0.35 tension + 0.0 ML |
| Evolution | Frozen (158 < 300 trade threshold) |
| Exploration | Fully removed (no execution path exists) |
| Docker | 3 containers (api, postgres, redis) via `docker-compose.paper.yml` |
| Drawdown kill | 20% (`ORGANISM_DRAWDOWN_KILL_PCT`) |
| Equity | $111,612.21 |
| Paper days | ~14 trading days |
| Last 3 days | Zero trades (3/11, 3/12, 3/13) — structural confidence gap |

---

## Changes Since Last Baseline (7a8fa1a → bcef6a1)

| Change | Detail |
|--------|--------|
| Config alignment | MAX_POSITIONS 15→8, universe 30→22 (resolved in 8db0fab) |
| Trade count | 142→158 (+16 trades, all in-memory from post-C2-patch runtime) |
| Brain runs | 35→66 |
| Brain PnL | -$944.74 → -$1,008.77 |
| Brain save | Last persisted 2026-03-13T19:39:46 (was 2026-03-11T21:13:37) |
| Audit artifacts | 50+ audit files committed (daily reports, forensics, post-close audits) |
| No code changes | Zero lines of trading logic changed since 7a8fa1a |

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

### `regime.py` (680 lines)
Classifies market state into six regimes: `trending_up`, `trending_down`, `chop`, `high_vol`, `low_vol`, `stress`. Multi-model approach (volatility + trend + volume). Each regime maps to different parameter sets for sizing, exits, and confidence thresholds. Contains `DriftDetector` for distribution shift detection.

**Known issue (INV-003)**: SMA(200) + EMA smoothing (alpha=0.3) creates 15-20 bar regime detection lag. Cross-session state persists without reset. Under investigation.

---

## Stage 4: Signal Generation

### `ml_signal.py` (619 lines)
XGBoost ensemble predicting next-bar direction and magnitude. Outputs `MLSignal` with direction, confidence, predicted_return. **In learning mode: ML weight = 0%** — signal computed but not used.

### `alpha_scanner.py` (396 lines)
Scores every universe symbol by combining ML prediction, breakout strength, volume profile, and regime alignment into a composite score. Returns top-N (N=5) candidates. Contains inverse ETF definitions (DOG, PSQ, RWM, SH) with flipped regime alignment. In learning mode: ML weight redistributed to breakout (0.40) + momentum (0.20).

**Known issue (INV-008)**: Confidence formula `0.65*breakout + 0.35*tension` structurally cannot score inverse ETFs or defensive rotations above ~0.20, because these don't exhibit breakout patterns. This is the root cause of the 3-day zero-trade streak during the 3/11-3/13 sell-off.

### `breakout_scanner.py` (477 lines)
Six breakout patterns: Bollinger squeeze release, volume surge, range contraction, relative strength new high, pivot level break, order flow imbalance. Combined into a single composite_score (0-1).

### `market_scanner.py` (475 lines)
Queries Alpaca most-actives and top-movers for discovery. Market awareness only — not used for entry decisions.

---

## Stage 5: Entry Gating

### `live_engine.py` (4,139 lines)
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
11. **Confidence gate** — 0.25 floor, 0.40 baseline, 0.45 in defensive regimes (chop/high_vol/trending_down)
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

### `kelly_sizer.py` (643 lines)
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

### `adaptive_exits.py` (720 lines)
Regime-conditioned exits:
- **ATR trailing stops** — multipliers: trending_up=3.5, trending_down=2.5, chop=2.5, high_vol=4.0, low_vol=3.0, stress=2.5, unknown=3.0
- **Partial take-profit** — at 3R (sell 30%, ride 70%). **Disabled in learning mode** to avoid clipping small winners
- **Horizon timeout** — hard exit at 18 bars (learning mode)
- **EOD flatten** — block entries at 15:45, force close at 15:58

### `pyramider.py` (267 lines)
Adds to winning positions at 1.5R and 3.0R continuation levels. Trend validation before adding.

---

## Stage 9: Learning & Evolution

### `self_evolution.py` (1,247 lines)
Meta-learning engine. After each trade: updates symbol fitness (trade-count decay), regime-specific parameter weights, feature importance, confidence calibration. **Frozen for first 300 trades.** Current: 158 trades, frozen.

### `continuous_learner.py` (529 lines)
Orchestrates: record trade -> compute attribution -> update fitness -> evaluate model -> retrain if needed -> gate promotion.

### `background_trainer.py` (412 lines)
ML retraining in separate process. Non-blocking to hot tick path.

### `transfer_learning.py` (581 lines)
Cross-reset knowledge distillation. Warm-start gated by 300-trade freeze.

### `walk_forward.py` (459 lines)
Chronological out-of-sample validation before parameter promotion.

---

## Persistence & Telemetry

### `brain_persistence.py` (1,341 lines)
Saves organism state (evolved params, ML models, trade history) with atomic writes, versioning, automatic backups. Loads on startup for cross-session continuity. All 8 forensic fields (entry_source, regime_at_entry/exit, mfe, mae, bars_held, time_in_trade, closed_at) wired since C2 patch (2026-03-09).

### `decision_telemetry.py` (464 lines)
Captures every indicator value, gate decision, and threshold comparison per tick.

### `attribution.py` (421 lines)
Per-symbol P&L reconstruction from order fills. Feeds evolution and dashboard.

---

## Key Audit Considerations

1. **`live_engine.py` is the single point of control** — all trading decisions flow through it. Any bug here affects every trade.

2. **Learning vs production mode** is the critical behavioral split. Learning mode (< 200 trades): simplified sizing, no Kelly, no partial TP, ML weight 0%.

3. **Evolution freeze (300 trades)** prevents parameter adaptation from corrupting learning signal. Currently active (158 trades).

4. **Three layers of risk control**: organism gates (live_engine), governance (drawdown kill 20%), institutional risk manager (backend/risk). Operate independently.

5. **Confidence formula changes between modes**: learning = 0.65*breakout + 0.35*tension; production = 0.50*ml + 0.30*breakout + 0.20*tension.

6. **Inverse ETFs** (DOG, PSQ, RWM, SH) have flipped regime alignment — trending_down is bullish for inverse ETFs. But the flip only affects the 5% alpha weight for regime_alignment, NOT the confidence formula. This is why inverse ETFs always score near 0.

7. **Replay simulator** feeds historical bars through the same `live_tick()` pipeline — primary regression test for trading logic.

8. **Exploration fully removed** — no execution path exists (improve9/H1).

9. **Universe: 22 symbols** (code default, container env aligned). Includes SH, PSQ inverse ETFs.

10. **Max positions = 8** (aligned to code default). Alpha top_n = 5.

11. **Brain is early-stage**: gen 0, 66 runs, 158 trades, PnL -$1,008.77. ML not trained. All learning-mode safeguards active.

12. **3-day zero-trade streak (3/11-3/13)**: Structural confidence gap. Scanner correctly detects candidates but confidence formula cannot score rotation/sell-off patterns above the 0.25 floor gate. Known limitation (INV-008), not a bug.

13. **Forensic fields**: Fully wired in code but NOT yet validated live — no trade has opened+closed since C2 patch due to 3-day zero-trade streak.
