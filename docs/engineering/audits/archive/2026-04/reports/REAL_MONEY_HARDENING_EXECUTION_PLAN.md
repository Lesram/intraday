# Real-Money Hardening Execution Plan

**Date**: 2026-04-19
**Current state**: Paper trading at ce06d41 (Exp1A + Exp2 + Exp3 prep)
**Target**: Stage 1 tiny live-capital candidate ($5K)
**Current equity**: $111,558 paper

---

## Execution sequence — 6 steps, 3 deploys

### Step 1: G1/G2/G3 mechanical hardening [DEPLOY 1]

**Already committed at `15cc0a4`.** Low risk, orthogonal to experiments.

| Fix | What | File | Lines | Risk |
|---|---|---|---|---|
| G1 | Exit-level restore → WARNING + mark for safety | live_engine.py:816-822 | +12 | Very low |
| G2 | Exit cooldown on success only (remove finally block) | live_engine.py:1679-1690 | +8/-5 | Low |
| G3 | NaN/Inf/zero guard on pyramider current_price | pyramider.py:164-169 | +8 | Very low |

**Bundle**: All three in one deploy (single commit). Tested: 119/119 pass.
**Deploy timing**: Next post-close window (Mon Apr 20 or later).
**Rollback**: `git revert 15cc0a4`

---

### Step 2: H1 — Activate production risk-budget [new code needed]

**Problem**: `_RISK_BUDGET_PER_TRADE = 0.0025` (0.25% equity) is defined at `kelly_sizer.py:157` but NEVER used in the production sizing path. Only the learning-mode constant (`_RISK_BUDGET_PER_TRADE_LEARNING = 0.0010`) is active (line 336). When the system exits learning mode, per-trade risk is uncapped.

**Fix** (~15 lines):
In `kelly_sizer.py` `size_positions()`, add a production-mode risk-budget clamp AFTER the Kelly sizing path completes (around line 487):

```python
# H1: Apply per-trade risk-budget cap in production mode
if not _is_learning and _risk_budget_applied is False:
    stop_distance = atr * _RISK_BUDGET_STOP_ATR
    if stop_distance > 0:
        max_shares_by_risk = int(
            (portfolio_value * _RISK_BUDGET_PER_TRADE) / stop_distance
        )
        if sz.shares > max_shares_by_risk:
            sz.shares = max_shares_by_risk
            sz.notional = sz.shares * current_price
```

**Bundle**: Can bundle with H2 (same deploy).
**Tests**: Add 2 tests (production risk cap applied / learning risk cap unchanged).

---

### Step 3: H2 — Feature drift crash guard [new code needed]

**Problem**: If SPY drops from streaming, cross-sectional features are skipped, producing 74 features instead of 79. XGBoost trained on 79 features will crash with `ValueError: X has wrong number of features`.

**Fix** (~10 lines):
In `ml_signal.py` before inference (around line 580):

```python
# H2: Guard against feature drift between training and inference
if len(actual_features) != len(self._feature_cols):
    logger.error(
        "H2: Feature drift detected — inference has %d features, "
        "model trained on %d. Returning neutral signal.",
        len(actual_features), len(self._feature_cols),
    )
    return MLSignal(direction=0, confidence=0.0, predicted_return=0.0)
```

**Bundle**: Bundle with H1 in one deploy.
**Tests**: Add 2 tests (drift detected → neutral / normal → signal).

---

### Step 4: Per-trade notional cap [new code needed, DEPLOY 2]

**Problem**: IWM -$41.52 showed that position sizing can allow single-trade notional up to ~$5K+ with no hard cap. In a $5K live account, this would be 100% of capital in one trade.

**Design**:
In `live_engine.py` entry loop (around line 2451), add a hard notional cap:

```python
# REAL-MONEY: Per-trade notional cap
_MAX_NOTIONAL_PER_TRADE = float(os.getenv("ORGANISM_MAX_NOTIONAL", "5000"))
_notional = sz.shares * current_price
if _notional > _MAX_NOTIONAL_PER_TRADE:
    sz.shares = max(1, int(_MAX_NOTIONAL_PER_TRADE / current_price))
    logger.info("Notional cap: %s capped from %d to %d shares ($%.0f → $%.0f)",
                sz.symbol, original_shares, sz.shares, _notional, sz.shares * current_price)
```

Configurable via env var. Default $5K for Stage 1. Scale up for Stage 2+.

**Bundle**: Bundle with daily max-loss halt (Step 5) in one deploy.
**Tests**: Add 3 tests (cap applied / under cap unchanged / env override).

---

### Step 5: Daily max-loss auto-halt [new code needed, bundled with Step 4]

**Design**:
In `live_engine.py` at the equity check section (around line 1395), add daily loss tracking:

```python
# REAL-MONEY: Daily max-loss circuit breaker
_MAX_DAILY_LOSS = float(os.getenv("ORGANISM_MAX_DAILY_LOSS", "500"))
if not hasattr(self, '_daily_starting_equity'):
    self._daily_starting_equity = equity
    self._daily_loss_date = self._now_fn().date()

current_date = self._now_fn().date()
if current_date != self._daily_loss_date:
    self._daily_starting_equity = equity
    self._daily_loss_date = current_date

daily_pnl = equity - self._daily_starting_equity
if daily_pnl <= -_MAX_DAILY_LOSS:
    self.governance.halt_trading()
    logger.critical(
        "DAILY MAX-LOSS HALT: PnL=$%.2f exceeds -$%.0f limit. "
        "Trading halted for the day. Resume manually.",
        daily_pnl, _MAX_DAILY_LOSS,
    )
    entries_blocked = True
```

