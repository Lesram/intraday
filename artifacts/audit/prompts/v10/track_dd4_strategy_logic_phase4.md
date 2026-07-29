# Track DD4 v10 — Strategy Logic Phase 4

V9 DD3 found 6 strategy-logic findings; wave-44 closed DD3-1 (pyramider Layer 2 reachability), DD3-4 (EOD pending-entry cancel), DD3-5 (fitness gate missing-data). **DD4 verifies the production behavior matches the design AND drills into edges DD3 didn't reach**.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `35a1fe9`.

## Method

### 1. Verify wave-44 DD3-5 fitness gate ACTUALLY rejects

The wave-44 fix says: if `symbol_fitness` has no entry for a symbol AND `trade_count >= min_trades_for_fitness`, BLOCK with reason "fitness_gate".

Verify via:
- Read `organism_brain/manifest.json` `evolved_params.symbol_fitness`. Note: V9 found this empty at gen 168.
- For each symbol in the universe, check `evolved_params.symbol_trade_counts.get(symbol, 0)` — how many would now be blocked?
- Compare expected-block list to actual entry telemetry (if available in `tick_telemetry`).

If the fix is in place but no symbols are blocked, either:
- (a) symbol_trade_counts is also empty (gate condition unmet)
- (b) all symbols ARE in symbol_fitness and the gate isn't engaging

Document which.

### 2. Verify wave-44 DD3-1 pyramider Layer 2 reaches in production

In the most recent ~50 trades from `organism_brain/trade_history.csv`:
- How many had `pyramid_action == "add"`?
- How many were Layer 1 vs Layer 2?
- Does the Layer 2 path ever fire post-deploy?

If Layer 2 still doesn't fire, the wave-44 fix may have a remaining gap (e.g., `r_current` never reaches `ADD_2_THRESHOLD` because an upstream gate cuts the position first).

### 3. Pyramid R-multiple math under partial fills

V8 DD2 partially-touched but V9 DD3 didn't drill: when a pyramid Layer 1 add fills only 30% of intended, what does `position.r_multiple` compute against?
- `entry = position.layers[0].entry_price` — only the FIRST layer's entry, not the weighted average.
- This means subsequent fills at higher prices but partial qty don't affect R-multiple.
- Verify that `_pyramider.check_pyramid` doesn't accidentally re-fire Layer 1 because the partial layer didn't materialize.

### 4. Reconcile-fill collapse audit (the V9 DD3 root cause)

V9 DD3 noted "post-fill collapse in `_reconcile_fills` (live_engine.py:5114-5129) leaves `pyr.layers` length 1 forever". Verify whether wave-44's `max_level` fix is sufficient or whether the collapse code itself needs repair.

Read `live_engine.py:5114-5129` and walk through the collapse logic. Document whether:
- The collapse is intentional (and `max_level` is the correct workaround).
- The collapse is a bug and `pyr.layers` should grow naturally with each fill.

### 5. ML reversal one-shot guard

`_ml_reversal_used: set[str]` — a position that gets one ML-reversal exit can't get another. Verify:
- On position close, does the symbol get removed from `_ml_reversal_used`?
- Search for `_ml_reversal_used.discard\|_ml_reversal_used.remove`.
- If not removed on close, the next position in the same symbol can't ever trigger ML-reversal.

### 6. Confidence axis post-wave-33 verification

V8 DD2-2 / Wave-33 fixed ML calibration axes. Verify the actual prediction outcomes recorded since wave-33 deploy use raw_confidence:
- Read `organism_brain/ml_state.json` if it has calibration_counts.
- Check whether bin distributions look reasonable (not all in bin 4).

### 7. Stop-loss precedence under multiple triggers

In a single tick:
- Position has stop_loss_price = $99.
- Current price = $98.50 (past stop).
- ML reversal also fires.
- Pyramid cut also fires.

Which exit reason wins? Is the order deterministic? Document.

### 8. Inverse-ETF (SH/PSQ) regime flip composability

V8 DD2-6 (deferred) noted inverse-ETF flip lives only in AlphaScanner, not Kelly / AdaptiveExits / cooldown. Verify:
- Has DD2-6 been addressed? (Likely no.)
- For the most recent SH or PSQ trade, what regime did Kelly / AdaptiveExits use?

### 9. Day-2 / Day-3 production observation continuation

Since DD3-6 was diagnostic-only and recommended 2-week observation: pull recent trade_history rows and report concentration of edge.

### 10. Replay-determinism gaps (audit `_now_fn` again)

Wave-35 DD2-10 closed runner.py + routes.py. Re-grep:

```
grep -rn "datetime\.now(UTC)\|datetime\.now(timezone\.utc)" backend/ --include='*.py' | grep -v test | head -20
```

Identify any new sites added in waves 41-49.

## Output

`artifacts/audit/v10_reports/track_dd4_strategy_logic_phase4.md` with findings, source-file:line citations, behavioral test descriptions.

Quality bar: 2-5 findings.
