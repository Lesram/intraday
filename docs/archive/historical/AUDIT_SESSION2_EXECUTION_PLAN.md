# Audit Session 2 — Execution Plan

**Date:** 2026-02-08  
**Scope:** Deep platform-wide audit, trading improvements, architecture hardening  
**Total New Findings:** ~100 across strategies, infrastructure, frontend, architecture

---

## Execution Order (by impact)

### WAVE 1 — CRITICAL Strategy & Engine Bugs

| ID | Issue | File | Impact |
|----|-------|------|--------|
| W1-01 | `StrategyManager.generate_combined_signal` returns BUY when all strategies say HOLD (dict ordering bug) | `trading_strategies.py` | Phantom BUY signals |
| W1-02 | `MomentumStrategy` target price is scale-dependent (not normalized by price) | `trading_strategies.py` | Wrong TP on all stocks |
| W1-03 | `AdaptiveRegimeMomentumStrategy` dead ternary — STRONG_BUY branch identical to BUY | `advanced_strategies.py` | Missing signal granularity |
| W1-04 | `engine.py` discarded `.get()` return value — no-op line | `engine.py` | Dead code / potential bug |
| W1-05 | `StatArb` — exit_threshold never used, no close signal | `trading_strategies.py` | Positions overshoot mean |
| W1-06 | `BreakoutStrategy` — No stop_loss/take_profit set | `trading_strategies.py` | Unlimited downside |
| W1-07 | `BreakoutStrategy` — Short selling disabled, misses bearish breakouts | `trading_strategies.py` | Missing opportunities |
| W1-08 | `MomentumStrategy` — stop/TP set incorrectly for HOLD signals | `trading_strategies.py` | Bad metadata |

### WAVE 2 — Trading Improvements & New Features

| ID | Issue | File | Impact |
|----|-------|------|--------|
| W2-01 | Build Bollinger-Keltner Squeeze breakout detector | `indicators.py` NEW | High-win-rate setup |
| W2-02 | Build failed-breakout reversal detector | `advanced_strategies.py` | Captures reversals |
| W2-03 | Add multi-timeframe breakout confirmation | `advanced_strategies.py` | Reduces false breakouts |
| W2-04 | Add adaptive exit logic to StatArb | `trading_strategies.py` | Proper mean-reversion exits |
| W2-05 | Fix composite score scale mismatch in OrderFlowImbalance | `advanced_strategies.py` | Better signal components |
| W2-06 | Fix MicrostructureAlpha missing 2/4 divergence cases | `advanced_strategies.py` | Complete signal coverage |
| W2-07 | Normalize VWAP to reset daily | `indicators.py` | Correct VWAP indicator |
| W2-08 | Fix ADX smoothing (Wilder's alpha) | `indicators.py` | Correct ADX values |
| W2-09 | Fix Aroon off-by-one | `indicators.py` | Correct Aroon range |
| W2-10 | Fix MFI zero-division | `indicators.py` | NaN prevention |
| W2-11 | Fix feature_engineering RSI to match indicators RSI | `feature_engineering.py` | Consistent features |
| W2-12 | Un-stub skewness/kurtosis features | `feature_engineering.py` | ML feature quality |

### WAVE 3 — Architecture & Infrastructure

| ID | Issue | File | Impact |
|----|-------|------|--------|
| W3-01 | Remove dead `register_routes()` function | `factory.py` | Clean code |
| W3-02 | Remove legacy auth routes (past sunset date) | `factory.py` | Security |
| W3-03 | Remove 400-line test stubs from database.py | `database.py` | Clean production code |
| W3-04 | Fix Redis port binding (bind to 127.0.0.1) | `docker-compose.yml` | Security |
| W3-05 | Add GZip middleware | `factory.py` | Performance |
| W3-06 | Fix WebSocket broadcast_to_all backpressure | `websocket.py` | Stability |

### WAVE 4 — Frontend Improvements

| ID | Issue | File | Impact |
|----|-------|------|--------|
| W4-01 | Fix hardcoded notification badge count | `AppHeader.tsx` | UX |
| W4-02 | Add role-based sidebar filtering | `AppSidebar.tsx` | Security/UX |
| W4-03 | Fix PortfolioPage type consistency | `PortfolioPage.tsx` | Data display |
| W4-04 | Fix StrategyMonitorPage error swallowing | `StrategyMonitorPage.tsx` | Error visibility |

---

## Verification

After all waves:
- Run `pytest tests/ -q --tb=line -m "unit or api or services" --timeout=60`
- Expect: 506+ passed, 0 failed
- All organism tests: 37/37
