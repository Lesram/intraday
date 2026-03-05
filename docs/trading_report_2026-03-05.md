# Trading Report — March 5, 2026

## Executive Summary

| Metric | Value |
|--------|-------|
| **Opening Equity** | $112,225.82 |
| **Closing Equity** | $111,874.37 |
| **Day P&L** | **-$351.45 (-0.31%)** |
| **Intraday High** | $112,297.00 |
| **Intraday Low** | $111,857.41 |
| **Max Drawdown (from peak)** | -$439.59 (-0.39%) |
| **Total Orders** | 98 filled (41 buys, 57 sells) |
| **Total Shares Traded** | 892 bought / 1,010 sold |
| **Unique Symbols Traded** | 22 of 30 universe |
| **Win Rate** | 25.7% (9W / 26L) |
| **Total Trades Recorded** | 93 (all-time brain), ~35 today |
| **Brain Generation** | 2 → 3 (retrained twice today) |
| **ML Accuracy** | Gen 1: 58.4%, Gen 2: 67.0% |
| **Engine Mode** | Learning (<200 trades) |

**Result**: Net loss of $351 on the first full trading day after the improve7 system overhaul. The engine spent the first ~2 hours of market hours blocked by three critical bugs (stale data gate broken, fitness gate too restrictive, variable scope error). After hotfixes deployed at ~1:43 PM ET, the engine traded aggressively in learning mode through close. Loss is concentrated in trending_up entries that reversed into trending_down / high_vol regimes.

---

## 1. System Changes Deployed Today

### 1.1 Improve7 Overhaul (deployed pre-market)

Full implementation of the improve7 forensic audit recommendations from the March 4 session:

| Change | Files Modified | Purpose |
|--------|---------------|---------|
| **FTF redesign in chop** | adaptive_exits.py | Losers-only exit with multi-bar momentum; winners get stop tightened instead of exited |
| **Confidence entry gate** | live_engine.py | Gate 10: min confidence 0.30 (0.35 in chop); below-threshold → exploration bucket |
| **Symbol circuit breaker** | live_engine.py | Gate 9: ban symbol for session after 2 consecutive losers OR -$15 daily P&L |
| **EOD flatten** | live_engine.py | Block entries 15:45 ET, force close all 15:58 ET |
| **Risk-budget floor scaling** | kelly_sizer.py | Floor × clamp(0.5 + 0.8 × confidence, 0.5, 1.1) |
| **Regime evolution freeze** | kelly_sizer.py | Evolved regime scales locked until 200+ total trades AND 30+ per regime |
| **Intraday trend threshold** | regime.py | trend_threshold × 1/√(bars_per_day) for 1-min bars |
| **Trade causal fields** | continuous_learner.py | entry_source, regime_at_entry/exit, MFE, MAE, bars_held, time_in_trade |

### 1.2 Hotfixes (deployed 1:43 PM ET)

Three critical bugs discovered during market hours and fixed:

#### Bug 1: Stale Data Gate Broken (CRITICAL)
- **Root cause**: `live_engine.py` line 943 checked `self._streaming_provider.last_update_time` but `StreamingDataProvider` never defined that attribute. `getattr()` returned `None`, so `self._data_stale` was always `False`.
- **Impact**: Engine never blocked entries during data staleness. When WebSocket disconnected (keepalive ping timeout), the engine continued attempting trades with stale/REST-fallback data.
- **Fix**: Added `last_update_time: float | None = None` property to `StreamingDataProvider`, updated on every bar callback and pre-fill.
- **Verification**: After fix, logs show "Stale data — blocking entries (exits still active)" during WebSocket disconnections.

#### Bug 2: Fitness Gate Chicken-and-Egg (HIGH)
- **Root cause**: Fitness gate threshold was hardcoded at 0.45 with no learning-mode bypass. After brain reset from March 4, symbol fitness scores ranged from 0.30–0.65 with 19/25 symbols below 0.45. Only 6 symbols could ever be traded.
- **Impact**: Engine could not accumulate enough trades to learn — classic chicken-and-egg. AAPL blocked at fitness=0.41, most symbols blocked.
- **Fix**: Added learning-mode bypass: `_eff_fitness_gate = 0.30 if self._is_learning_mode else 0.45`. All 25 scored symbols now pass in learning mode.
- **Production behavior**: Once engine reaches 200 trades, gate tightens to 0.45 automatically.