Configurable via env var. Default $500. Uses existing governance.halt_trading() mechanism — resume via `POST /organism/resume`.

**Tests**: Add 3 tests (halt fires at threshold / no halt above threshold / resets next day).

---

### Step 6: Monitoring/alerting minimum viable stack [DEPLOY 3]

**Current gap**: diagnostics warn "No alert channels configured." No Slack/email alerts for:
- daily max-loss halt
- guard fires (BRAIN SAVE BLOCKED etc.)
- container restarts
- unusual error spikes

**Minimum viable approach**:
Configure a webhook URL in `.env` (`ALERT_WEBHOOK_URL`) and wire the existing `backend/infra/alerting.py` to POST to it. Slack incoming webhook is the simplest path.

```
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
```

The alerting module already exists (`backend/infra/alerting.py:290` shows "No alert channels configured"). It just needs the webhook wired.

**Effort**: Small — configure env var, wire existing module.
**Bundle**: Standalone deploy or bundle with Step 4/5.

---

## Rollback and kill-switch rules

### Kill switches (already working)
| Method | Path | Effect |
|---|---|---|
| Manual halt | `POST /api/v1/organism/halt` | Stops all entries, continues exits |
| Manual resume | `POST /api/v1/organism/resume` | Resumes trading |
| Freeze | `POST /api/v1/organism/freeze` | Freezes parameter adaptation |
| Force-save | `POST /api/v1/organism/save?force=true` | Full brain dump to disk |
| Container stop | `docker compose stop api` | Graceful shutdown + brain save |
| **NEW: Daily max-loss** | Auto-triggers governance.halt_trading() | Stops entries when daily loss exceeds threshold |

### Rollback rules for real money
1. **Any single-trade loss > 10% of live capital** → manual halt + investigate
2. **Daily max-loss halt fires** → do not resume until next day + review
3. **Container restart with open positions** → force-save before restart, verify positions after
4. **Guard fire (BRAIN SAVE BLOCKED / FORENSIC GUARD)** → halt + force-save + investigate
5. **Expectancy turns negative over 5+ sessions** → halt + reassess

### Rollback sequence
```bash
# 1. Halt trading immediately
curl -X POST http://localhost:8000/api/v1/organism/halt -H "Authorization: Bearer $TOKEN"

# 2. Force-save brain state
curl -X POST "http://localhost:8000/api/v1/organism/save?force=true" -H "Authorization: Bearer $TOKEN"

# 3. If code rollback needed:
git checkout <safe_commit>
docker compose -f docker-compose.paper.yml up -d --build api
```

---

## Stage 1 gating criteria

All of the following MUST be true before live capital:

| # | Criterion | How to measure | Current status |
|---|---|---|---|
| 1 | Expectancy ≥ +$0.50/trade sustained ≥2 weeks | Cumulative from observation reports | -$0.50 (improving) |
| 2 | Win rate ≥ 25% sustained ≥2 weeks | Same | 34.3% ✅ |
| 3 | Max single-trade loss < 5% of live capital | Per-trade notional cap deployed | NOT YET |
| 4 | Daily max-loss halt deployed and tested | Step 5 above | NOT YET |
| 5 | G1/G2/G3 deployed | Step 1 above | OFFLINE READY |
| 6 | H1 (production risk-budget) deployed | Step 2 above | NOT CODED |
| 7 | H2 (feature drift guard) deployed | Step 3 above | NOT CODED |
| 8 | Monitoring/alerting configured | Step 6 above | NOT CONFIGURED |
| 9 | Container stable ≥7 days without restart | Track uptime | 3.5 days ✅ |
| 10 | Zero guard fires over the observation window | Guard logs | ✅ ZERO |

### Stage 1 parameters
- Capital: **$5,000**
- Max notional per trade: **$2,500** (50% of capital)
- Max daily loss: **$250** (5% of capital)
- Max open positions: **4** (reduce from 8)
- Risk per trade: **0.25%** ($12.50 max risk)
- Paper parallel: continue paper trading on separate account for comparison

---

## Deploy timeline

| Step | Content | Deploy | Prerequisite |
|---|---|---|---|
| **1** | G1/G2/G3 | DEPLOY 1 (next post-close) | Exp2 observation continues |
| **2+3** | H1 + H2 | Bundle with Deploy 2 | Step 1 deployed |
| **4+5** | Notional cap + daily max-loss | DEPLOY 2 | Steps 2+3 coded |
| **6** | Alerting webhook | DEPLOY 3 or bundle | Steps 4+5 deployed |
| **Gate** | 2 weeks positive expectancy | Observation only | All steps deployed |
| **Stage 1** | Switch to live Alpaca keys | Config change | Gate criteria met |

**Earliest realistic Stage 1 date**: **Week of May 5** — IF expectancy stays positive through Apr 21-May 2 AND all 6 steps are deployed by Apr 28.
