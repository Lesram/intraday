# Experiment 1A — Chop-regime minimum-hold gate for pyramid_cut

**Commit**: `ab54b2f`
**Parent**: `7d36b61` (Full Patch F tip)
**Status**: COMMITTED, not deployed.

## Hypothesis

In chop regime, pyramid_cut exits fire too early on temporary adverse excursions, destroying edge that the entry system generates. 78% of trades go green (MFE > 0), but 76% of those green trades close negative because pyramid cuts trigger at −1.0R to −1.8R within the first 2-5 bars. Meanwhile, trades forced to hold to timeout (18-30 bars) are 100% winners. A minimum hold of 10 bars before pyramid cuts can fire in chop should allow entries to work through temporary noise.

## Exact change

In `backend/organism/live_engine.py`, inside `_live_tick_inner` at the pyramid `close_partial` processing block (~line 1926):

```python
_CHOP_MIN_HOLD_BARS = 10
_is_chop = (regime == "chop")
_meta = self._entry_metadata.get(sym, {})
_entry_tick = _meta.get("entry_tick", 0)
_bars_held = self._tick_count - _entry_tick
if _is_chop and _bars_held < _CHOP_MIN_HOLD_BARS:
    # Log suppression and continue (skip the pyramid cut)
    continue
```

**What is NOT changed**:
- `stop_loss` — still fires immediately via `adaptive_exits.check_exit` (separate code path, step 5 in the tick loop). The ATR-based stop is the real risk control; pyramid cuts are just an anti-pyramid sizing tool.
- `horizon_timeout` / `max_holding_period` — still fire at 18/30 bars via `adaptive_exits.check_exit`.
- Non-chop regime pyramid cuts — unchanged. Trending/high_vol/stress regimes keep their normal cut behavior.
- Entry logic, sizing, ML, walk-forward gate — untouched.

## Files changed

| File | +/- |
|---|---|
| `backend/organism/live_engine.py` | +27 |
| `tests/test_experiment_1a_chop_min_hold.py` | +225 (new) |

## Instrumentation

When a pyramid_cut is suppressed, logs:
```
Exp1A: pyramid_cut suppressed (chop min-hold): PSQ bars_held=3/10 regime=chop r=-1.3R unrealized=$-4.60 reason=cut_full_at_-1.3R
```

This lets us measure exactly how many cuts are suppressed, what their R-multiples were, and what the unrealized PnL was at suppression time. If suppressed trades subsequently hit stop_loss at a larger loss, the instrumentation will show it.

## Tests — 115/115 passed

| Suite | Count | Status |
|---|---:|---|
| Experiment 1A focused | 8 | PASS |
| Organism regression (5 files) | 107 | PASS |

## Expected measurable effect

Based on Apr 7-10 baseline (32 real trades):
- **12 premature exits (≤5 bars, negative)** accounted for −$52.68 (86% of total loss)
- If the 10-bar hold gate prevents even HALF of those premature cuts from firing, expected improvement: **+$25–35 per 4-day window**
- Best case (all 12 premature exits held to timeout): **+$50–65** improvement
- Worst case (held trades hit stop_loss at larger loss): net PnL could worsen by ~$10–15 per window
- **Net expected value: +$15–50 per 4-day window** (positive skew because MFE capture rate is 78%)

## What to watch in the observation window

1. **`Exp1A: pyramid_cut suppressed` log count** — how many cuts are being held back
2. **Win rate on trades that survive the hold period** — should increase from the baseline 18.8%
3. **Average hold time** — should increase from the baseline 550s median
4. **Stop_loss frequency** — may increase slightly (some held trades will eventually hit the wider stop instead of the tighter pyramid cut)
5. **Net PnL change vs baseline** — the real verdict

## Recommended observation window

**Minimum 3 sessions, ideally 5** (to accumulate ~30+ trades for statistical comparison against the 32-trade baseline). At the current ~8 trades/day pace, 5 sessions = ~40 trades.

## Rollback steps

```bash
git revert ab54b2f
# or
git reset --hard 7d36b61  # DESTRUCTIVE — only if ab54b2f is the tip
```

Rollback removes the 10-bar hold gate; pyramid cuts revert to firing immediately in all regimes.

## Safe for paper-trading deployment?

**Yes.** The change is a single conditional gate (27 lines) in one code path. It preserves all safety mechanisms:
- `stop_loss` is unaffected (fires via a completely separate exit-check loop)
- EOD flatten is unaffected
- Position reconciliation is unaffected
- The worst case is slightly larger per-trade losses if held trades hit stop — but the stop-loss ATR already provides the risk boundary