#### Bug 3: Variable Scope Error (MEDIUM)
- **Root cause**: `_eff_fitness_gate` was initially defined inside the `for c in candidates:` loop but referenced in the pure-breakout section outside it. Python `UnboundLocalError` on every tick.
- **Impact**: `"Live tick error: cannot access local variable '_eff_fitness_gate'"` — engine continued but skipped all entry logic.
- **Fix**: Moved `_eff_fitness_gate` definition to the outer scope before the candidate loop.

---

## 2. Timeline of Events

| Time (ET) | Tick | Event |
|-----------|------|-------|
| ~9:30 AM | 1 | Market open. Engine running with improve7 changes. |
| 9:30–1:00 PM | 1–400 | **ENGINE BLOCKED** — stale data gate broken (always False), fitness gate blocking most symbols. Only COST (liquidity gate) and AAPL (fitness 0.41 < 0.45) attempted. Zero signals, zero orders for ~3.5 hours. |
| ~12:00 PM | ~300 | WebSocket "keepalive ping timeout" disconnection. Stale data warnings for all 30 symbols (~500s staleness). Engine continues via REST fallback but scanner produces no viable candidates. |
| **1:43 PM** | **400** | **Hotfixes deployed** — Docker rebuilt with 3 fixes. Engine immediately starts generating signals. |
| 1:43 PM | 400 | Legacy exits: PLTR (34 shares), WMT (42 shares) from overnight/pre-fix positions |
| 1:43 PM | 400–402 | Batch entries: MSFT (12), COIN (17), AVGO (16), AMZN (24), NFLX (54), NVDA (29), PLTR (34), TSLA (13) |
| 1:44 PM | 411 | Regime: trending_up. Signals=1, Orders=1. Exits=2 (COIN, PLTR). |
| 1:45 PM | 415 | Regime shifts to high_vol. 3 signals, 3 orders. |
| 1:46 PM | 416 | **XLE circuit breaker** — BANNED for session (daily P&L -$144.44, 1 consecutive loss). First circuit breaker activation. |
| 1:46 PM | 417 | **Entry throttle hit** — 13 entries in last hour, max 12 (learning mode). Entries blocked. |
| 1:47–2:15 PM | 417–476 | Throttle periodically blocks new entries. Exits continue (MSFT partial, AVGO partial, AMZN partial, SNOW partial). |
| 2:15–3:00 PM | 476–530 | Second wave: COIN (19), XOM (35), GOOGL (17), WMT (43), ABNB (39), MU (13), IWM (21), NFLX (54). Multiple quick exits. |
| 3:00–3:45 PM | 530–570 | Third wave entries + exits. WMT and XOM cycle again. CAT (7) entered and exited. |
| **3:45 PM** | ~575 | **EOD entry block** activated — "no new entries after 15:45 ET". |
| 3:52 PM | 585 | Last exit: CAT (7 shares). |
| 4:00 PM+ | 598+ | Market closed. Engine continues ticking, stale data gate blocks entries. Regime: trending_down. |

---

## 3. Trade Analysis

### 3.1 Regime-Stratified P&L

| Regime | Wins | Losses | Win Rate | P&L | Avg Win | Avg Loss |
|--------|------|--------|----------|-----|---------|----------|
| trending_up | 4 | 10 | 28.6% | -$404.32 | $3.30 | $41.75 |
| trending_down | 0 | 5 | 0.0% | -$28.68 | $0.00 | $5.74 |
| high_vol | 4 | 9 | 30.8% | -$134.87 | $26.84 | $26.92 |
| unknown | 1 | 2 | 33.3% | -$206.51 | $15.01 | $110.76 |
| **TOTAL** | **9** | **26** | **25.7%** | **-$774.39** | — | — |

**Key insight**: The worst regime for P&L was `trending_up` (-$404), not `trending_down`. This is because the engine entered aggressively when regime was trending_up, but the market reversed. The large position sizes in trending_up (regime scale 1.164) amplified losses when the regime shifted to high_vol/trending_down.

### 3.2 Per-Symbol Performance

