# Experiment 4 — Trailing-Stop Giveback Control in Chop

**Commit**: `b97f903`
**Status**: COMMITTED, NOT deployed. Queued behind Exp2.

## Hypothesis
In chop, the trailing stop distance (3.0× ATR from high) is too tight. Normal chop oscillation routinely retraces 3× ATR from highs, triggering the trailing stop on trades that would have recovered. The NVDA trade on Apr 13 had $13.81 MFE but closed at -$1.08 via trailing stop — giving back the entire gain.

## Implementation
In `adaptive_exits.py:_update_trailing_stop()`, when regime is chop:

**Variant A (default: "widen")**: Trail distance widened from 3.0× to 5.0× ATR. Gives trades room to breathe through chop oscillation while still protecting against genuine reversals.

**Variant B ("disable")**: Trailing stop skipped entirely in chop. Trades rely on timeout/max_hold (which is 100% win rate in the baseline) as the primary exit.

Controlled by `_EXP4_CHOP_TRAIL_MODE` constant. Easy to switch between variants for A/B testing.

## Files changed
| File | +/- |
|---|---|
| `backend/organism/adaptive_exits.py` | +40/−3 |
| `tests/test_experiment_4_trailing_giveback.py` | +194 (new) |
| `scripts/generate_experiment_observation_report.py` | +80 (giveback section) |

## Expected measurable effect
**Variant A**: If the NVDA trade had 5× ATR trail, it would have survived the reversal. Expected: $5-15 improvement per session from 1-3 trailing-stop trades that would have otherwise given back gains.

**Variant B**: More aggressive — all chop trades exit via timeout (30 bars max) or stop_loss. Expected: higher capture rate but potentially larger worst-case losses on genuine reversals.

## Risk
**Variant A**: Moderate. Wider trail = larger giveback before exit if the reversal is genuine. Worst case: a 5× ATR reversal still triggers the trail, but the loss is larger than with 3× ATR.

**Variant B**: Higher risk. Disabling trailing entirely means a trade can go from +$14 to -$14 before the stop_loss fires. Only recommended if timeout exits consistently capture enough MFE.

## Recommended variant
**Variant A (widen to 5.0× ATR)**. It preserves trailing as a safety mechanism while reducing false triggers in chop. Variant B is too aggressive without more data.

## Deployment order
**Behind Exp2.** Exp2 (suppress PSQ/SH in chop) is higher confidence (0% win rate, 6 trades, 4 days) and orthogonal. Exp4 should deploy AFTER Exp2 and AFTER the Exp1A observation confirms that trailing-stop giveback is a persistent pattern (not a single-session artifact).

If Exp1A Day 2-3 data shows 3+ more trailing-stop givebacks > $5, Exp4 could leapfrog Exp2 based on expected value.

## Rollback
```bash
git revert b97f903
```

## Observation tooling update
The daily report generator now includes an "Exit giveback analysis" section with total MFE, capture rate, giveback by exit reason, and top 3 worst giveback trades. No separate giveback analysis task needed going forward.
