# H1 + H2 Offline Report

**Commit**: `679ffd2`
**Status**: COMMITTED, NOT deployed. Ready for bundle deploy.

## H1 — Production risk-budget cap

**File**: `backend/organism/kelly_sizer.py` (+18 lines, ~line 510)
**Root cause**: `_RISK_BUDGET_PER_TRADE = 0.0025` (0.25% equity) defined at line 157 but never applied in the production Kelly sizing path. Only the learning-mode cap (`_RISK_BUDGET_PER_TRADE_LEARNING = 0.0010`) was active (lines 488-502). Production mode had no per-trade dollar-risk limit.
**Fix**: After Kelly sizing completes, clamp shares by `portfolio_value * 0.0025 / (atr_pct * 1.5 * current_price)`. Same formula as learning-mode cap, at the production rate.
**Impact**: Caps the maximum loss per trade to 0.25% of equity regardless of Kelly output. At $100K equity, that's $250 max risk per trade.
**Rollback**: `git revert 679ffd2`

## H2 — Feature drift guard

**File**: `backend/organism/ml_signal.py` (+25/-4 lines, ~line 341)
**Root cause**: Existing code zero-pads missing features (won't crash), but zero-padding >20% of trained features produces degraded predictions that look valid. No rejection mechanism.
**Fix**: If `missing_pct > 0.20`, log ERROR with exact counts and return neutral signal (direction=0, confidence=0). Below 20%, existing zero-padding behavior preserved.
**Impact**: Prevents degraded ML predictions from passing as legitimate signals when market data is incomplete.
**Rollback**: Same commit.

## Tests — 112/112 passed
- 2 H1 tests (production cap applies / learning mode unchanged)
- 3 H2 tests (major drift → neutral / minor drift → signal / full features → normal)
- 107 organism regression — PASS

## Bundle deploy plan
H1 + H2 deploy together with G1/G2/G3 + notional cap + daily max-loss in the next hardening deploy (Deploy 2 per the execution plan).
