# Track DD5 v11 — Strategy Logic Phase 5

V10 DD4 closed 3 strategy findings (DD4-1 fitness, DD4-2 Layer 2, DD4-4 telemetry). Wave-60 closed DD4-3 (inverse-ETF flip). **DD5 verifies all five fixes work in production AND drills into edges DD4 didn't reach.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`.

## Method

### 1. Wave-53 DD4-1 fitness gate verification

After Monday's restart with the wave-53 fix:
- Read `organism_brain/manifest.json` — does `extra_counters.symbol_trade_counts_runtime` exist?
- Compare to `evolved_params.symbol_trade_counts` — runtime should be ≥ promotion-gated.
- Cross-reference with `trade_history.csv` non-recon trade counts.

If runtime counts still match the V10 stale 62, the wave-53 persistence fix didn't take.

### 2. Wave-53 DD4-2 layer-2 reachability verification

Pull the most recent ~20 trades from `trade_history.csv`:
- Count `pyramid_action == "add"` events.
- Of those, how many `level=1` vs `level=2`?

If `level=2` count remains 0 after several days of post-fix trading, DD4-2's L0-entry-preservation fix didn't help.

### 3. Wave-60 DD4-3 inverse-ETF flip — empirical check

Pull SH/PSQ/DOG/RWM trades from `trade_history.csv`. For each:
- What was `regime_at_entry`?
- What was `stop_atr_mult` used? (need to deduce from `stop_loss_price - entry_price`).
- Compare to non-inverse symbols' stop math under the same regime.

If SH/PSQ stops are still computed against un-flipped regime, wave-60 didn't take.

### 4. Regime hysteresis on fast-flip days

V8 DD2-4 added hysteresis. On a "fast flip" day (regime changes 5+ times in 30 min), is the hysteresis sufficient to prevent thrashing?
- Read `regime_state.json` history if available.
- Look for transition density.

### 5. ML reversal one-shot guard re-audit

`_ml_reversal_used` is cleared on close. Verify:
- Search for `_ml_reversal_used.add` and `_ml_reversal_used.discard` / `_ml_reversal_used.remove`.
- Confirm every add has a matching clear.

### 6. Pyramid_cut analysis (V9 DD3-6 follow-through)

V9 DD3-6 noted 31% of closes are pyramid_cuts; chop-min-hold gate failed to suppress 3 of 5 short-bars-held cuts. Re-pull recent data:
- pyramid_cut count / total close count
- For each pyramid_cut, was bars_held < 10? Should now be suppressed by chop-min-hold.

### 7. Day-N edge concentration

Pull all trades since wave-53 deploy. Compute:
- mean PnL excluding top-2 winners
- Sharpe excluding top-2 winners
- Symbol concentration (top 3 symbols' share of total PnL)

V9 DD3-6 found edge was 1-symbol concentrated (AMD). Has it broadened?

### 8. EOD flatten + cancel-pending-entries empirical (wave-44 DD3-4)

If today was a trading day, look for orders submitted at 15:55-15:59 ET that filled post-16:00. Should be ZERO post-wave-44.

### 9. Confidence calibration drift post-wave-33

Re-pull `_calibration_counts` from `organism_brain/ml_state.json`. Has the bin distribution shifted to be more uniform (sign of correct axis-binning)?

### 10. Pyramider telemetry hookup (wave-53 DD4-4)

`MomentumPyramider.telemetry()` exists; is it called from anywhere? If not, the counter is still write-only.

## Output

`artifacts/audit/v11_reports/track_dd5_strategy_phase5.md` with per-section findings + observations.

Quality bar: 2-5 findings.
