# Real-Money Risk Limits — Offline Report

**Commit**: `bb5cbb5`
**Status**: COMMITTED, NOT deployed. Ready for bundle deploy.

## Per-trade notional cap

**File**: `backend/organism/live_engine.py` (entry loop, ~line 2486)
**Env var**: `ORGANISM_MAX_NOTIONAL` (default: 0 = disabled)
**Behavior**: If `initial_shares * current_price > MAX_NOTIONAL_PER_TRADE`, clamp shares to `max(1, int(cap / price))`. Logged when capping.
**Stage 1 config**: `ORGANISM_MAX_NOTIONAL=2500` ($2,500 per trade on $5K account)

## Daily max-loss circuit breaker

**File**: `backend/organism/live_engine.py` (equity check, ~line 1413)
**Env var**: `ORGANISM_MAX_DAILY_LOSS` (default: 0 = disabled)
**Behavior**: Tracks daily starting equity (resets on new date). If `equity - starting < -MAX_DAILY_LOSS`, calls `governance.halt_trading()`. Entries blocked, exits continue. Resume via `POST /organism/resume`. CRITICAL log.
**Stage 1 config**: `ORGANISM_MAX_DAILY_LOSS=250` ($250 = 5% of $5K)

## Tests — 116/116 passed
- 4 CAP tests (cap applies / under limit / disabled / min 1 share)
- 5 HALT tests (triggers / no trigger / next-day reset / disabled / positive day)
- 107 organism regression — PASS

## Bundle deploy plan
Deploy together with G1/G2/G3 + H1/H2 as the complete real-money hardening package.
Both features are DISABLED by default (env var = 0) so they have zero impact until explicitly configured in .env.

## Rollback
```bash
git revert bb5cbb5
```