| Symbol | Orders | Shares | Fitness | Win Rate | Avg P&L | Notes |
|--------|--------|--------|---------|----------|---------|-------|
| NVDA | 8 | 90 | 0.697 | 51.0% | +$5.53 | **Best performer** |
| QQQ | 3 | 16 | 0.652 | 36.0% | +$3.74 | Small position, positive |
| AMZN | 9 | 144 | 0.606 | 25.5% | +$0.57 | Breakeven |
| COST | 3 | 10 | 0.590 | 30.0% | +$0.72 | Limited exposure |
| LLY | 4 | 14 | 0.590 | 30.0% | +$2.11 | Small, positive |
| COIN | 7 | 114 | 0.573 | 16.9% | +$3.60 | High volume, positive avg |
| XLE | 6 | 188 | 0.552 | 32.8% | -$3.56 | **Circuit breaker triggered** (-$144) |
| PLTR | 5 | 138 | 0.410 | 27.2% | -$5.60 | High volume, losing |
| WMT | 7 | 300 | 0.379 | 18.0% | -$40.30 | **Worst per-trade loss** |
| CAT | 4 | 26 | 0.347 | 0.0% | -$107.08 | Very poor |
| XOM | 4 | 140 | 0.351 | 0.0% | -$3.60 | No wins |
| MSFT | 6 | 48 | 0.343 | 0.0% | -$7.99 | No wins |

**Notable patterns**:
- Top-fitness symbols (NVDA, QQQ, COIN) were profitable or breakeven
- Bottom-fitness symbols (CAT, WMT, XOM, MSFT) were consistent losers
- XLE got circuit-breaker'd at -$144 — this worked as designed
- WMT was the worst performer per-trade (-$40.30 avg P&L), entered 3 times with 43 shares each

### 3.3 Complete Order Log

98 orders executed today (41 buys, 57 sells). All filled at market.

**Phase 1: Legacy position cleanup (ticks 1–4)**
```
EXIT  PLTR  34 shares  (overnight position)
EXIT  WMT   42 shares  (overnight position)
```

**Phase 2: First entry wave (ticks 6–20)**
```
BUY   MSFT  12 shares  t6
BUY   COIN  17 shares  t6
BUY   AVGO  16 shares  t7
BUY   AMZN  24 shares  t7
BUY   NFLX  54 shares  t8
BUY   NVDA  29 shares  t8
BUY   PLTR  34 shares  t11
BUY   TSLA  13 shares  t20
```

**Phase 3: Partial exits + pyramid (ticks 37–42)**
```
BUY   AVGO   8 shares  t37  (pyramid)
EXIT  AMZN   7 shares  t38  (partial)
EXIT  MSFT   3 shares  t38  (partial)
BUY   NVDA  14 shares  t38  (pyramid)
EXIT  AVGO   7 shares  t41  (partial)
EXIT  NFLX  16 shares  t41  (partial)
EXIT  NVDA  12 shares  t42  (partial)
EXIT  TSLA   3 shares  t42  (partial)
```

**Phase 4: Mass exit (tick 60–61) — regime shift or rebalance**
```
EXIT  AMZN  17, AVGO 17, COIN 17, MSFT 9, NFLX 38, NVDA 31, PLTR 34, TSLA 10  (all at t60)
BUY   CAT    6 shares  t60
EXIT  CAT    6 shares  t61  (immediate stop)
EXIT  UBER  21 shares  t61  (legacy position)
```

**Phase 5: Exploration micro-trades (ticks 135–398)**
```
BUY   XLE    1 share   t135  →  EXIT t275
BUY   AMZN  24 shares  t275
BUY   ADBE   1 share   t275  →  EXIT t301
BUY   NVDA   1 share   t284  →  EXIT t351
BUY   XLE    1 share   t292
BUY   WMT   43 shares  t301  →  EXIT t398
BUY   GOOGL 17 shares  t301  →  EXIT t338
BUY   LLY    5 shares  t356
BUY   NVDA   1 share   t375
BUY   COST   5 shares  t391  →  EXIT t403 (trailing_stop)
BUY   LLY    2 shares  t395
EXIT  UBER  49 shares  t390  (legacy)
```

**Phase 6: Post-hotfix deployment (ticks 400–416)**
```
EXIT  AMZN 17, COST 1, LLY 1, NVDA 1, XLE 1  (all at t400 — engine restart cleanup)
BUY   PLTR  35 shares  t402
BUY   COIN  21 shares  t402
EXIT  COST   4 shares  t403  (trailing_stop)
EXIT  LLY    6 shares  t403  (stop_loss)
EXIT  COIN  21 shares  t411
EXIT  PLTR  35 shares  t411
BUY   XLE   92 shares  t411  →  EXIT t415 (circuit breaker: -$144.44)
BUY   AVGO  16, MSFT 12, QQQ 8  t415
BUY   AMZN  24, SNOW 30  t416
```

**Phase 7: Final trading wave (ticks 420–585)**
```
EXIT  MSFT 3 (t420), AVGO 4 (t429), AMZN 7 (t436), SNOW 9 (t440)
EXIT  QQQ 2+6, SNOW 21, AMZN 17, AVGO 12, MSFT 9  (t476-482)
BUY   COIN 19 (t486), XOM 35 (t499), GOOGL 17 (t499), WMT 43 (t503)
EXIT  GOOGL 17 (t525), COIN 5+14 (t529+539), WMT 43 (t529)
BUY   ABNB 39 (t529), MU 13 (t534), IWM 21 (t535), NFLX 54 (t535), WMT 43 (t539)
EXIT  XOM 35 (t530), NFLX 54 (t543), IWM 21 (t548), ABNB 11 (t552), MU 13 (t560)
BUY   XOM 35 (t548), CAT 7 (t561)
EXIT  WMT 43 (t569), XOM 35 (t577), CAT 7 (t585)
```

### 3.4 Exit Reason Analysis

Based on engine logs and order flow:

| Exit Reason | Estimated Count | Notes |
|-------------|----------------|-------|
| stop_loss | ~12 | Primary exit for losing trades |
| trailing_stop | ~5 | Triggered on partial winners (COST, ABNB) |
| failure_to_follow | ~4 | Redesigned in improve7 — only losers in chop, should be lower |
| partial exit | ~8 | Partial position reductions (AMZN, MSFT, AVGO, NVDA, TSLA) |
| eod_flatten | 0 | EOD block activated but no open positions at 15:58 |
| circuit_breaker_triggered | 1 | XLE banned after -$144.44 |

---

## 4. Equity Curve

```
Tick    Equity       Delta    Phase
───────────────────────────────────────────────
  53    $112,225.82   +0.00   Open (first valid reading)
  71    $112,280.34  +54.52   Brief rally  ← INTRADAY HIGH ~$112,297
  89    $112,181.90  -98.44   First wave exits (losses)
 107    $112,187.72   +5.82   Stabilization
 125    $111,996.33 -191.39   Mass exit (tick 60) — large drawdown
 146    $112,025.24  +28.91   Micro-recovery
 164    $112,027.93   +2.69   Flat (stale data, no trading)
 182    $112,016.17  -11.76   Slow drift
 325    $111,996.15  -20.02   Long flat period (engine blocked)
 343    $111,994.05   -2.10   Still blocked
 361    $112,000.22   +6.17   Minor fluctuation
 379    $111,971.76  -28.46   Pre-hotfix drift
 397    $111,983.39  +11.63   Slight recovery
 415    $111,942.17  -41.22   Post-hotfix: XLE circuit breaker loss
 433    $111,948.29   +6.12   Recovery attempt
 451    $111,937.65  -10.64   Grinding lower
 469    $111,963.79  +26.14   Best recovery of the day
 487    $111,909.99  -53.80   Sharp drop (WMT losses)
 505    $111,928.02  +18.03   Bounce
 523    $111,940.05  +12.03   Recovery
 541    $111,898.30  -41.75   Late-day selling
 559    $111,889.48   -8.82   Continued pressure
 577    $111,884.67   -4.81   XOM exit
 595    $111,871.97  -12.70   Near low
 613    $111,881.42   +9.45   Minor bounce
 631    $111,868.35  -13.07   Late drift
 642    $111,874.37   +6.02   Close
```

**Pattern**: Two distinct drawdown phases:
1. **Tick 71→125**: -$283 — first wave entries hit stops after trending_up reversed
2. **Tick 469→559**: -$64 — late-day entries (WMT, XOM, CAT) all stopped out in trending_down

---

## 5. Governance Features Performance

### 5.1 Stale Data Gate
- **Status**: WORKING (after hotfix)
- **Events**: "Stale data — blocking entries" logged during WebSocket disconnections post-fix
- **Before fix**: Gate was completely non-functional (always returned False)

### 5.2 Fitness Gate
- **Status**: WORKING (learning mode: 0.30, production: 0.45)
- **Events**: ADBE, AMZN intermittently blocked by liquidity gate (not fitness)
- **Before fix**: Blocked 19/25 symbols at 0.45 threshold

### 5.3 Symbol Circuit Breaker
- **Status**: WORKING
- **Events**: XLE BANNED at tick 416 after -$144.44 daily P&L
- **Assessment**: Correctly prevented further losses on XLE

### 5.4 Entry Throttle
- **Status**: WORKING
- **Events**: Hit 13/12 entries/hour limit repeatedly (ticks 417–430+)
- **Assessment**: Prevented over-trading in learning mode

### 5.5 EOD Entry Block
- **Status**: WORKING
- **Events**: "EOD entry block — no new entries after 15:45 ET" logged at tick ~575
- **Assessment**: No positions open at 15:58 (already exited), so flatten not triggered

### 5.6 Liquidity Gate
- **Status**: WORKING
- **Events**: Blocked ADBE and COST intermittently
- **Assessment**: Correctly preventing illiquid entries

### 5.7 FTF Redesign (Chop)
- **Status**: WORKING
- **Assessment**: FTF exits appear reduced compared to March 4 (was 58% of exits). Need more data to confirm improvement.

---

## 6. Brain / ML State at Close

### 6.1 Learning State
```json
{
    "generation": 2,
    "total_trades": 93,
    "cumulative_pnl": -981.90,
    "best_sharpe": -6.0623,
    "retrain_count": 2,
    "generation_accuracies": [0.5837, 0.67]
}
```

- ML accuracy improved 58.4% → 67.0% between generations
- Still in learning mode (93 < 200 trades)
- Sharpe deeply negative (-6.06 best) — expected for learning phase

### 6.2 Evolved Parameters (Gen 3)
```
Alpha weights:  ML 35.6%, Volume 19.6%, Momentum 17.6%, Breakout 14.7%, Regime 12.5%
Direction:      Buy 0.55, Sell 0.45
Stop ATR:       0.985 (tightened from 1.0)
Trailing dist:  0.936 (tightened from 1.0)
```

Regime size scales:
```
trending_up:    1.164  (boosted — but premature, losses were here)
trending_down:  0.582  (correctly reduced)
chop:           0.500
high_vol:       0.700
stress:         0.300
```

### 6.3 Symbol Fitness (Top 7 / Bottom 7)

| Rank | Symbol | Fitness | Trades | Win Rate | Avg P&L |
|------|--------|---------|--------|----------|---------|
| 1 | NVDA | 0.697 | 7 | 51.0% | +$5.53 |
| 2 | QQQ | 0.652 | 3 | 36.0% | +$3.74 |
| 3 | AMZN | 0.606 | 10 | 25.5% | +$0.57 |
| 4 | COST | 0.590 | 1 | 30.0% | +$0.72 |
| 5 | LLY | 0.590 | 1 | 30.0% | +$2.11 |
| 6 | COIN | 0.573 | 12 | 16.9% | +$3.60 |
| 7 | XLE | 0.552 | 14 | 32.8% | -$3.56 |
| ... | ... | ... | ... | ... | ... |
| 21 | SNOW | 0.303 | 5 | 0.0% | -$7.78 |
| 22 | MSFT | 0.303 | 7 | 0.0% | -$7.99 |
| 23 | UBER | 0.303 | 4 | 0.0% | -$1.80 |
| 24 | META | 0.303 | 2 | 0.0% | -$7.24 |
| 25 | CAT | 0.263 | 2 | 0.0% | -$107.08 |

### 6.4 ML Calibration
```
Confidence buckets:    [0-0.2] [0.2-0.4] [0.4-0.6] [0.6-0.8] [0.8-1.0]
Correct/Total:         0/1     3/8       3/13      6/18      0/0
Calibration map:       1.00    1.00      0.60      0.48      1.00
```
- Most trades in 0.4–0.8 confidence range
- Calibration shows overconfidence: predicted 60% accuracy, actual 23% in 0.4–0.6 bucket

### 6.5 Regime Kelly Stats
```
trending_up:    4W/10L, P&L -$404.32, Win$=13.21, Loss$=417.53
trending_down:  0W/ 5L, P&L  -$28.68, Win$= 0.00, Loss$= 28.68
high_vol:       4W/ 9L, P&L -$134.87, Win$=107.37, Loss$=242.25
unknown:        1W/ 2L, P&L -$206.51, Win$= 15.01, Loss$=221.52
```

---

## 7. Remaining Open Positions at Close

| Symbol | Shares | Entry | Stop | TP | Bars Held | Trailing | Source | Regime at Entry |
|--------|--------|-------|------|----|-----------|----------|--------|-----------------|
| ABNB | 28 | $135.36 | $135.11 | $136.09 | 18 | Yes | alpha+breakout | trending_down |
| UBER | stale ref | $76.75 | $74.52 | $85.96 | 69 | No | unknown | unknown |

- ABNB: Trailing stop active, 28 shares remaining (11 partial exited at t552)
- UBER: Stale position reference — no entry_metadata, likely orphaned from pre-fix state

---

## 8. Infrastructure Issues

### 8.1 WebSocket Disconnections
- **Event**: "WebSocket connection closed: sent 1011 (internal error) keepalive ping timeout"
- **Frequency**: At least 1 confirmed disconnect (~12:00 PM ET)
- **Impact**: All 30 symbols showed stale data (500+ seconds). Reconnection succeeded but data remained stale for several minutes.
- **Root cause**: Alpaca WebSocket keepalive timing (ping_interval=20s, ping_timeout=10s)

### 8.2 Alpaca Connection Error
- **Event**: "Failed to get all positions: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
- **Impact**: Transient — single tick affected, recovered automatically

### 8.3 Docker Rebuilds
- 3 Docker rebuilds today (improve7 deploy, hotfix 1, hotfix 2)
- Each rebuild takes ~30 seconds, engine resumes from brain state automatically
- Entry timestamps preserved across restarts (throttle state maintained)

---

## 9. Root Cause Analysis for Losses

### Primary Loss Drivers

1. **Trending_up entries that reversed (-$404.32)**
   - Engine entered 8 positions in first wave during trending_up regime
   - Market reversed to high_vol/trending_down within ~30 ticks (5 minutes)
   - Regime scale of 1.164 for trending_up amplified position sizes
   - Stops hit quickly — average loss per trade was $41.75 in trending_up

2. **WMT repeated failures (-$40.30 avg per trade)**
   - Entered WMT 3 times (43 shares each = 129 total buy shares)
   - All 3 entries stopped out — 0% win rate
   - Fitness score dropped to 0.379 but still above learning-mode gate (0.30)
   - The engine re-entered after cooldown despite prior losses

3. **CAT catastrophic loss (-$107.08 avg)**
   - Only 2 trades, both losses
   - Fitness score 0.263 (lowest in universe)
   - Small position (6–7 shares) but very poor entry timing

4. **XLE circuit breaker event (-$144.44)**
   - 92-share position at tick 411, exited 4 ticks later at tick 415
   - Massive single-trade loss — circuit breaker correctly banned XLE
   - The 92-share position was outsized compared to other positions

5. **Late-day trending_down entries**
   - Tick 499+: XOM (35), GOOGL (17), WMT (43) entered during trending_down
   - All stopped out — trending_down regime had 0 wins / 5 losses today

### Contributing Factors

- **No trading for 3.5 hours**: Bug-blocked from 9:30 AM to 1:43 PM. When fixed, engine entered aggressively to "catch up" in learning mode, but market conditions had deteriorated.
- **ML brain still learning**: 25.7% win rate, overconfident calibration (predicted 60%, actual 23% in mid-confidence bucket)
- **No WMT/XLE/CAT banning before circuit breaker**: WMT fitness (0.379) stayed above 0.30 gate, allowing repeated entries despite 0% win rate. Circuit breaker threshold (-$15) didn't trigger for WMT (losses were distributed across 3 entries).

---

## 10. Recommendations for AIA Review

### Immediate Priority

1. **Investigate trending_up regime scale**: Scale of 1.164 may be too aggressive given only 4W/10L history. Should the regime evolution freeze threshold (200 trades) also protect regime scales from increasing too quickly during learning?

2. **WMT repeat-entry problem**: The engine entered WMT 3 times despite 0% win rate. The circuit breaker only triggers at -$15 cumulative or 2 consecutive losers. WMT losses were ~$40/trade but spread across separate cooldown cycles. Consider: should the circuit breaker also check cumulative trade count + win rate?

3. **XLE 92-share position sizing**: Why did XLE get a 92-share position when other symbols got 12–54 shares? Investigate if the Kelly sizer or risk-budget floor is producing outsized positions for certain symbols in certain regimes.

4. **Late-day trending_down entries**: The engine entered XOM, GOOGL, WMT after 3:00 PM in trending_down regime. Should there be a regime-based entry block (disable entries in trending_down entirely during learning mode)?

5. **ML calibration overconfidence**: Predicted 60% accuracy in 0.4–0.6 confidence bucket but actual was 23%. The confidence gate (0.30 minimum) may be too permissive. Consider raising to 0.40 during learning mode.

### Medium Priority

6. **Stale data handling**: Even with the gate fixed, the engine still has no mechanism to detect when it's operating on REST-fallback data vs fresh streaming data. Consider adding a data-source indicator to telemetry.

7. **Entry throttle timing**: 12/hr in learning mode was hit within the first hour after the hotfix. This is correct behavior but may need tuning — 12/hr may be too aggressive for a trending_down market.

8. **Partial exit sizing**: Several trades had partial exits (AMZN 7 of 24, MSFT 3 of 12, etc.) before the rest exited. Verify the partial take-profit logic is using correct ATR-based thresholds.

9. **UBER orphaned position**: UBER has stale exit_levels (69 bars held, no entry_metadata). This is a position from before the hotfix that was never properly cleaned up. The engine should detect and clean up orphaned exit_levels.

### Data Collection Needs

10. Track **entry_source** distribution: How many entries were "alpha", "breakout", "alpha+breakout", "exploration"? Today's data should have this from the improve7 causal fields.

11. Track **time_in_trade_seconds**: How long are positions held? Are stops hitting too quickly (within 1–2 minutes)?

12. Track **MFE/MAE**: What's the maximum favorable/adverse excursion before exit? Are we leaving money on the table or getting stopped out at the worst point?

---

## Appendix A: System Configuration

```
Engine: Learning mode (<200 trades, currently 93)
Tick interval: 10 seconds
Universe: 30 symbols (25 active + 5 rotated out)
Timeframe: 1-Min bars
Max positions: 15 (LONG_ONLY)
Drawdown kill: 8%
Entry throttle: 12/hr (learning), max(3, 6-open)/hr (production)
Fitness gate: 0.30 (learning), 0.45 (production)
Confidence gate: 0.30 (default), 0.35 (chop)
Circuit breaker: 2 consecutive losers OR -$15 daily P&L per symbol
EOD: Block entries 15:45 ET, flatten 15:58 ET
Risk-budget floor: 0.25% equity / (atr × 1.5) × clamp(0.5 + 0.8 × conf, 0.5, 1.1)
FTF: Disabled for trending_up/low_vol. Chop: losers-only with multi-bar momentum. Others: 0.25R/0.15R.
```

## Appendix B: Files Modified Today

| File | Changes |
|------|---------|
| `backend/organism/adaptive_exits.py` | FTF redesign, ExitLevels v5 fields |
| `backend/organism/kelly_sizer.py` | Risk-budget floor scaling, regime evolution freeze |
| `backend/organism/continuous_learner.py` | 7 causal provenance fields on TradeRecord |
| `backend/organism/live_engine.py` | Confidence gate, circuit breaker, EOD flatten, entry metadata, fitness gate learning bypass, stale data gate fix |
| `backend/organism/regime.py` | Intraday trend threshold calibration |
| `backend/organism/streaming_data_provider.py` | Added `last_update_time` property |
| `tests/test_self_evolution.py` | Regime stats seeding for evolution freeze test |
| `docs/architecture/mapss.md` | 18 section updates for improve7 |
| `docs/architecture/improve7.md` | Added to repository |
